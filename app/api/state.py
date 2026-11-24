"""Runtime bot state tracking, in-memory log buffer, and WebSocket broadcasting."""

from __future__ import annotations

import asyncio
import collections
import logging
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import WebSocket

from app.api.schemas import BotStatusResponse, LogEntry
from app.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# In-Memory Ring Buffer for Logs
# ---------------------------------------------------------------------------


class LogBufferHandler(logging.Handler):
    """Logging handler that captures records into an in-memory deque and broadcasts."""

    def __init__(self, buffer: collections.deque[LogEntry], max_level: int = logging.DEBUG) -> None:
        super().__init__(level=max_level)
        self.buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            entry = LogEntry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                level=record.levelname,
                message=msg,
                logger=record.name,
            )
            self.buffer.append(entry)

            # Fire-and-forget broadcast to WebSockets
            if ws_manager.active_connections:
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(
                        ws_manager.broadcast_json({"type": "log", "data": entry.model_dump(mode="json")})
                    )
                except RuntimeError:
                    pass
        except Exception:
            self.handleError(record)


# ---------------------------------------------------------------------------
# WebSocket Connection Manager
# ---------------------------------------------------------------------------


class WebSocketManager:
    """Manages active WebSocket connections and delivers live updates."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new client."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.debug("WebSocket client connected. Total clients: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        """Unregister a disconnected client."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.debug(
                "WebSocket client disconnected. Total clients: %d", len(self.active_connections)
            )

    async def broadcast_json(self, payload: dict[str, Any]) -> None:
        """Broadcast JSON payload to all active clients, cleaning up dead ones."""
        disconnected: list[WebSocket] = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(payload)
            except Exception:
                disconnected.append(connection)

        for dead in disconnected:
            self.disconnect(dead)


# ---------------------------------------------------------------------------
# Bot State Manager
# ---------------------------------------------------------------------------


class BotStateManager:
    """Central store for bot runtime state, action tracking, and counters."""

    def __init__(self) -> None:
        self.status: Literal["idle", "running", "paused", "stopped", "error"] = "idle"
        self.is_running: bool = False
        self.current_action: str | None = None
        self.current_vacancy: str | None = None
        self.started_at: datetime | None = None
        self.last_run: datetime | None = None
        self.next_run: datetime | None = None
        self.error_message: str | None = None

        # Counters for current session
        self.applications_today: int = 0
        self.applications_this_hour: int = 0

        # In-memory log buffer (retains last 500 records)
        self.log_buffer: collections.deque[LogEntry] = collections.deque(maxlen=500)
        self.log_handler = LogBufferHandler(self.log_buffer)

    def attach_logger(self) -> None:
        """Attach buffer handler to root logger so all app logs are captured."""
        root = logging.getLogger()
        if self.log_handler not in root.handlers:
            self.log_handler.setFormatter(
                logging.Formatter("%(message)s")
            )
            root.addHandler(self.log_handler)

    def set_running(self, action: str | None = None, vacancy: str | None = None) -> None:
        """Mark bot as running an active task."""
        self.status = "running"
        self.is_running = True
        if self.started_at is None:
            self.started_at = datetime.now(timezone.utc)
        self.current_action = action
        self.current_vacancy = vacancy
        self.error_message = None
        self._notify_state_change()

    def set_idle(self, next_run: datetime | None = None) -> None:
        """Mark bot as idle (waiting for next scheduled interval)."""
        self.status = "idle"
        self.is_running = False
        self.current_action = None
        self.current_vacancy = None
        self.last_run = datetime.now(timezone.utc)
        self.next_run = next_run
        self._notify_state_change()

    def set_stopped(self) -> None:
        """Mark bot as stopped by user."""
        self.status = "stopped"
        self.is_running = False
        self.current_action = None
        self.current_vacancy = None
        self.started_at = None
        self.next_run = None
        self._notify_state_change()

    def set_error(self, message: str) -> None:
        """Mark bot in error state."""
        self.status = "error"
        self.is_running = False
        self.error_message = message
        self.current_action = None
        self.current_vacancy = None
        self._notify_state_change()

    def record_application_sent(self) -> None:
        """Increment live counters."""
        self.applications_today += 1
        self.applications_this_hour += 1

    def to_status_response(self) -> BotStatusResponse:
        """Build status schema response."""
        settings = get_settings()
        uptime = 0
        if self.started_at:
            uptime = int((datetime.now(timezone.utc) - self.started_at).total_seconds())

        return BotStatusResponse(
            status=self.status,
            is_running=self.is_running,
            current_action=self.current_action,
            current_vacancy=self.current_vacancy,
            uptime_seconds=uptime,
            last_run=self.last_run,
            next_run=self.next_run,
            applications_today=self.applications_today,
            applications_this_hour=self.applications_this_hour,
            limits={
                "per_hour": settings.max_applications_per_hour,
                "per_day": settings.max_applications_per_day,
                "min_delay_sec": settings.min_delay_between_applies_sec,
                "interval_min": settings.search_interval_minutes,
            },
            error_message=self.error_message,
        )

    def snapshot(self) -> BotStatusResponse:
        """Alias for to_status_response for backward compatibility."""
        return self.to_status_response()

    @property
    def logs(self) -> list[LogEntry]:
        """Return all log entries currently in memory."""
        return list(self.log_buffer)

    def get_logs(self, limit: int = 100) -> list[LogEntry]:
        """Return the most recent log entries up to limit."""
        return list(self.log_buffer)[-limit:]

    def _notify_state_change(self) -> None:
        """Broadcast state update to all WebSocket listeners."""
        if ws_manager.active_connections:
            payload = {"type": "bot_status", "data": self.to_status_response().model_dump(mode="json")}
            asyncio.create_task(ws_manager.broadcast_json(payload))


# Global singletons
bot_state = BotStateManager()
ws_manager = WebSocketManager()
