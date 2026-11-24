"""APScheduler service for periodic job runs with randomized jitter and graceful shutdown."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.api.state import bot_state
from app.config import get_settings
from app.scheduler.worker import BotWorker
from app.utils.power import prevent_sleep

logger = logging.getLogger(__name__)


class SchedulerService:
    """Manages periodic execution of search_and_apply jobs with launch jitter."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.scheduler = AsyncIOScheduler()
        self.worker = BotWorker()
        self._is_active: bool = False
        self._job_id = "search_and_apply_job"

    def is_active(self) -> bool:
        return self._is_active

    async def _scheduled_task_wrapper(self) -> None:
        """Wrapper that executes cycle and schedules next run with randomized jitter."""
        if not self._is_active:
            return

        # Load interval (check runtime DB override first)
        base_mins = self.settings.search_interval_minutes
        try:
            from app.db.database import get_session
            from app.db.repositories import get_setting

            async with get_session() as session:
                override = await get_setting(session, "search_interval_minutes")
                if override is not None:
                    base_mins = max(3, int(override))
        except Exception:
            pass

        jitter_factor = random.uniform(0.85, 1.15)
        next_run_delta = timedelta(minutes=base_mins * jitter_factor)
        next_run_time = datetime.now(timezone.utc) + next_run_delta
        bot_state.next_run = next_run_time

        await self.worker.run_cycle()

        if self._is_active:
            bot_state.set_idle(next_run=next_run_time)
            local_diff = datetime.now() - datetime.utcnow()
            local_next = next_run_time.replace(tzinfo=None) + local_diff
            logger.info("Цикл завершен. Следующий запуск планировщика в %s (по местному времени)", local_next.strftime("%H:%M:%S"))

    def reschedule(self, interval_mins: int) -> None:
        """Dynamically update interval trigger when settings change."""
        if not self._is_active or not self.scheduler.running:
            return
        interval_mins = max(3, interval_mins)
        try:
            self.scheduler.reschedule_job(
                self._job_id,
                trigger=IntervalTrigger(minutes=interval_mins),
            )
            logger.info("Scheduler rescheduled to new interval: %d minutes", interval_mins)
        except Exception as exc:
            logger.warning("Could not reschedule job: %s", exc)

    def start(self) -> None:
        """Start scheduler and schedule initial periodic job."""
        if self._is_active:
            logger.info("Scheduler is already active")
            return

        self._is_active = True
        prevent_sleep(True)
        self.worker.reset_stop()
        bot_state.set_running(action="Планировщик запущен, ожидание первого запуска...")

        if not self.scheduler.running:
            self.scheduler.start()

        # Add periodic interval job
        interval_mins = max(3, self.settings.search_interval_minutes)
        self.scheduler.add_job(
            self._scheduled_task_wrapper,
            trigger=IntervalTrigger(minutes=interval_mins),
            id=self._job_id,
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=2),
        )
        logger.info(
            "Scheduler started: job scheduled every ~%d minutes (±20%% jitter)", interval_mins
        )

    def trigger_now(self) -> None:
        """Manually trigger immediate execution of cycle across all active users."""
        self.worker.reset_stop()
        if not self._is_active:
            self.start()
        asyncio.create_task(self.worker.run_cycle())

    def trigger_user_now(self, user_id: int) -> None:
        """Manually trigger immediate execution for a specific user."""
        self.worker.reset_stop()
        if not self._is_active:
            self.start()

        async def _run() -> None:
            try:
                from app.db.database import get_session
                from app.db.repositories import get_user_by_id

                logger.info("Manually triggering cycle for user #%d...", user_id)
                async with get_session() as session:
                    user = await get_user_by_id(session, user_id)
                if user and user.bot_enabled and user.hh_is_connected:
                    await self.worker.run_user_cycle(user)
            except Exception as e:
                logger.error("Error executing manual cycle for user #%d: %s", user_id, e, exc_info=True)

        asyncio.create_task(_run())

    def stop(self) -> None:
        """Request immediate stop of worker and pause scheduler."""
        logger.info("Stopping scheduler service...")
        self._is_active = False
        prevent_sleep(False)
        self.worker.request_stop()

        try:
            if self.scheduler.get_job(self._job_id):
                self.scheduler.remove_job(self._job_id)
        except Exception:
            pass

        bot_state.set_stopped()
        logger.info("Scheduler service stopped")

    async def shutdown(self) -> None:
        """Gracefully shutdown scheduler and wait up to 5 seconds for tasks to exit."""
        self.stop()
        try:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=False)
        except Exception as exc:
            logger.debug("Scheduler shutdown error suppressed: %s", exc)
        logger.info("Scheduler shutdown complete")


# Global scheduler singleton
scheduler_service = SchedulerService()
