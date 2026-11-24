"""FastAPI route handlers for SaaS multi-tenancy, authentication, HH login, dashboard, and WebSockets."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.security import (
    create_access_token,
    decode_access_token,
    get_current_user,
    get_optional_user,
    hash_password,
    verify_password,
)
from app.api.schemas import (
    ApplicationDetail,
    ApplicationListItem,
    ApplicationPagination,
    AuthTokenResponse,
    BotStatusResponse,
    CaptchaAttemptItem,
    CompanyStatPoint,
    DailyStatPoint,
    HHLoginResponse,
    HHLoginStartRequest,
    HHLoginVerifyRequest,
    LLMCallItem,
    LogsResponse,
    ResumeResponse,
    ResumeUpdateRequest,
    SettingsResponse,
    SettingsUpdateRequest,
    StandardResponse,
    StatsSummaryResponse,
    UserCredentialsUpdateRequest,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
    VacancySummary,
)
from app.api.state import bot_state, ws_manager
from app.config import get_settings
from app.db.database import get_session, get_session_dep
from app.db.models import Application, ApplicationStatus, DailyStats, User, Vacancy, VacancyStatus
from app.db.repositories import (
    count_applications,
    create_user,
    get_all_settings,
    get_recent_daily_stats,
    get_setting,
    get_total_stats,
    get_user_by_email,
    get_user_by_id,
    list_applications,
    list_vacancies,
    set_setting,
    update_user_bot_state,
    update_user_hh_status,
    upsert_vacancy,
)
from app.hh.web_login import cancel_hh_login, start_hh_login, verify_hh_code
from app.scheduler.service import scheduler_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api"])


def _mask_secret(val: str | None, show_chars: int = 4) -> str:
    """Mask sensitive string leaving only trailing characters."""
    if not val:
        return ""
    if len(val) <= show_chars:
        return "***"
    return f"***{val[-show_chars:]}"


def _user_to_response(user: User) -> UserResponse:
    """Helper to convert ORM User to UserResponse."""
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        hh_phone=user.hh_phone,
        hh_is_connected=user.hh_is_connected,
        selected_resume_id=user.selected_resume_id,
        selected_resume_title=user.selected_resume_title,
        bot_enabled=user.bot_enabled,
        bot_status=user.bot_status,
        current_action=user.current_action,
        search_query=user.search_query,
        search_region=user.search_region,
        target_salary=user.target_salary,
        proxy_url=_mask_secret(user.proxy_url, 6) if user.proxy_url else None,
        gigachat_auth_key_masked=_mask_secret(user.gigachat_auth_key),
        last_run_at=user.last_run_at,
        created_at=user.created_at,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. SaaS Authentication (Register / Login / Me)
# ═══════════════════════════════════════════════════════════════════════════


@router.post(
    "/auth/register",
    response_model=AuthTokenResponse,
    summary="Register a new user on the SaaS platform",
)
async def register(
    payload: UserRegisterRequest,
    response: Response,
    session: AsyncSession = Depends(get_session_dep),
) -> AuthTokenResponse:
    """Register a new user, return JWT and set auth cookie."""
    existing = await get_user_by_email(session, payload.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пользователь с таким email уже зарегистрирован",
        )

    # First user is admin automatically
    count_stmt = select(func.count(User.id))
    user_count = (await session.execute(count_stmt)).scalar_one() or 0
    is_admin = user_count == 0

    hashed_pw = hash_password(payload.password)
    user = await create_user(
        session,
        email=payload.email,
        hashed_password=hashed_pw,
        full_name=payload.full_name,
        is_admin=is_admin,
    )
    await session.commit()
    await session.refresh(user)

    token = create_access_token({"sub": str(user.id), "email": user.email})
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=30 * 24 * 3600,
        samesite="lax",
    )

    logger.info("New user registered: #%d (%s)", user.id, user.email)
    return AuthTokenResponse(
        access_token=token,
        user=_user_to_response(user),
    )


@router.post(
    "/auth/login",
    response_model=AuthTokenResponse,
    summary="Log in with email and password",
)
async def login(
    payload: UserLoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session_dep),
) -> AuthTokenResponse:
    """Verify credentials and issue JWT token."""
    user = await get_user_by_email(session, payload.email)
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Аккаунт заблокирован",
        )

    token = create_access_token({"sub": str(user.id), "email": user.email})
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=30 * 24 * 3600,
        samesite="lax",
    )

    logger.info("User logged in: #%d (%s)", user.id, user.email)
    return AuthTokenResponse(
        access_token=token,
        user=_user_to_response(user),
    )


@router.get(
    "/auth/me",
    response_model=UserResponse,
    summary="Get current logged in user profile",
)
async def get_me(user: User = Depends(get_current_user)) -> UserResponse:
    """Return profile of the current authenticated user."""
    return _user_to_response(user)


@router.post(
    "/auth/logout",
    response_model=StandardResponse,
    summary="Log out and clear session cookie",
)
async def logout(response: Response) -> StandardResponse:
    """Clear access_token cookie."""
    response.delete_cookie("access_token")
    return StandardResponse(success=True, message="Вы успешно вышли")


# ═══════════════════════════════════════════════════════════════════════════
# 2. HH.ru Web Login Wizard (Phone -> SMS Code)
# ═══════════════════════════════════════════════════════════════════════════


@router.post(
    "/hh/login/start",
    response_model=HHLoginResponse,
    summary="Initiate HH.ru login: enter phone and request SMS code",
)
async def hh_login_start(
    payload: HHLoginStartRequest,
    user: User = Depends(get_current_user),
) -> HHLoginResponse:
    """Spawn browser session and send SMS verification code."""
    res = await start_hh_login(
        user_id=user.id,
        phone=payload.phone,
        proxy_url=payload.proxy_url or user.proxy_url,
    )
    return HHLoginResponse(
        status=res.get("status", "code_sent"),
        message=res.get("message", "СМС отправлено"),
    )


@router.post(
    "/hh/login/verify",
    response_model=HHLoginResponse,
    summary="Verify SMS code and link HH.ru account",
)
async def hh_login_verify(
    payload: HHLoginVerifyRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dep),
) -> HHLoginResponse:
    """Verify SMS code, store session cookies, and extract user resumes."""
    res = await verify_hh_code(user_id=user.id, code=payload.code)

    if res.get("status") == "success":
        resumes = res.get("resumes", [])
        sel_id = resumes[0]["id"] if resumes else None
        sel_title = resumes[0]["title"] if resumes else None

        await update_user_hh_status(
            session,
            user.id,
            hh_is_connected=True,
            selected_resume_id=sel_id,
            selected_resume_title=sel_title,
        )
        await session.commit()

    return HHLoginResponse(
        status=res.get("status", "error"),
        message=res.get("message", ""),
        resumes=res.get("resumes", []),
    )


@router.post(
    "/hh/login/cancel",
    response_model=StandardResponse,
    summary="Cancel pending HH.ru login session",
)
async def hh_login_cancel(user: User = Depends(get_current_user)) -> StandardResponse:
    """Close and cancel pending login browser session."""
    await cancel_hh_login(user.id)
    return StandardResponse(success=True, message="Сессия авторизации отменена")


# ═══════════════════════════════════════════════════════════════════════════
# 3. User Settings & Bot Controls
# ═══════════════════════════════════════════════════════════════════════════


@router.get(
    "/user/settings",
    response_model=UserResponse,
    summary="Get user-specific settings and credentials",
)
@router.get(
    "/settings",
    response_model=UserResponse,
    summary="Get user-specific settings (alias)",
)
async def get_user_settings(user: User = Depends(get_current_user)) -> UserResponse:
    """Return user configuration."""
    return _user_to_response(user)


@router.post(
    "/user/settings",
    response_model=UserResponse,
    summary="Update personal GigaChat key, proxy, search filters, and resume",
)
async def update_user_settings(
    payload: UserCredentialsUpdateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dep),
) -> UserResponse:
    """Save user-specific configurations."""
    values: dict[str, Any] = {}

    if payload.gigachat_auth_key is not None and payload.gigachat_auth_key.strip():
        values["gigachat_auth_key"] = payload.gigachat_auth_key.strip()
    if payload.gigachat_scope is not None:
        values["gigachat_scope"] = payload.gigachat_scope.strip()
    if payload.proxy_url is not None:
        values["proxy_url"] = payload.proxy_url.strip() or None
    if payload.search_query is not None:
        values["search_query"] = payload.search_query.strip()
    if payload.search_region is not None:
        values["search_region"] = payload.search_region
    if payload.target_salary is not None:
        values["target_salary"] = payload.target_salary.strip()
    if payload.selected_resume_id is not None:
        values["selected_resume_id"] = payload.selected_resume_id.strip()
    if payload.selected_resume_title is not None:
        values["selected_resume_title"] = payload.selected_resume_title.strip()

    if values:
        stmt = update(User).where(User.id == user.id).values(**values)
        await session.execute(stmt)
        await session.commit()
        await session.refresh(user)

    logger.info("User #%d settings updated", user.id)
    return _user_to_response(user)


@router.post(
    "/user/bot/toggle",
    response_model=StandardResponse,
    summary="Toggle bot running status (on/off) for current user",
)
async def toggle_user_bot(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dep),
) -> StandardResponse:
    """Toggle user bot execution."""
    if not user.hh_is_connected and not user.bot_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Сначала подключите аккаунт hh.ru через веб-форму",
        )

    settings = get_settings()
    has_key = bool(
        (user.gigachat_auth_key and user.gigachat_auth_key.strip())
        or (settings.gigachat_auth_key and settings.gigachat_auth_key.get_secret_value())
    )
    if not has_key and not user.bot_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Укажите ваш личный GigaChat Authorization Key в разделе 'Настройки' перед запуском бота",
        )

    new_state = not user.bot_enabled
    new_status = "idle" if new_state else "stopped"
    action = "Ожидание запуска" if new_state else "Остановлен"

    await update_user_bot_state(
        session,
        user.id,
        bot_enabled=new_state,
        bot_status=new_status,
        current_action=action,
    )
    await session.commit()

    if new_state:
        # Trigger immediate cycle for this user so they don't wait for the next periodic tick
        scheduler_service.trigger_user_now(user.id)

    logger.info("User #%d bot toggled: enabled=%s", user.id, new_state)
    return StandardResponse(
        success=True,
        message="Бот запущен" if new_state else "Бот остановлен",
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4. User Dashboard Stats & Applications
# ═══════════════════════════════════════════════════════════════════════════


@router.get(
    "/user/stats",
    response_model=StatsSummaryResponse,
    summary="Get personal stats for the authenticated user",
)
@router.get(
    "/stats",
    response_model=StatsSummaryResponse,
    summary="Get personal stats (alias)",
)
async def get_user_stats(
    period: Annotated[Literal["7d", "30d", "all"], Query()] = "7d",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dep),
) -> StatsSummaryResponse:
    """Return period summary and timeline for current user."""
    days = 30 if period == "30d" else (90 if period == "all" else 7)

    daily_rows = await get_recent_daily_stats(session, user_id=user.id, days=days)
    timeline = [
        DailyStatPoint(
            date=row.date.strftime("%Y-%m-%d"),
            applications=row.applications_count,
            responses=row.responses_count,
            interviews=row.interviews_count,
        )
        for row in daily_rows
    ]

    total_stats = await get_total_stats(session, user_id=user.id)
    total_apps = total_stats["sent"]
    total_resp = total_stats["responses"]
    total_intv = total_stats["interviews"]

    resp_rate = round((total_resp / total_apps * 100), 1) if total_apps > 0 else 0.0
    intv_rate = round((total_intv / total_apps * 100), 1) if total_apps > 0 else 0.0

    today_date = datetime.now(timezone.utc).date()
    today_stats = next((r for r in daily_rows if r.date == today_date), None)
    today_apps = today_stats.applications_count if today_stats else 0

    return StatsSummaryResponse(
        period=period,
        total_applications=total_apps,
        today_applications=today_apps,
        total_responses=total_resp,
        total_interviews=total_intv,
        response_rate_pct=resp_rate,
        interview_rate_pct=intv_rate,
        timeline=timeline,
        status_distribution={
            "sent": total_apps,
            "response": total_resp,
            "interview": total_intv,
            "pending": total_stats["pending"],
            "manual": total_stats["manual"],
        },
        top_companies=[],
    )


@router.get(
    "/user/applications",
    response_model=ApplicationPagination,
    summary="Get user's job applications list",
)
@router.get(
    "/applications",
    response_model=ApplicationPagination,
    summary="Get user's job applications list (alias)",
)
async def get_user_applications(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    status: ApplicationStatus | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dep),
) -> ApplicationPagination:
    """Return paginated list of user applications."""
    offset = (page - 1) * limit
    apps = await list_applications(session, user_id=user.id, status=status, limit=limit, offset=offset)
    total = await count_applications(session, user_id=user.id, status=status)

    items = [
        ApplicationListItem(
            id=a.id,
            vacancy_id=a.vacancy_id,
            vacancy=VacancySummary(
                id=a.vacancy.id,
                hh_id=a.vacancy.hh_id,
                title=a.vacancy.title,
                company=a.vacancy.company,
                salary=a.vacancy.salary,
                url=a.vacancy.url,
                status=a.vacancy.status.value,
                description=a.vacancy.description[:200] if a.vacancy.description else None,
            )
            if a.vacancy
            else None,
            status=a.status.value,
            cover_letter_preview=a.cover_letter[:150] if a.cover_letter else None,
            sent_at=a.sent_at,
            response_at=a.response_at,
            response_type=a.response_type,
            created_at=a.created_at,
        )
        for a in apps
    ]

    pages = (total + limit - 1) // limit if total > 0 else 1
    return ApplicationPagination(items=items, total=total, page=page, limit=limit, pages=pages)


@router.post(
    "/user/vacancies/reset",
    response_model=StandardResponse,
    summary="Reset manual vacancies back to 'new' for retry",
)
async def reset_user_vacancies(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dep),
) -> StandardResponse:
    """Reset manual vacancies and delete failed applications for current user."""
    stmt_vac = (
        update(Vacancy)
        .where(Vacancy.user_id == user.id, Vacancy.status == VacancyStatus.manual)
        .values(status=VacancyStatus.new)
    )
    res_vac = await session.execute(stmt_vac)

    stmt_app = delete(Application).where(
        Application.user_id == user.id, Application.status == ApplicationStatus.manual
    )
    res_app = await session.execute(stmt_app)

    await set_setting(session, user.id, "search_current_page", "0")
    await session.commit()

    return StandardResponse(
        success=True,
        message=f"Сброшено {res_vac.rowcount} вакансий со статусом 'manual' обратно в 'new'.",
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4. Resume Management
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/resume", response_model=ResumeResponse, summary="Get candidate resume text")
async def get_resume(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dep),
) -> ResumeResponse:
    """Retrieve candidate resume stored in database settings for current user."""
    text = await get_setting(session, user.id, "resume_text")
    if not text:
        text = await get_setting(session, "resume_text") or ""
    updated = await get_setting(session, user.id, "resume_updated_at")
    return ResumeResponse(text=text, updated_at=updated)


@router.put("/resume", response_model=StandardResponse, summary="Update candidate resume text")
async def update_resume(
    payload: ResumeUpdateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dep),
) -> StandardResponse:
    """Save candidate resume text for current user."""
    await set_setting(session, user.id, "resume_text", payload.text)
    await set_setting(
        session, user.id, "resume_updated_at", datetime.now(timezone.utc).isoformat()
    )
    await session.commit()
    logger.info("Resume text updated for user #%d (%d characters)", user.id, len(payload.text))
    return StandardResponse(message="Резюме успешно сохранено")


# ═══════════════════════════════════════════════════════════════════════════
# 5. Backward Compatibility & System Endpoints
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/bot/status", response_model=BotStatusResponse)
async def get_bot_status(
    user: User | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_session_dep),
) -> BotStatusResponse:
    """Return bot status for current user (or global status)."""
    if user:
        return BotStatusResponse(
            status=user.bot_status if user.bot_enabled else "stopped",
            is_running=user.bot_enabled,
            current_action=user.current_action,
            current_vacancy=None,
            uptime_seconds=0,
            last_run=user.last_run_at,
            next_run=None,
            applications_today=0,
            applications_this_hour=0,
            limits={},
            error_message=user.last_error,
        )

    # Fallback to system state
    s = bot_state.snapshot()
    return BotStatusResponse(
        status=s.status,
        is_running=s.is_running,
        current_action=s.current_action,
        current_vacancy=s.current_vacancy,
        uptime_seconds=s.uptime_seconds,
        last_run=s.last_run,
        next_run=s.next_run,
        applications_today=s.applications_today,
        applications_this_hour=s.applications_this_hour,
        limits=s.limits,
        error_message=s.error_message,
    )


@router.get("/logs", response_model=LogsResponse)
async def get_logs(limit: int = 100) -> LogsResponse:
    """Fetch recent system logs."""
    all_logs = bot_state.logs
    slice_logs = all_logs[-limit:] if limit < len(all_logs) else all_logs
    return LogsResponse(logs=slice_logs, total=len(all_logs))


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    """Real-time updates WebSocket endpoint."""
    await ws_manager.connect(websocket)
    try:
        # Send initial bot status snapshot
        await websocket.send_json(
            {"type": "bot_status", "data": bot_state.snapshot().model_dump(mode="json")}
        )
        while True:
            try:
                # 20-second keepalive to prevent idle disconnects across firewalls / browsers
                await asyncio.wait_for(websocket.receive_text(), timeout=20.0)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
    except (WebSocketDisconnect, Exception):
        ws_manager.disconnect(websocket)
