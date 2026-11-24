#!/usr/bin/env python3
"""Manual login helper — opens a visible browser for hh.ru authentication.

Usage::

    python login.py

The script:
1. Launches a Chromium instance with Android device emulation (Pixel 7).
2. Navigates to hh.ru.
3. Waits for the user to log in manually (including CAPTCHA if needed).
4. On pressing Enter in the terminal, saves the browser profile to ``data/session/``.

The saved persistent context (cookies, localStorage, IndexedDB) is then
used by the bot on subsequent runs — no password is stored anywhere.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Ensure project root is on sys.path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import SESSION_DIR, get_settings


async def main() -> None:
    """Run the interactive login flow."""
    # Import here to defer heavy imports
    from patchright.async_api import async_playwright

    settings = get_settings()
    session_dir = Path(settings.user_data_dir)
    session_dir.mkdir(parents=True, exist_ok=True)

    cookies_path = session_dir / "cookies.json"

    print("=" * 60)
    print("  HH Auto-Apply Bot — Manual Login")
    print("=" * 60)
    print()
    print(f"  Session dir : {session_dir.resolve()}")
    print(f"  User-Agent  : {settings.user_agent}")
    print(f"  Viewport    : {settings.viewport_width}x{settings.viewport_height}")
    print()

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(session_dir),
            headless=False,  # always visible for manual login
            user_agent=settings.user_agent,
            viewport={
                "width": settings.viewport_width,
                "height": settings.viewport_height,
            },
            device_scale_factor=settings.device_scale_factor,
            is_mobile=True,
            has_touch=True,
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                f"--user-agent={settings.user_agent}",
            ],
        )

        page = context.pages[0] if context.pages else await context.new_page()

        # Navigate to hh.ru
        await page.goto("https://hh.ru", wait_until="domcontentloaded")

        print("  ➜ Browser opened. Please log in to hh.ru manually.")
        print("  ➜ Complete any CAPTCHA if prompted.")
        print()
        print("  When you are logged in, press ENTER here to save the session.")
        print()

        # Wait for user confirmation
        await asyncio.get_event_loop().run_in_executor(None, input)

        # Save cookies as a backup (workaround for Playwright bug #36139)
        cookies = await context.cookies()
        cookies_path.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  ✓ Cookies saved to {cookies_path}")

        # The persistent context is auto-saved to user_data_dir on close
        await context.close()

    print(f"  ✓ Session profile saved to {session_dir.resolve()}")
    print()
    print("  You can now start the bot. It will use this session.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
