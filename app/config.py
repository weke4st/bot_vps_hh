"""Application configuration via pydantic-settings.

All secrets and tunables are read from environment variables / .env file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

BASE_DIR: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = BASE_DIR / "data"
SESSION_DIR: Path = DATA_DIR / "session"
USERS_DIR: Path = DATA_DIR / "users"
SCREENSHOTS_DIR: Path = DATA_DIR / "screenshots"
CAPTCHA_DIR: Path = DATA_DIR / "captcha"


class Settings(BaseSettings):
    """Central configuration — loaded from ``.env`` at project root."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── General ───────────────────────────────────────────────────────────
    app_name: str = "HH Auto-Apply Bot"
    debug: bool = False
    log_level: str = "INFO"
    api_token: SecretStr = Field(default=SecretStr("changeme"), description="Bearer token for API auth")
    jwt_secret: str = "hh-bot-super-secret-jwt-key-change-in-production"
    default_proxy: str | None = None  # e.g. "http://user:pass@proxy-server:port" for cloud VPS in Netherlands

    # ── Database ──────────────────────────────────────────────────────────
    database_url: str = Field(
        default=f"sqlite+aiosqlite:///{DATA_DIR / 'bot.db'}",
        description="SQLAlchemy async DSN. SQLite (WAL) by default; set to postgresql+asyncpg://... for PG.",
    )

    # ── Browser / Device emulation ────────────────────────────────────────
    headless: bool = True
    user_data_dir: str = str(SESSION_DIR)
    user_agent: str = (
        "Mozilla/5.0 (Linux; Android 14; Pixel 7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.6778.39 Mobile Safari/537.36"
    )
    viewport_width: int = 412
    viewport_height: int = 915
    device_scale_factor: float = 2.625
    hardware_concurrency: int = 8
    device_memory: int = 8
    max_touch_points: int = 5
    webgl_vendor: str = "Qualcomm"
    webgl_renderer: str = "Adreno (TM) 740"

    # ── HH search filters ────────────────────────────────────────────────
    search_query: str = "Python developer"
    search_region: int = 1  # 1 = Moscow
    salary_from: int | None = None
    experience: str | None = None  # noExperience, between1And3, between3And6, moreThan6
    work_format: str | None = None  # remote, office, hybrid
    target_salary: str = "180000"  # Target salary to enter in employer questionnaires

    # ── Rate limits ───────────────────────────────────────────────────────
    max_applications_per_hour: int = 20
    max_applications_per_day: int = 100
    min_delay_between_applies_sec: int = 15
    max_delay_between_applies_sec: int = 30
    search_interval_minutes: int = 30

    # ── LLM — Cover letter generation ─────────────────────────────────────
    llm_provider: Literal["gigachat", "deepseek"] = "gigachat"

    # GigaChat
    gigachat_auth_key: SecretStr = Field(default=SecretStr(""), description="Base64 auth key for GigaChat OAuth")
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_base_url: str = "https://gigachat.devices.sberbank.ru/api/v1"
    gigachat_model: str = "GigaChat"
    gigachat_oauth_url: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"

    # DeepSeek
    deepseek_api_key: SecretStr = Field(default=SecretStr(""), description="DeepSeek API key")
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # LLM generation params
    llm_temperature: float = 0.7
    llm_max_tokens: int = 600

    # ── OCR — CAPTCHA solving ─────────────────────────────────────────────
    ocr_endpoint: str = "http://localhost:8080/v1"
    ocr_model: str = "PaddleOCR-VL-0.9B"
    ocr_max_retries: int = 3

    # ── Behavior tuning ───────────────────────────────────────────────────
    typing_mean_ms: int = 120
    typing_std_ms: int = 35
    typo_rate: float = 0.015
    scroll_pause_min: float = 0.3
    scroll_pause_max: float = 1.2
    action_pause_mean: float = 5.0
    miss_click_rate: float = 0.05

    @field_validator("database_url")
    @classmethod
    def _normalise_sqlite_path(cls, v: str) -> str:
        """Ensure SQLite path is absolute."""
        if v.startswith("sqlite") and ":///" not in v:
            v = v.replace("://", ":///", 1)
        return v


# Singleton-like accessor --------------------------------------------------

_settings: Settings | None = None


def get_settings() -> Settings:
    """Return cached ``Settings`` instance (created on first call)."""
    global _settings  # noqa: PLW0603
    if _settings is None:
        _settings = Settings()
    return _settings
