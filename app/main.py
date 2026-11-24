"""HH Auto-Apply Bot — FastAPI application entry point.

Run with::

    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

# Fix for Windows: Ensure ProactorEventLoop is used so Patchright can spawn Chromium subprocesses
if sys.platform == "win32":
    try:
        import uvicorn.loops.asyncio

        uvicorn.loops.asyncio.asyncio_loop_factory = (
            lambda use_subprocess=False: asyncio.ProactorEventLoop
        )
    except Exception:
        pass
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.api.state import bot_state
from app.config import get_settings
from app.db.database import close_db, init_db
from app.scheduler.service import scheduler_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_application: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle hook."""
    settings = get_settings()

    # ── Startup ───────────────────────────────────────────────────────────
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    logger.info("Starting %s (debug=%s)", settings.app_name, settings.debug)

    # Ensure data directories exist
    from app.config import CAPTCHA_DIR, SCREENSHOTS_DIR, SESSION_DIR, USERS_DIR

    for d in (SESSION_DIR, SCREENSHOTS_DIR, CAPTCHA_DIR, USERS_DIR):
        d.mkdir(parents=True, exist_ok=True)

    # Initialise database (create tables, enable WAL)
    await init_db()
    logger.info("Database initialised")

    # Start background scheduler service
    scheduler_service.start()
    logger.info("Background scheduler started")

    # Attach in-memory log buffer & WebSocket broadcaster
    bot_state.attach_logger()

    # Prevent Windows from sleeping during bot execution
    from app.utils.power import prevent_sleep

    prevent_sleep(True)

    # Suppress harmless Windows socket reset errors in asyncio event loop
    loop = asyncio.get_running_loop()

    def _suppress_winerror_10054(l, context):
        exc = context.get("exception")
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError)):
            return
        if isinstance(exc, OSError) and getattr(exc, "winerror", None) == 10054:
            return
        l.default_exception_handler(context)

    loop.set_exception_handler(_suppress_winerror_10054)

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────
    prevent_sleep(False)
    await scheduler_service.shutdown()
    await close_db()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS — allow web access
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount API router
    application.include_router(api_router)

    # Health check
    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # Mount compiled React frontend if present
    from pathlib import Path
    from fastapi.staticfiles import StaticFiles

    dist_dir = Path(__file__).resolve().parent.parent / "web" / "dist"
    if dist_dir.exists():
        application.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="static")

    return application


app: FastAPI = create_app()

