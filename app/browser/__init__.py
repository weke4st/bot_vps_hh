"""Browser automation with Patchright and Android device emulation."""

from app.browser.context import BrowserManager, load_selectors
from app.browser.stealth import STEALTH_SCRIPT

__all__ = ["BrowserManager", "load_selectors", "STEALTH_SCRIPT"]
