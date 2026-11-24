"""Unit tests for scheduler rate limiting and service lifecycle."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Application, ApplicationStatus, Base, Vacancy
from app.db.repositories import set_setting
from app.scheduler.limits import RateLimiter
from app.scheduler.service import SchedulerService


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_rate_limiter_allows_initial(session_factory) -> None:
    limiter = RateLimiter()
    async with session_factory() as session:
        allowed, reason = await limiter.can_apply(session)
        assert allowed is True
        assert "OK" in reason


@pytest.mark.asyncio
async def test_rate_limiter_blocks_hourly_limit(session_factory) -> None:
    limiter = RateLimiter()
    async with session_factory() as session:
        # Set limit to 2
        await set_setting(session, "max_applications_per_hour", "2")

        v = Vacancy(
            hh_id="test_lim", title="Dev", company="Comp", description="Desc", url="http://hh"
        )
        session.add(v)
        await session.flush()

        # Add 2 sent applications in the last 10 minutes
        now = datetime.now(timezone.utc)
        session.add(
            Application(
                vacancy_id=v.id,
                status=ApplicationStatus.sent,
                sent_at=now - timedelta(minutes=5),
            )
        )
        session.add(
            Application(
                vacancy_id=v.id,
                status=ApplicationStatus.sent,
                sent_at=now - timedelta(minutes=2),
            )
        )
        await session.commit()

        allowed, reason = await limiter.can_apply(session)
        assert allowed is False
        assert "Hourly limit reached" in reason


@pytest.mark.asyncio
async def test_scheduler_service_lifecycle() -> None:
    service = SchedulerService()
    assert not service.is_active()

    service.start()
    assert service.is_active()

    service.stop()
    assert not service.is_active()
    await service.shutdown()
