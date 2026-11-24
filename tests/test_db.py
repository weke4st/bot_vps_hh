"""Smoke tests for database models and repository layer."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import (
    Application,
    ApplicationStatus,
    Base,
    CaptchaAttempt,
    DailyStats,
    LLMCall,
    Setting,
    Vacancy,
    VacancyStatus,
)
from app.db.repositories import (
    count_applications_since,
    create_application,
    create_captcha_attempt,
    create_llm_call,
    get_all_settings,
    get_daily_stats,
    get_setting,
    get_stats_summary,
    get_vacancy_by_hh_id,
    list_applications,
    list_vacancies,
    set_setting,
    update_application_status,
    update_vacancy_status,
    upsert_daily_stats,
    upsert_vacancy,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def engine():
    """Create an in-memory SQLite engine for testing."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine) -> AsyncSession:
    """Provide a fresh async session."""
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess


# ---------------------------------------------------------------------------
# Tests: Vacancy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_vacancy_creates_new(session: AsyncSession) -> None:
    """First upsert should create a new vacancy."""
    v = await upsert_vacancy(
        session,
        hh_id="12345",
        title="Python Developer",
        company="ACME Corp",
        description="We need a dev",
        url="https://hh.ru/vacancy/12345",
        salary="200 000 руб.",
    )
    await session.commit()

    assert v.id is not None
    assert v.hh_id == "12345"
    assert v.status == VacancyStatus.new


@pytest.mark.asyncio
async def test_upsert_vacancy_returns_existing(session: AsyncSession) -> None:
    """Second upsert with the same hh_id should return the existing record."""
    v1 = await upsert_vacancy(
        session, hh_id="99", title="T1", company="C1", description="D1", url="https://hh.ru/99"
    )
    await session.commit()

    v2 = await upsert_vacancy(
        session, hh_id="99", title="T2", company="C2", description="D2", url="https://hh.ru/99"
    )
    assert v2.id == v1.id
    assert v2.title == "T1"  # original title preserved


@pytest.mark.asyncio
async def test_update_vacancy_status(session: AsyncSession) -> None:
    v = await upsert_vacancy(
        session, hh_id="50", title="T", company="C", description="D", url="u"
    )
    await session.commit()

    await update_vacancy_status(session, v.id, VacancyStatus.applied)
    await session.commit()

    fetched = await get_vacancy_by_hh_id(session, "50")
    assert fetched is not None
    assert fetched.status == VacancyStatus.applied


@pytest.mark.asyncio
async def test_list_vacancies_with_filter(session: AsyncSession) -> None:
    await upsert_vacancy(session, hh_id="1", title="A", company="C", description="D", url="u")
    v2 = await upsert_vacancy(session, hh_id="2", title="B", company="C", description="D", url="u")
    await session.commit()
    await update_vacancy_status(session, v2.id, VacancyStatus.applied)
    await session.commit()

    all_v = await list_vacancies(session)
    assert len(all_v) == 2

    applied = await list_vacancies(session, status=VacancyStatus.applied)
    assert len(applied) == 1
    assert applied[0].hh_id == "2"


# ---------------------------------------------------------------------------
# Tests: Application
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_update_application(session: AsyncSession) -> None:
    v = await upsert_vacancy(session, hh_id="A1", title="T", company="C", description="D", url="u")
    await session.commit()

    app = await create_application(session, vacancy_id=v.id, cover_letter="Hello!")
    await session.commit()

    assert app.status == ApplicationStatus.pending

    now = datetime.now(tz=timezone.utc)
    await update_application_status(session, app.id, ApplicationStatus.sent, sent_at=now)
    await session.commit()


@pytest.mark.asyncio
async def test_count_applications_since(session: AsyncSession) -> None:
    v = await upsert_vacancy(session, hh_id="C1", title="T", company="C", description="D", url="u")
    await session.commit()

    app = await create_application(session, vacancy_id=v.id)
    now = datetime.now(tz=timezone.utc)
    await update_application_status(session, app.id, ApplicationStatus.sent, sent_at=now)
    await session.commit()

    count = await count_applications_since(session, now.replace(hour=0, minute=0, second=0))
    assert count >= 1


# ---------------------------------------------------------------------------
# Tests: Setting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_setting_crud(session: AsyncSession) -> None:
    await set_setting(session, "max_per_hour", "25")
    await session.commit()

    val = await get_setting(session, "max_per_hour")
    assert val == "25"

    await set_setting(session, "max_per_hour", "30")
    await session.commit()

    val = await get_setting(session, "max_per_hour")
    assert val == "30"

    all_s = await get_all_settings(session)
    assert "max_per_hour" in all_s


# ---------------------------------------------------------------------------
# Tests: DailyStats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_daily_stats_upsert(session: AsyncSession) -> None:
    today = date.today()
    s1 = await upsert_daily_stats(session, target_date=today, applications_delta=5)
    await session.commit()
    assert s1.applications_count == 5

    s2 = await upsert_daily_stats(session, target_date=today, applications_delta=3)
    await session.commit()
    assert s2.applications_count == 8

    stats = await get_daily_stats(session, days=7)
    assert len(stats) >= 1


# ---------------------------------------------------------------------------
# Tests: LLMCall
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_llm_call(session: AsyncSession) -> None:
    call = await create_llm_call(
        session,
        provider="gigachat",
        model="GigaChat",
        prompt_tokens=100,
        completion_tokens=50,
        latency_ms=350,
    )
    await session.commit()
    assert call.id is not None
    assert call.provider == "gigachat"
