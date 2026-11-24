"""SQLAlchemy 2.x ORM models for HH Auto-Apply SaaS Multi-Tenant Platform.

Tables
------
- ``User``           — SaaS user account with per-user settings, GigaChat keys, and proxy.
- ``Vacancy``        — parsed vacancy cards from hh.ru per user.
- ``Application``    — submitted (or pending) job applications per user.
- ``CaptchaAttempt`` — individual CAPTCHA solve attempts.
- ``Setting``        — key/value runtime settings store per user.
- ``DailyStats``     — aggregated daily counters for dashboard charts per user.
- ``LLMCall``        — LLM API usage log for cost tracking.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """Shared declarative base for all models."""

    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class VacancyStatus(str, enum.Enum):
    """Lifecycle status of a vacancy record."""

    new = "new"
    skipped = "skipped"
    applied = "applied"
    manual = "manual"


class ApplicationStatus(str, enum.Enum):
    """Lifecycle status of an application."""

    pending = "pending"
    sent = "sent"
    response = "response"
    interview = "interview"
    rejected = "rejected"
    manual = "manual"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class User(Base):
    """User account on the SaaS platform with personal credentials and session."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(default=False, nullable=False)
    approval_status: Mapped[str] = mapped_column(
        String(32), default="approved", nullable=False, index=True
    )
    registration_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # HH.ru Account Details
    hh_phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    hh_is_connected: Mapped[bool] = mapped_column(default=False, nullable=False)
    selected_resume_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    selected_resume_title: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # Personal GigaChat credentials (each user inputs their own)
    gigachat_auth_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gigachat_scope: Mapped[str] = mapped_column(String(64), default="GIGACHAT_API_PERS", nullable=False)

    # Personal Proxy for Netherlands VPS bypass (optional)
    proxy_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Search & Application Filters
    search_query: Mapped[str] = mapped_column(String(256), default="DevOps", nullable=False)
    search_region: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 1 = Moscow, 113 = Russia
    target_salary: Mapped[str] = mapped_column(String(64), default="180000", nullable=False)

    # Bot runner state
    bot_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    bot_status: Mapped[str] = mapped_column(String(64), default="stopped", nullable=False)
    current_action: Mapped[str] = mapped_column(String(256), default="Ожидание", nullable=False)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    vacancies: Mapped[list[Vacancy]] = relationship(
        "Vacancy", back_populates="user", cascade="all, delete-orphan"
    )
    applications: Mapped[list[Application]] = relationship(
        "Application", back_populates="user", cascade="all, delete-orphan"
    )
    daily_stats: Mapped[list[DailyStats]] = relationship(
        "DailyStats", back_populates="user", cascade="all, delete-orphan"
    )
    settings: Mapped[list[Setting]] = relationship(
        "Setting", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} connected={self.hh_is_connected}>"


class Vacancy(Base):
    """A parsed vacancy from hh.ru per user."""

    __tablename__ = "vacancies"
    __table_args__ = (UniqueConstraint("user_id", "hh_id", name="uq_user_vacancy_hh_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hh_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    company: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    salary: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    status: Mapped[VacancyStatus] = mapped_column(
        Enum(VacancyStatus, native_enum=False, length=16),
        nullable=False,
        default=VacancyStatus.new,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="vacancies")
    applications: Mapped[list[Application]] = relationship(
        "Application", back_populates="vacancy", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Vacancy id={self.id} user_id={self.user_id} hh_id={self.hh_id!r} title={self.title!r}>"


class Application(Base):
    """A job application (one per vacancy attempt per user)."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vacancy_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("vacancies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cover_letter: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus, native_enum=False, length=16),
        nullable=False,
        default=ApplicationStatus.pending,
        index=True,
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    response_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    response_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="applications")
    vacancy: Mapped[Vacancy] = relationship("Vacancy", back_populates="applications")
    captcha_attempts: Mapped[list[CaptchaAttempt]] = relationship(
        "CaptchaAttempt", back_populates="application", cascade="all, delete-orphan"
    )
    llm_calls: Mapped[list[LLMCall]] = relationship(
        "LLMCall", back_populates="application", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Application id={self.id} user_id={self.user_id} vacancy_id={self.vacancy_id} status={self.status.value!r}>"


class CaptchaAttempt(Base):
    """Record of a single CAPTCHA recognition attempt."""

    __tablename__ = "captcha_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    image_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    model_answer: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    correct: Mapped[Optional[bool]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    application: Mapped[Application] = relationship("Application", back_populates="captcha_attempts")

    def __repr__(self) -> str:
        return f"<CaptchaAttempt id={self.id} correct={self.correct}>"


class Setting(Base):
    """Key-value runtime settings per user."""

    __tablename__ = "settings"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_user_setting_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")

    user: Mapped[User] = relationship("User", back_populates="settings")

    def __repr__(self) -> str:
        return f"<Setting user_id={self.user_id} key={self.key!r}>"


class DailyStats(Base):
    """Aggregated daily counters for dashboard charts per user."""

    __tablename__ = "daily_stats"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_user_daily_stats_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    applications_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    responses_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    interviews_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    user: Mapped[User] = relationship("User", back_populates="daily_stats")

    def __repr__(self) -> str:
        return f"<DailyStats user_id={self.user_id} date={self.date} apps={self.applications_count}>"


class LLMCall(Base):
    """LLM API call log — tracks provider usage and latency."""

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    application: Mapped[Optional[Application]] = relationship("Application", back_populates="llm_calls")

    def __repr__(self) -> str:
        return f"<LLMCall id={self.id} provider={self.provider!r} tokens={self.prompt_tokens + self.completion_tokens}>"
