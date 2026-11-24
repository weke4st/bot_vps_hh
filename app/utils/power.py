"""Windows power management utilities to prevent system sleep during bot operation."""

from __future__ import annotations

import asyncio
import ctypes
import logging
import sys

logger = logging.getLogger(__name__)

# Windows Execution State Flags
# ES_CONTINUOUS: State remains in effect until the next call with ES_CONTINUOUS.
# ES_SYSTEM_REQUIRED: Resets the system idle timer, keeping CPU and network alive.
# ES_DISPLAY_REQUIRED: Resets display idle timer, preventing display sleep and Modern Standby sleep.
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

_heartbeat_task: asyncio.Task | None = None


def _set_execution_state(flags: int) -> int:
    if sys.platform == "win32":
        try:
            return ctypes.windll.kernel32.SetThreadExecutionState(flags)
        except Exception as exc:
            logger.debug("SetThreadExecutionState failed: %s", exc)
    return 0


async def _power_heartbeat_loop() -> None:
    """Periodically reset Windows idle timer every 30s to guarantee continuous all-night operation."""
    while True:
        try:
            await asyncio.sleep(30)
            _set_execution_state(ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)
        except asyncio.CancelledError:
            break
        except Exception:
            pass


def prevent_sleep(enable: bool = True) -> bool:
    """Prevent Windows from going to sleep while the bot is active."""
    global _heartbeat_task
    if sys.platform != "win32":
        return False

    try:
        if enable:
            result = _set_execution_state(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
            )
            if result != 0:
                logger.info(
                    "Windows sleep prevention ACTIVATED: system and network will not sleep while bot is running."
                )
                try:
                    loop = asyncio.get_running_loop()
                    if _heartbeat_task is None or _heartbeat_task.done():
                        _heartbeat_task = loop.create_task(_power_heartbeat_loop())
                except RuntimeError:
                    pass  # No running event loop yet (e.g. called from synchronous main entry)
                return True
        else:
            _set_execution_state(ES_CONTINUOUS)
            if _heartbeat_task and not _heartbeat_task.done():
                _heartbeat_task.cancel()
                _heartbeat_task = None
            logger.info("Windows sleep prevention DEACTIVATED: standard system sleep restored.")
            return True
    except Exception as exc:
        logger.warning("Could not set Windows execution state: %s", exc)

    return False
