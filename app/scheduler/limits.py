"""Rate limiting checks for applications per hour and per day."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.repositories import count_applications_since, get_setting

logger = logging.getLogger(__name__)


class RateLimiter:
    """Enforces hourly and daily maximum application limits."""

    def __init__(self) -> None:
        self.settings = get_settings()

    async def can_apply(self, session: AsyncSession, user_id: int = 1) -> tuple[bool, str]:
        """Check whether the user is allowed to submit another application right now.

        Returns:
            (allowed: bool, reason: str)
        """
        # Load active limits (DB override takes precedence over .env)
        max_hour_str = await get_setting(session, user_id, "max_applications_per_hour")
        max_hour = (
            int(max_hour_str)
            if max_hour_str is not None
            else self.settings.max_applications_per_hour
        )

        max_day_str = await get_setting(session, user_id, "max_applications_per_day")
        max_day = (
            int(max_day_str)
            if max_day_str is not None
            else self.settings.max_applications_per_day
        )

        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)
        today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # 1. Check hourly limit
        count_hour = await count_applications_since(session, user_id, one_hour_ago)
        if count_hour >= max_hour:
            from sqlalchemy import select
            from app.db.models import Application, ApplicationStatus

            stmt = (
                select(Application.sent_at)
                .where(
                    Application.user_id == user_id,
                    Application.sent_at >= one_hour_ago,
                    Application.status == ApplicationStatus.sent,
                )
                .order_by(Application.sent_at.asc())
                .limit(1)
            )
            earliest_sent = (await session.execute(stmt)).scalar_one_or_none()
            if earliest_sent is not None:
                slot_time = earliest_sent + timedelta(hours=1)
                local_diff = datetime.now() - datetime.utcnow()
                local_slot = slot_time if slot_time.tzinfo else (slot_time + local_diff)
                mins_left = max(1, int((slot_time.timestamp() - now.timestamp()) / 60))
                time_str = local_slot.strftime("%H:%M")
                reason = (
                    f"Лимит откликов в час достигнут ({count_hour}/{max_hour} за 60 мин). "
                    f"Следующий отклик станет доступен в {time_str} (через ~{mins_left} мин)."
                )
            else:
                reason = f"Лимит откликов в час достигнут ({count_hour}/{max_hour} за 60 мин)."

            logger.warning(reason)
            return False, reason

        # 2. Check daily limit
        count_today = await count_applications_since(session, user_id, today_midnight)
        if count_today >= max_day:
            reason = f"Суточный лимит откликов достигнут ({count_today}/{max_day} сегодня). Сброс в полночь."
            logger.warning(reason)
            return False, reason

        return True, "Limits OK"
