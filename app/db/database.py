"""Async database engine, session factory, and initialisation helpers.

SQLite is configured with WAL journal mode for concurrent read/write access.
PostgreSQL is supported by changing ``DATABASE_URL`` in ``.env``.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.db.models import Base

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engine & session factory (module-level singletons, created lazily)
# ---------------------------------------------------------------------------

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_engine() -> AsyncEngine:
    """Return (and lazily create) the global async engine."""
    global _engine  # noqa: PLW0603
    if _engine is None:
        settings = get_settings()
        connect_args: dict = {}
        if settings.database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False

        _engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,
            connect_args=connect_args,
            pool_pre_ping=True,
        )

        # Enable WAL for SQLite on every new raw connection
        if settings.database_url.startswith("sqlite"):

            @event.listens_for(_engine.sync_engine, "connect")
            def _set_sqlite_wal(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.close()

    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return (and lazily create) the session factory."""
    global _session_factory  # noqa: PLW0603
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


async def init_db() -> None:
    """Create all tables (if they don't exist), run migrations, and verify WAL mode."""
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Auto-migrate older SQLite databases to multi-tenant schema if user_id is missing
        settings = get_settings()
        if settings.database_url.startswith("sqlite"):
            for table in ("vacancies", "applications", "settings", "daily_stats"):
                try:
                    res = await conn.execute(text(f"PRAGMA table_info({table})"))
                    cols = [row[1] for row in res.fetchall()]
                    if cols and "user_id" not in cols:
                        logger.info("Migrating table %s: adding user_id column", table)
                        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER"))
                except Exception as exc:
                    logger.debug("Migration check on %s: %s", table, exc)

    # Log current journal mode for SQLite
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        async with engine.connect() as conn:
            result = await conn.execute(text("PRAGMA journal_mode"))
            mode = result.scalar()
            logger.info("SQLite journal_mode = %s", mode)


async def close_db() -> None:
    """Dispose of the engine connection pool."""
    global _engine, _session_factory  # noqa: PLW0603
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database engine disposed")


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional async session scope.

    Usage::

        async with get_session() as session:
            session.add(obj)
            await session.commit()
    """
    factory = _get_session_factory()
    session = factory()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_session_dep() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an ``AsyncSession``.

    Commits are the caller's responsibility; rollback happens on exception.
    """
    async with get_session() as session:
        yield session
