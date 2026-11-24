"""Core execution worker for SaaS multi-tenant search-and-apply cycles."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.api.state import bot_state
from app.browser.context import BrowserManager
from app.config import get_settings
from app.db.database import get_session
from app.db.models import User, VacancyStatus
from app.db.repositories import (
    get_setting,
    list_active_bot_users,
    list_vacancies,
    set_setting,
    update_user_bot_state,
)
from app.hh.client import HHClient
from app.scheduler.limits import RateLimiter

logger = logging.getLogger(__name__)


class BotWorker:
    """Coordinates search, limit enforcement, and vacancy applications across SaaS users."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.rate_limiter = RateLimiter()
        self.stop_event = asyncio.Event()

    def request_stop(self) -> None:
        """Signal worker to abort current tasks gracefully within 5 seconds."""
        logger.info("Worker stop requested")
        self.stop_event.set()

    def reset_stop(self) -> None:
        """Clear stop flag for new runs."""
        self.stop_event.clear()

    async def run_cycle(self) -> None:
        """Execute automated search and application cycle across all active users."""
        if self.stop_event.is_set():
            logger.info("Cycle skipped: stop event is set")
            return

        async with get_session() as session:
            active_users = await list_active_bot_users(session)

        if not active_users:
            logger.info("No active bot users found to process in this cycle.")
            return

        logger.info("Starting automated cycle for %d active users...", len(active_users))

        for user in active_users:
            if self.stop_event.is_set():
                break

            try:
                await self.run_user_cycle(user)
            except Exception as e:
                logger.error("Error running cycle for user #%d (%s): %s", user.id, user.email, e, exc_info=True)
                async with get_session() as session:
                    await update_user_bot_state(
                        session, user.id, last_error=str(e), bot_status="error", current_action=f"Ошибка: {e}"
                    )
                    await session.commit()

    async def run_user_cycle(self, user: User) -> None:
        """Execute automated search and apply cycle for a single user."""
        logger.info("Processing cycle for user #%d (%s)...", user.id, user.email)

        async with get_session() as session:
            await update_user_bot_state(
                session, user.id, bot_status="running", current_action="Проверка лимитов..."
            )
            await session.commit()

        browser_manager = BrowserManager(user_id=user.id, proxy_url=user.proxy_url)
        client = HHClient(
            browser_manager,
            user_id=user.id,
            auth_key=user.gigachat_auth_key,
            scope=user.gigachat_scope,
            target_salary=user.target_salary,
        )

        try:
            # 1. Verify rate limits for this user
            async with get_session() as session:
                allowed, reason = await self.rate_limiter.can_apply(session, user_id=user.id)
                if not allowed:
                    logger.info("Pausing run for user #%d: %s", user.id, reason)
                    await update_user_bot_state(
                        session, user.id, bot_status="idle", current_action=reason
                    )
                    await session.commit()
                    return

            # 2. Check pending unapplied vacancies from DB
            async with get_session() as session:
                pending_vacancies = await list_vacancies(
                    session, user_id=user.id, status=VacancyStatus.new, limit=100
                )

            # 3. If fewer than 50 unapplied vacancies remain, scan search results
            pages_scanned = 0
            max_pages_per_cycle = 5

            while len(pending_vacancies) < 50 and pages_scanned < max_pages_per_cycle:
                if self.stop_event.is_set():
                    break

                async with get_session() as session:
                    cur_page_str = await get_setting(session, user.id, "search_current_page")
                    cur_page = int(cur_page_str) if cur_page_str else 0

                    logger.info(
                        "User #%d: scanning hh.ru search (page %d, pending in DB: %d)...",
                        user.id,
                        cur_page,
                        len(pending_vacancies),
                    )
                    collected = await client.search_and_collect(session, page_num=cur_page)

                    if len(collected) == 0 or cur_page >= 30:
                        await set_setting(session, user.id, "search_current_page", "0")
                    else:
                        await set_setting(session, user.id, "search_current_page", str(cur_page + 1))
                    await session.commit()

                    pages_scanned += 1
                    pending_vacancies = await list_vacancies(
                        session, user_id=user.id, status=VacancyStatus.new, limit=100
                    )

            logger.info("User #%d: pending new vacancies to process: %d", user.id, len(pending_vacancies))

            # 4. Sequentially process and apply to vacancies
            applied_in_this_cycle = 0

            for vacancy in pending_vacancies:
                if self.stop_event.is_set():
                    break

                # Re-check rate limits
                async with get_session() as session:
                    can_go, _ = await self.rate_limiter.can_apply(session, user_id=user.id)
                    if not can_go:
                        logger.info("User #%d: rate limit reached mid-cycle", user.id)
                        break

                async with get_session() as session:
                    success = await client.apply_to_vacancy(session, vacancy)

                if success:
                    applied_in_this_cycle += 1

            now = datetime.now(timezone.utc)
            async with get_session() as session:
                await update_user_bot_state(
                    session,
                    user.id,
                    bot_status="idle",
                    current_action="Ожидание следующего цикла",
                    last_run_at=now,
                    last_error=None,
                )
                await session.commit()

        finally:
            await browser_manager.close()
