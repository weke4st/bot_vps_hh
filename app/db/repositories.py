"""Repository layer — async CRUD helpers for SaaS multi-tenancy.

Every public function accepts an ``AsyncSession`` and returns domain objects.
Callers are responsible for committing or rolling back the session.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    Application,
    ApplicationStatus,
    CaptchaAttempt,
    DailyStats,
    LLMCall,
    Setting,
    User,
    Vacancy,
    VacancyStatus,
)


# ═══════════════════════════════════════════════════════════════════════════
# User CRUD
# ═══════════════════════════════════════════════════════════════════════════


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    hashed_password: str,
    full_name: str = "",
    is_admin: bool = False,
) -> User:
    """Create a new SaaS user."""
    user = User(
        email=email.strip().lower(),
        hashed_password=hashed_password,
        full_name=full_name.strip(),
        is_admin=is_admin,
    )
    session.add(user)
    await session.flush()
    return user


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    """Fetch user by email."""
    stmt = select(User).where(User.email == email.strip().lower())
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    """Fetch user by id."""
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_active_bot_users(session: AsyncSession) -> Sequence[User]:
    """Fetch all users who have enabled the bot and connected hh.ru."""
    stmt = select(User).where(
        User.bot_enabled.is_(True),
        User.is_active.is_(True),
        User.hh_is_connected.is_(True),
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def update_user_bot_state(
    session: AsyncSession,
    user_id: int,
    *,
    bot_enabled: bool | None = None,
    bot_status: str | None = None,
    current_action: str | None = None,
    last_run_at: datetime | None = None,
    last_error: str | None = None,
) -> None:
    """Update user bot execution status."""
    values: dict[str, Any] = {}
    if bot_enabled is not None:
        values["bot_enabled"] = bot_enabled
    if bot_status is not None:
        values["bot_status"] = bot_status
    if current_action is not None:
        values["current_action"] = current_action
    if last_run_at is not None:
        values["last_run_at"] = last_run_at
    if last_error is not None:
        values["last_error"] = last_error

    if values:
        stmt = update(User).where(User.id == user_id).values(**values)
        await session.execute(stmt)


async def update_user_hh_status(
    session: AsyncSession,
    user_id: int,
    *,
    hh_is_connected: bool,
    hh_phone: str | None = None,
    selected_resume_id: str | None = None,
    selected_resume_title: str | None = None,
) -> None:
    """Update user HH connection state."""
    values: dict[str, Any] = {"hh_is_connected": hh_is_connected}
    if hh_phone is not None:
        values["hh_phone"] = hh_phone
    if selected_resume_id is not None:
        values["selected_resume_id"] = selected_resume_id
    if selected_resume_title is not None:
        values["selected_resume_title"] = selected_resume_title

    stmt = update(User).where(User.id == user_id).values(**values)
    await session.execute(stmt)


# ═══════════════════════════════════════════════════════════════════════════
# Vacancy
# ═══════════════════════════════════════════════════════════════════════════


async def get_vacancy_by_hh_id(session: AsyncSession, user_id: int, hh_id: str) -> Vacancy | None:
    """Fetch a vacancy for a user by its hh.ru identifier."""
    stmt = select(Vacancy).where(Vacancy.user_id == user_id, Vacancy.hh_id == hh_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_vacancy(
    session: AsyncSession,
    *,
    user_id: int,
    hh_id: str,
    title: str,
    company: str,
    description: str,
    url: str,
    salary: str | None = None,
) -> Vacancy:
    """Insert a new vacancy or return existing for this user."""
    existing = await get_vacancy_by_hh_id(session, user_id, hh_id)
    if existing is not None:
        return existing

    vacancy = Vacancy(
        user_id=user_id,
        hh_id=hh_id,
        title=title,
        company=company,
        description=description,
        url=url,
        salary=salary,
        status=VacancyStatus.new,
    )
    session.add(vacancy)
    await session.flush()
    return vacancy


async def list_vacancies(
    session: AsyncSession,
    *,
    user_id: int,
    status: VacancyStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Sequence[Vacancy]:
    """Return user's vacancies filtered by optional status, with pagination."""
    stmt = select(Vacancy).where(Vacancy.user_id == user_id).order_by(Vacancy.created_at.desc()).offset(offset).limit(limit)
    if status is not None:
        stmt = stmt.where(Vacancy.status == status)
    result = await session.execute(stmt)
    return result.scalars().all()


async def count_vacancies(
    session: AsyncSession, *, user_id: int, status: VacancyStatus | None = None
) -> int:
    """Count user's vacancies matching an optional status."""
    stmt = select(func.count(Vacancy.id)).where(Vacancy.user_id == user_id)
    if status is not None:
        stmt = stmt.where(Vacancy.status == status)
    result = await session.execute(stmt)
    return result.scalar_one() or 0


async def update_vacancy_status(
    session: AsyncSession, vacancy_id: int, status: VacancyStatus
) -> None:
    """Update status of a vacancy."""
    stmt = update(Vacancy).where(Vacancy.id == vacancy_id).values(status=status)
    await session.execute(stmt)


# ═══════════════════════════════════════════════════════════════════════════
# Application
# ═══════════════════════════════════════════════════════════════════════════


async def create_application(
    session: AsyncSession,
    *,
    user_id: int,
    vacancy_id: int,
    cover_letter: str | None = None,
    status: ApplicationStatus = ApplicationStatus.pending,
) -> Application:
    """Create a new job application record for a user."""
    app = Application(
        user_id=user_id,
        vacancy_id=vacancy_id,
        cover_letter=cover_letter,
        status=status,
    )
    session.add(app)
    await session.flush()
    return app


async def get_application(session: AsyncSession, app_id: int) -> Application | None:
    """Fetch an application by primary key, preloading its vacancy."""
    stmt = (
        select(Application)
        .where(Application.id == app_id)
        .options(selectinload(Application.vacancy))
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_applications(
    session: AsyncSession,
    *,
    user_id: int,
    status: ApplicationStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Sequence[Application]:
    """Return applications for user ordered by created_at desc."""
    stmt = (
        select(Application)
        .where(Application.user_id == user_id)
        .order_by(Application.created_at.desc())
        .offset(offset)
        .limit(limit)
        .options(selectinload(Application.vacancy))
    )
    if status is not None:
        stmt = stmt.where(Application.status == status)
    result = await session.execute(stmt)
    return result.scalars().all()


async def count_applications(
    session: AsyncSession, *, user_id: int, status: ApplicationStatus | None = None
) -> int:
    """Count user applications matching an optional status."""
    stmt = select(func.count(Application.id)).where(Application.user_id == user_id)
    if status is not None:
        stmt = stmt.where(Application.status == status)
    result = await session.execute(stmt)
    return result.scalar_one() or 0


async def get_application_detail(
    session: AsyncSession, application_id: int, user_id: int | None = None
) -> Application | None:
    """Fetch a single application by ID with related objects loaded."""
    stmt = (
        select(Application)
        .options(
            selectinload(Application.vacancy),
            selectinload(Application.captcha_attempts),
            selectinload(Application.llm_calls),
        )
        .where(Application.id == application_id)
    )
    if user_id is not None:
        stmt = stmt.where(Application.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def reset_application_for_retry(
    session: AsyncSession, application_id: int, user_id: int | None = None
) -> Application | None:
    """Reset an application back to pending status for retry."""
    app = await get_application_detail(session, application_id, user_id)
    if app is None:
        return None
    app.status = ApplicationStatus.pending
    app.sent_at = None
    app.vacancy.status = VacancyStatus.new
    return app


async def reset_user_manual_vacancies(
    session: AsyncSession, user_id: int
) -> int:
    """Reset all vacancies with status 'manual' back to 'new' for this user."""
    stmt = (
        update(Vacancy)
        .where(Vacancy.user_id == user_id, Vacancy.status == VacancyStatus.manual)
        .values(status=VacancyStatus.new)
    )
    result = await session.execute(stmt)
    stmt_app = (
        delete(Application)
        .where(Application.user_id == user_id, Application.status == ApplicationStatus.manual)
    )
    await session.execute(stmt_app)
    return result.rowcount or 0


async def count_applications_since(
    session: AsyncSession, user_id: int, since: datetime
) -> int:
    """Count user applications submitted since a given datetime."""
    stmt = select(func.count(Application.id)).where(
        Application.user_id == user_id,
        Application.sent_at >= since,
        Application.status == ApplicationStatus.sent,
    )
    result = await session.execute(stmt)
    return result.scalar_one() or 0


async def update_application_status(
    session: AsyncSession,
    app_id: int,
    status: ApplicationStatus,
    *,
    sent_at: datetime | None = None,
    response_at: datetime | None = None,
    response_type: str | None = None,
) -> None:
    """Update status and timestamps of an application."""
    values: dict[str, Any] = {"status": status}
    if sent_at is not None:
        values["sent_at"] = sent_at
    if response_at is not None:
        values["response_at"] = response_at
    if response_type is not None:
        values["response_type"] = response_type

    stmt = update(Application).where(Application.id == app_id).values(**values)
    await session.execute(stmt)


# ═══════════════════════════════════════════════════════════════════════════
# CaptchaAttempt
# ═══════════════════════════════════════════════════════════════════════════


async def create_captcha_attempt(
    session: AsyncSession,
    *,
    application_id: int,
    image_path: str,
    model_answer: str | None = None,
    correct: bool | None = None,
) -> CaptchaAttempt:
    """Record a CAPTCHA solve attempt."""
    attempt = CaptchaAttempt(
        application_id=application_id,
        image_path=image_path,
        model_answer=model_answer,
        correct=correct,
    )
    session.add(attempt)
    await session.flush()
    return attempt


# ═══════════════════════════════════════════════════════════════════════════
# Settings
# ═══════════════════════════════════════════════════════════════════════════


async def get_setting(
    session: AsyncSession,
    user_id_or_key: int | str,
    key: str | None = None,
    default: str | None = None,
) -> str | None:
    """Fetch setting value for user or system global if user_id omitted."""
    if key is None:
        actual_key = str(user_id_or_key)
        stmt = select(Setting.value).where(Setting.key == actual_key, Setting.user_id.is_(None))
    else:
        actual_user_id = int(user_id_or_key)
        stmt = select(Setting.value).where(Setting.user_id == actual_user_id, Setting.key == key)
    result = await session.execute(stmt)
    val = result.scalar_one_or_none()
    return val if val is not None else default


async def set_setting(
    session: AsyncSession,
    user_id_or_key: int | str,
    key_or_val: str,
    value: str | None = None,
) -> None:
    """Upsert setting value for user or system global."""
    if value is None:
        actual_key = str(user_id_or_key)
        actual_val = key_or_val
        stmt = select(Setting).where(Setting.key == actual_key, Setting.user_id.is_(None))
        result = await session.execute(stmt)
        setting = result.scalar_one_or_none()
        if setting is None:
            setting = Setting(user_id=None, key=actual_key, value=actual_val)
            session.add(setting)
        else:
            setting.value = actual_val
    else:
        actual_user_id = int(user_id_or_key)
        actual_key = key_or_val
        stmt = select(Setting).where(Setting.user_id == actual_user_id, Setting.key == actual_key)
        result = await session.execute(stmt)
        setting = result.scalar_one_or_none()
        if setting is None:
            setting = Setting(user_id=actual_user_id, key=actual_key, value=value)
            session.add(setting)
        else:
            setting.value = value
    await session.flush()


async def get_all_settings(session: AsyncSession, user_id: int | None = None) -> dict[str, str]:
    """Fetch all settings for a user (or system globals) as dict."""
    if user_id is None:
        stmt = select(Setting).where(Setting.user_id.is_(None))
    else:
        stmt = select(Setting).where(Setting.user_id == user_id)
    result = await session.execute(stmt)
    return {s.key: s.value for s in result.scalars()}


# ═══════════════════════════════════════════════════════════════════════════
# DailyStats
# ═══════════════════════════════════════════════════════════════════════════


async def upsert_daily_stats(
    session: AsyncSession,
    *,
    user_id: int,
    target_date: date | None = None,
    applications_delta: int = 0,
    responses_delta: int = 0,
    interviews_delta: int = 0,
) -> DailyStats:
    """Increment counters for user on given date."""
    d = target_date or datetime.now(timezone.utc).date()
    stmt = select(DailyStats).where(DailyStats.user_id == user_id, DailyStats.date == d)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()

    if row is None:
        row = DailyStats(
            user_id=user_id,
            date=d,
            applications_count=max(0, applications_delta),
            responses_count=max(0, responses_delta),
            interviews_count=max(0, interviews_delta),
        )
        session.add(row)
    else:
        row.applications_count += applications_delta
        row.responses_count += responses_delta
        row.interviews_count += interviews_delta

    await session.flush()
    return row


async def get_recent_daily_stats(
    session: AsyncSession, *, user_id: int, days: int = 14
) -> Sequence[DailyStats]:
    """Return user daily stats for last N days."""
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=days)
    stmt = (
        select(DailyStats)
        .where(DailyStats.user_id == user_id, DailyStats.date >= cutoff)
        .order_by(DailyStats.date.asc())
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_total_stats(session: AsyncSession, user_id: int) -> dict[str, int]:
    """Return aggregated stats for user dashboard."""
    total_apps = await count_applications(session, user_id=user_id, status=ApplicationStatus.sent)
    total_responses = await count_applications(session, user_id=user_id, status=ApplicationStatus.response)
    total_interviews = await count_applications(session, user_id=user_id, status=ApplicationStatus.interview)
    total_pending = await count_applications(session, user_id=user_id, status=ApplicationStatus.pending)
    total_manual = await count_applications(session, user_id=user_id, status=ApplicationStatus.manual)

    return {
        "sent": total_apps,
        "responses": total_responses,
        "interviews": total_interviews,
        "pending": total_pending,
        "manual": total_manual,
    }


# ═══════════════════════════════════════════════════════════════════════════
# LLMCall
# ═══════════════════════════════════════════════════════════════════════════


async def log_llm_call(
    session: AsyncSession,
    *,
    application_id: int | None = None,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
) -> LLMCall:
    """Record an LLM API call."""
    record = LLMCall(
        application_id=application_id,
        provider=provider,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
    )
    session.add(record)
    await session.flush()
    return record


# Compatibility alias
create_llm_call = log_llm_call

