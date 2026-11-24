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
        self._user_stop_events: dict[int, asyncio.Event] = {}
        self._running_users: set[int] = set()
        self._cycle_lock = asyncio.Lock()

    def is_user_running(self, user_id: int) -> bool:
        """Check if a cycle is already currently running for a given user."""
        return user_id in self._running_users

    def request_stop(self) -> None:
        """Signal worker to abort current tasks gracefully within 5 seconds."""
        logger.info("Worker stop requested")
        self.stop_event.set()

    def stop_user(self, user_id: int) -> None:
        """Signal worker to abort a specific user's running cycle immediately."""
        evt = self._user_stop_events.get(user_id)
        if evt:
            evt.set()
            logger.info("User #%d: Stop signal delivered", user_id)

    def reset_stop(self) -> None:
        """Clear stop flag for new runs."""
        self.stop_event.clear()

    async def run_cycle(self) -> None:
        """Execute automated search and application cycle across all active users."""
        if self.stop_event.is_set():
            logger.info("Cycle skipped: stop event is set")
            return

        if self._cycle_lock.locked():
            logger.info("Cycle skipped: another run_cycle is currently in progress")
            return

        async with self._cycle_lock:
            async with get_session() as session:
                active_users = await list_active_bot_users(session)

            if not active_users:
                logger.info("No active bot users found to process in this cycle.")
                return

            logger.info("Starting automated cycle for %d active users...", len(active_users))

            for user in active_users:
                if self.stop_event.is_set():
                    break

                if self.is_user_running(user.id):
                    logger.info("User #%d (%s) already has a cycle running. Skipping in scheduled tick.", user.id, user.email)
                    continue

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
        if user.id in self._running_users:
            logger.info("User #%d (%s) is already executing a cycle. Skipping duplicate call.", user.id, user.email)
            return

        self._running_users.add(user.id)
        user_stop_event = asyncio.Event()
        self._user_stop_events[user.id] = user_stop_event
        browser_manager = None
        try:
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

            # 0. Check GigaChat API key
            effective_key = user.gigachat_auth_key or self.settings.gigachat_auth_key.get_secret_value()
            if not effective_key:
                logger.warning("User #%d has no GigaChat API key configured", user.id)
                async with get_session() as session:
                    await update_user_bot_state(
                        session, user.id, bot_status="idle", current_action="Ошибка: укажите личный GigaChat API ключ в Настройках"
                    )
                    await session.commit()
                return

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
                if self.stop_event.is_set() or user_stop_event.is_set():
                    logger.info("User #%d: Stop requested during search scanning.", user.id)
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

            consecutive_errors = 0
            for vacancy in pending_vacancies:
                if self.stop_event.is_set() or user_stop_event.is_set():
                    logger.info("User #%d: Stop requested, aborting vacancy loop.", user.id)
                    break

                # Double check DB flag: did user toggle bot off on the website?
                async with get_session() as session:
                    from app.db.repositories import get_user_by_id
                    current_user = await get_user_by_id(session, user.id)
                    if not current_user or not current_user.bot_enabled:
                        logger.info("User #%d: bot disabled on website (bot_enabled=False). Stopping cycle immediately.", user.id)
                        break

                # Re-check rate limits
                async with get_session() as session:
                    can_go, _ = await self.rate_limiter.can_apply(session, user_id=user.id)
                    if not can_go:
                        logger.info("User #%d: rate limit reached mid-cycle", user.id)
                        break

                async with get_session() as session:
                    success = await client.apply_to_vacancy(session, vacancy, stop_event=user_stop_event)

                if success:
                    applied_in_this_cycle += 1
                    consecutive_errors = 0
                else:
                    consecutive_errors += 1
                    # Protective cooldown to prevent rapid error cycling
                    await asyncio.sleep(2.0)
                    if consecutive_errors >= 5:
                        logger.warning(
                            "User #%d: 5 consecutive vacancy errors encountered. Pausing cycle to protect account and resources.",
                            user.id,
                        )
                        break

            now = datetime.now(timezone.utc)
            async with get_session() as session:
                from app.db.repositories import get_user_by_id
                current_user = await get_user_by_id(session, user.id)
                is_still_enabled = (
                    current_user
                    and current_user.bot_enabled
                    and not user_stop_event.is_set()
                    and not self.stop_event.is_set()
                )
                if is_still_enabled:
                    await update_user_bot_state(
                        session,
                        user.id,
                        bot_status="idle",
                        current_action="Ожидание следующего цикла",
                        last_run_at=now,
                        last_error=None,
                    )
                else:
                    await update_user_bot_state(
                        session,
                        user.id,
                        bot_enabled=False,
                        bot_status="stopped",
                        current_action="Остановлен пользователем",
                        last_run_at=now,
                    )
                await session.commit()

        finally:
            self._running_users.discard(user.id)
            self._user_stop_events.pop(user.id, None)
            if browser_manager:
                await browser_manager.close()
