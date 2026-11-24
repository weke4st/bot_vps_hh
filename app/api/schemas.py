"""Pydantic v2 schemas for HH Auto-Apply Bot REST API and WebSockets."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Common / Generic
# ---------------------------------------------------------------------------


class StandardResponse(BaseModel):
    """Simple standard response envelope."""

    success: bool = True
    message: str = "ok"


# ---------------------------------------------------------------------------
# SaaS Multi-Tenancy & Auth Schemas
# ---------------------------------------------------------------------------


class UserRegisterRequest(BaseModel):
    """User registration / access request payload."""

    email: str
    password: str = Field(min_length=6)
    full_name: str = ""
    note: str = Field(default="", max_length=500)


class UserLoginRequest(BaseModel):
    """User login payload."""

    email: str
    password: str


class UserResponse(BaseModel):
    """Public user profile."""

    id: int
    email: str
    full_name: str
    is_active: bool = True
    is_admin: bool = False
    approval_status: str = "approved"
    hh_phone: str | None = None
    hh_is_connected: bool = False
    selected_resume_id: str | None = None
    selected_resume_title: str | None = None
    bot_enabled: bool = False
    bot_status: str = "stopped"
    current_action: str = "Ожидание"
    search_query: str = "DevOps"
    search_region: int = 1
    target_salary: str = "180000"
    proxy_url: str | None = None
    gigachat_auth_key_masked: str = ""
    last_run_at: datetime | None = None
    created_at: datetime


class AuthTokenResponse(BaseModel):
    """JWT Token response upon login."""

    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class RegisterResponse(BaseModel):
    """Response from /auth/register (either immediate bootstrap admin or pending approval)."""

    status: Literal["approved", "pending"]
    message: str
    access_token: str | None = None
    token_type: str = "bearer"
    user: UserResponse | None = None


class AuthConfigResponse(BaseModel):
    """Public authentication configuration (mode of registration)."""

    registration_mode: Literal["first_admin", "request", "closed"]


class HHLoginStartRequest(BaseModel):
    """Start HH.ru login wizard payload."""

    phone: str
    proxy_url: str | None = None


class HHLoginVerifyRequest(BaseModel):
    """Verify SMS code payload."""

    code: str


class HHLoginResponse(BaseModel):
    """Response from HH.ru login wizard."""

    status: str
    message: str
    resumes: list[dict[str, Any]] = Field(default_factory=list)


class UserCredentialsUpdateRequest(BaseModel):
    """Payload to update personal user settings and GigaChat credentials."""

    gigachat_auth_key: str | None = None
    gigachat_scope: str | None = None
    proxy_url: str | None = None
    search_query: str | None = None
    search_region: int | None = None
    target_salary: str | None = None
    selected_resume_id: str | None = None
    selected_resume_title: str | None = None


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class DailyStatPoint(BaseModel):
    """Daily data point for Recharts timeline."""

    date: str
    applications: int
    responses: int
    interviews: int


class CompanyStatPoint(BaseModel):
    """Top employer data point for Recharts bar chart."""

    company: str
    count: int


class StatsSummaryResponse(BaseModel):
    """Aggregated stats payload for dashboard cards & charts."""

    period: str
    total_applications: int
    today_applications: int
    total_responses: int
    total_interviews: int
    response_rate_pct: float
    interview_rate_pct: float
    timeline: list[DailyStatPoint]
    status_distribution: dict[str, int]
    top_companies: list[CompanyStatPoint]


# ---------------------------------------------------------------------------
# Vacancy & Application
# ---------------------------------------------------------------------------


class VacancySummary(BaseModel):
    """Condensed vacancy details."""

    id: int
    hh_id: str
    title: str
    company: str
    salary: str | None = None
    url: str
    status: str
    description: str | None = None


class CaptchaAttemptItem(BaseModel):
    """Log record of a single captcha solving attempt."""

    id: int
    image_path: str
    model_answer: str | None = None
    correct: bool | None = None
    created_at: datetime


class LLMCallItem(BaseModel):
    """Log record of an LLM call."""

    id: int
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    created_at: datetime


class ApplicationListItem(BaseModel):
    """Single application entry in paginated list."""

    id: int
    vacancy_id: int
    vacancy: VacancySummary | None = None
    status: str
    cover_letter_preview: str | None = None
    sent_at: datetime | None = None
    response_at: datetime | None = None
    response_type: str | None = None
    created_at: datetime


class ApplicationPagination(BaseModel):
    """Paginated application list response."""

    items: list[ApplicationListItem]
    total: int
    page: int
    limit: int
    pages: int


class ApplicationDetail(BaseModel):
    """Full application details including full cover letter & related logs."""

    id: int
    vacancy: VacancySummary
    cover_letter: str | None = None
    status: str
    sent_at: datetime | None = None
    response_at: datetime | None = None
    response_type: str | None = None
    created_at: datetime
    captcha_attempts: list[CaptchaAttemptItem] = Field(default_factory=list)
    llm_calls: list[LLMCallItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class SettingsResponse(BaseModel):
    """Current system settings with secrets safely masked."""

    # Rate limits
    max_applications_per_hour: int
    max_applications_per_day: int
    min_delay_between_applies_sec: int
    max_delay_between_applies_sec: int
    search_interval_minutes: int

    # Search filters
    search_query: str
    search_region: int
    salary_from: int | None = None
    experience: str | None = None
    work_format: str | None = None
    target_salary: str = "180000"

    # LLM
    llm_provider: Literal["gigachat", "deepseek"]
    gigachat_auth_key_masked: str
    gigachat_scope: str
    gigachat_model: str
    deepseek_api_key_masked: str
    deepseek_model: str
    llm_temperature: float
    llm_max_tokens: int

    # OCR
    ocr_endpoint: str
    ocr_model: str
    ocr_max_retries: int


class SettingsUpdateRequest(BaseModel):
    """Updatable settings payload (all fields optional)."""

    max_applications_per_hour: int | None = None
    max_applications_per_day: int | None = None
    min_delay_between_applies_sec: int | None = None
    max_delay_between_applies_sec: int | None = None
    search_interval_minutes: int | None = None

    search_query: str | None = None
    search_region: int | None = None
    salary_from: int | None = None
    experience: str | None = None
    work_format: str | None = None
    target_salary: str | None = None

    llm_provider: Literal["gigachat", "deepseek"] | None = None
    gigachat_auth_key: str | None = None
    gigachat_scope: str | None = None
    gigachat_model: str | None = None
    deepseek_api_key: str | None = None
    deepseek_model: str | None = None
    llm_temperature: float | None = None
    llm_max_tokens: int | None = None

    ocr_endpoint: str | None = None
    ocr_model: str | None = None
    ocr_max_retries: int | None = None


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------


class ResumeResponse(BaseModel):
    """User resume text."""

    text: str
    updated_at: str | None = None


class ResumeUpdateRequest(BaseModel):
    """Payload to update resume text."""

    text: str


# ---------------------------------------------------------------------------
# Bot Status & Control
# ---------------------------------------------------------------------------


class BotStatusResponse(BaseModel):
    """Real-time bot state information."""

    status: Literal["idle", "running", "paused", "stopped", "error"]
    is_running: bool
    current_action: str | None = None
    current_vacancy: str | None = None
    uptime_seconds: int = 0
    last_run: datetime | None = None
    next_run: datetime | None = None
    applications_today: int = 0
    applications_this_hour: int = 0
    limits: dict[str, int] = Field(default_factory=dict)
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------


class LogEntry(BaseModel):
    """Structured log event."""

    timestamp: str
    level: str
    message: str
    logger: str = "app"


class LogsResponse(BaseModel):
    """List of recent log events."""

    logs: list[LogEntry]
    total: int


# ---------------------------------------------------------------------------
# Admin Panel
# ---------------------------------------------------------------------------


class AdminUserItem(BaseModel):
    """Detailed user item visible in Admin Panel."""

    id: int
    email: str
    full_name: str
    is_active: bool
    is_admin: bool
    approval_status: str
    registration_note: str | None = None
    hh_phone: str | None = None
    hh_is_connected: bool
    bot_enabled: bool
    bot_status: str
    current_action: str
    search_query: str
    has_gigachat_key: bool
    has_proxy: bool
    applications_count: int = 0
    last_run_at: datetime | None = None
    created_at: datetime
    approved_at: datetime | None = None


class AdminOverviewSummary(BaseModel):
    """Platform-wide overview metrics for Admin Panel."""

    total_users: int
    pending_count: int
    active_bots_count: int
    total_applications: int


class AdminUsersListResponse(BaseModel):
    """Admin users management payload."""

    users: list[AdminUserItem]
    summary: AdminOverviewSummary
    allow_registration_requests: bool


class AdminCreateUserRequest(BaseModel):
    """Admin manual user creation payload."""

    email: str
    password: str = Field(min_length=6)
    full_name: str = ""
    is_admin: bool = False


class AdminResetPasswordRequest(BaseModel):
    """Admin password reset payload."""

    password: str = Field(min_length=6)


class AdminSettingsUpdateRequest(BaseModel):
    """Admin platform access policy settings."""

    allow_registration_requests: bool
