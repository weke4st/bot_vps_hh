"""Patchright browser manager with Android Pixel 7 emulation and persistent context."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from patchright.async_api import BrowserContext, Page, async_playwright

from app.browser.stealth import STEALTH_SCRIPT
from app.config import SCREENSHOTS_DIR, get_settings

logger = logging.getLogger(__name__)


def load_selectors() -> dict[str, Any]:
    """Load UI selectors configuration from selectors.yaml."""
    selectors_path = Path(__file__).resolve().parent.parent / "hh" / "selectors.yaml"
    with open(selectors_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class BrowserManager:
    """Manages Patchright persistent context, mobile emulation, and cookies per user."""

    def __init__(self, user_id: int | None = None, proxy_url: str | None = None) -> None:
        self.settings = get_settings()
        self.selectors = load_selectors()
        self.user_id = user_id
        self.proxy_url = proxy_url or self.settings.default_proxy

        if user_id is not None:
            from app.config import USERS_DIR
            self.user_data_dir = USERS_DIR / str(user_id) / "session"
        else:
            self.user_data_dir = Path(self.settings.user_data_dir)

        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        self.cookies_file = self.user_data_dir / "cookies.json"

        self._playwright: Any | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def start(self) -> Page:
        """Launch browser persistent context with Android Pixel 7 emulation."""
        if self._page is not None and not self._page.is_closed():
            return self._page

        logger.info(
            "Launching browser (headless=%s, profile=%s, proxy=%s)",
            self.settings.headless,
            self.user_data_dir,
            bool(self.proxy_url),
        )
        self._playwright = await async_playwright().start()

        chromium_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-infobars",
            "--window-position=0,0",
            "--ignore-certificate-errors",
            "--ignore-certificate-errors-spki-list",
            f"--user-agent={self.settings.user_agent}",
        ]

        if self.settings.headless:
            chromium_args.append("--headless=new")

        proxy_cfg = {"server": self.proxy_url} if self.proxy_url else None

        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.user_data_dir),
            headless=self.settings.headless,
            user_agent=self.settings.user_agent,
            viewport={
                "width": self.settings.viewport_width,
                "height": self.settings.viewport_height,
            },
            device_scale_factor=self.settings.device_scale_factor,
            is_mobile=True,
            has_touch=True,
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            proxy=proxy_cfg,
            extra_http_headers={
                "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                "sec-ch-ua-mobile": "?1",
                "sec-ch-ua-platform": '"Android"',
                "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            },
            args=chromium_args,
        )

        # Inject stealth scripts into every new document
        await self._context.add_init_script(STEALTH_SCRIPT)

        # Workaround for Patchright / Playwright bug #36139: restore cookies if backup exists
        await self._restore_cookies()

        pages = self._context.pages
        self._page = pages[0] if pages else await self._context.new_page()

        # Set default navigation timeouts
        self._page.set_default_navigation_timeout(45000)
        self._page.set_default_timeout(30000)

        logger.info("Browser initialized successfully (Pixel 7 Android 14 emulation)")
        return self._page

    async def _restore_cookies(self) -> None:
        """Restore cookies from json backup if available."""
        if self._context and self.cookies_file.exists():
            try:
                content = self.cookies_file.read_text(encoding="utf-8")
                cookies = json.loads(content)
                if cookies and isinstance(cookies, list):
                    await self._context.add_cookies(cookies)
                    logger.debug("Restored %d cookies from %s", len(cookies), self.cookies_file)
            except Exception as e:
                logger.warning("Failed to restore backup cookies: %s", e)

    async def save_cookies(self) -> None:
        """Save cookies to backup json file."""
        if self._context:
            try:
                cookies = await self._context.cookies()
                self.cookies_file.write_text(
                    json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                logger.debug("Saved %d cookies to %s", len(cookies), self.cookies_file)
            except Exception as e:
                logger.warning("Failed to save cookies: %s", e)

    async def get_page(self) -> Page:
        """Get or lazily start active browser page."""
        if self._page is None or self._page.is_closed():
            return await self.start()
        return self._page

    async def is_authenticated(self) -> bool:
        """Check whether the current session is logged into hh.ru."""
        page = await self.get_page()
        try:
            await page.goto("https://hh.ru", wait_until="domcontentloaded")
            logged_selector = self.selectors.get("auth", {}).get("logged_in_indicator")
            if logged_selector:
                el = await page.query_selector(logged_selector)
                if el is not None:
                    logger.info("Active session verified: user is logged in")
                    return True

            # Also check if login button exists
            login_selector = self.selectors.get("auth", {}).get("login_button")
            if login_selector:
                login_btn = await page.query_selector(login_selector)
                if login_btn is not None:
                    logger.warning("User is not logged into hh.ru (Login button is visible)")
                    return False

            return False
        except Exception as e:
            logger.error("Failed to check authentication status: %s", e)
            return False

    async def capture_screenshot(self, name_prefix: str = "error") -> Path:
        """Capture screenshot and store it in data/screenshots/."""
        page = await self.get_page()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        path = SCREENSHOTS_DIR / f"{name_prefix}_{timestamp}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            await page.screenshot(path=str(path), full_page=True)
            logger.info("Screenshot captured: %s", path)
        except Exception as e:
            logger.warning("Failed to capture full page screenshot: %s", e)
        return path

    async def close(self) -> None:
        """Save cookies and gracefully close browser context."""
        await self.save_cookies()
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
            self._page = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        logger.info("Browser closed")

    async def __aenter__(self) -> Page:
        return await self.start()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()
