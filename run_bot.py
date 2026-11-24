"""HH Auto-Apply Bot launcher script.

Ensures Windows ProactorEventLoop is active for Patchright,
starts Uvicorn, and serves both the API and the compiled Web UI.

Usage::

    .venv\Scripts\python run_bot.py
"""

from __future__ import annotations

import asyncio
import os
import sys

# Force Windows Proactor loop so Patchright can spawn Chromium subprocesses without errors
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    # Suppress harmless socket shutdown error: [WinError 10054] on client disconnect
    try:
        from asyncio.proactor_events import _ProactorBasePipeTransport

        orig_call = _ProactorBasePipeTransport._call_connection_lost

        def _silenced_call_connection_lost(self, exc):
            try:
                orig_call(self, exc)
            except (ConnectionResetError, ConnectionAbortedError, OSError):
                pass

        _ProactorBasePipeTransport._call_connection_lost = _silenced_call_connection_lost
    except Exception:
        pass

import uvicorn
from app.utils.power import prevent_sleep

if __name__ == "__main__":
    prevent_sleep(True)
    print()
    print("=" * 65)
    print("   🤖 HH Auto-Apply Bot — Сервер успешно запущен!")
    print("=" * 65)
    print()
    print("   👉 Откройте в браузере: http://localhost:8000")
    print("   👉 Логи и статус:       http://localhost:8000/api/logs")
    print()
    print("   Для остановки нажмите Ctrl + C")
    print("=" * 65)
    print()

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        loop="asyncio",
    )
