"""Web-based HH.ru Login Wizard (Phone -> SMS Code) for SaaS multi-tenancy.

Allows cloud users to link their hh.ru account directly from the website without
terminal access or desktop VNC.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from patchright.async_api import BrowserContext, Page, async_playwright

from app.behavior.mimic import human_click, human_typing, random_pause
from app.browser.context import STEALTH_SCRIPT
from app.config import DATA_DIR, USERS_DIR, get_settings

logger = logging.getLogger(__name__)


@dataclass
class ActiveLoginFlow:
    user_id: int
    phone: str
    playwright: Any
    context: BrowserContext
    page: Page
    created_at: float
    proxy_url: str | None = None


# In-memory map of active login sessions awaiting SMS code (user_id -> ActiveLoginFlow)
_active_flows: dict[int, ActiveLoginFlow] = {}


async def _cleanup_expired_flows() -> None:
    """Close login flows that have timed out (> 4 minutes)."""
    now = time.time()
    expired = [uid for uid, flow in _active_flows.items() if now - flow.created_at > 240]
    for uid in expired:
        flow = _active_flows.pop(uid, None)
        if flow:
            try:
                await flow.context.close()
                await flow.playwright.stop()
            except Exception:
                pass


async def start_hh_login(user_id: int, phone: str, proxy_url: str | None = None) -> dict[str, Any]:
    """Initiate login on hh.ru: open browser, enter phone, request SMS code."""
    await _cleanup_expired_flows()

    # Cancel previous flow if already active
    if user_id in _active_flows:
        await cancel_hh_login(user_id)

    settings = get_settings()
    user_dir = USERS_DIR / str(user_id) / "session"
    user_dir.mkdir(parents=True, exist_ok=True)

    # Clean phone digits
    clean_digits = re.sub(r"\D", "", phone)
    if clean_digits.startswith("7") or clean_digits.startswith("8"):
        national_digits = clean_digits[1:]
    else:
        national_digits = clean_digits

    effective_proxy = proxy_url or settings.default_proxy
    proxy_cfg = {"server": effective_proxy} if effective_proxy else None

    pw = await async_playwright().start()
    chromium_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--no-zygote",
        "--disable-infobars",
        "--ignore-certificate-errors",
    ]

    context = await pw.chromium.launch_persistent_context(
        user_data_dir=str(user_dir),
        headless=True,
        user_agent=settings.user_agent,
        viewport={"width": settings.viewport_width, "height": settings.viewport_height},
        device_scale_factor=settings.device_scale_factor,
        is_mobile=True,
        has_touch=True,
        locale="ru-RU",
        timezone_id="Europe/Moscow",
        proxy=proxy_cfg,
        args=chromium_args,
    )

    await context.add_init_script(STEALTH_SCRIPT)
    pages = context.pages
    page = pages[0] if pages else await context.new_page()
    page.set_default_timeout(30000)

    try:
        logger.info("Opening hh.ru login page for user #%d...", user_id)
        await page.goto("https://hh.ru/account/login", wait_until="domcontentloaded")
        await random_pause(min_s=1.5, max_s=2.5)

        # 0. Handle initial account-type screen (Applicant / Employer)
        # hh.ru presents a selection screen: "Кем вы хотите войти: Я ищу работу / Я ищу сотрудников"
        type_btn = await page.query_selector(
            "button[data-qa='submit-button']:has-text('Войти'), button:has-text('Войти')"
        )
        if type_btn and await type_btn.is_visible():
            logger.info("Account type screen detected on hh.ru for user #%d. Proceeding as applicant...", user_id)
            applicant_radio = await page.query_selector("[data-qa*='account-type-card-APPLICANT']")
            if applicant_radio and await applicant_radio.is_visible():
                await human_click(page, applicant_radio)
                await asyncio.sleep(0.3)
            await human_click(page, type_btn)
            await random_pause(min_s=1.2, max_s=2.2)

        # 1. Switch to phone tab if present
        phone_tab = await page.query_selector(
            "[data-qa*='credential-type-phone'], [data-qa='account-login-tab-phone'], button:has-text('Телефон')"
        )
        if phone_tab and await phone_tab.is_visible():
            is_checked = await phone_tab.get_attribute("checked")
            if not is_checked:
                await human_click(page, phone_tab)
                await asyncio.sleep(0.5)

        # 2. Find phone input
        phone_input = None
        for sel in [
            "[data-qa='magritte-phone-input-national-number-input']",
            "[data-qa='account-signup-email']",
            "input[type='tel']",
            "input[placeholder*='номер']",
            "input[placeholder*='телефон']",
            "input[name='login']",
            "input[type='text']",
        ]:
            cand = await page.query_selector(sel)
            if cand and await cand.is_visible():
                phone_input = cand
                break

        if not phone_input:
            # Capture debug screenshot
            try:
                err_path = Path("data/screenshots") / f"login_err_{user_id}.png"
                err_path.parent.mkdir(parents=True, exist_ok=True)
                await page.screenshot(path=str(err_path))
                logger.error("Phone input missing. Debug screenshot saved: %s, URL: %s", err_path, page.url)
            except Exception:
                pass
            raise RuntimeError("Поле ввода телефона не найдено на странице hh.ru")

        # Type the phone number
        await human_click(page, phone_input)
        # If input is national number input (+7 is outside), type 10 digits
        to_type = national_digits if len(national_digits) == 10 else phone
        await human_typing(page, phone_input, to_type)
        await random_pause(min_s=0.8, max_s=1.5)

        # 3. Click Submit / Next
        submit_btn = None
        for sel in [
            "button[data-qa='submit-button']:has-text('Дальше')",
            "[data-qa='submit-button']",
            "[data-qa='account-signup-submit']",
            "button[type='submit']",
            "button:has-text('Дальше')",
            "button:has-text('Продолжить')",
            "button:has-text('Получить код')",
        ]:
            cand = await page.query_selector(sel)
            if cand and await cand.is_visible():
                submit_btn = cand
                break

        if submit_btn:
            await human_click(page, submit_btn)
        else:
            await page.keyboard.press("Enter")

        await random_pause(min_s=2.0, max_s=3.5)

        # Check for error or captcha
        body = (await page.inner_text("body")).lower()
        if "неверный" in body or "ошибка" in body:
            raise RuntimeError("hh.ru отклонил номер телефона (проверьте правильность номера)")

        # Save active flow
        _active_flows[user_id] = ActiveLoginFlow(
            user_id=user_id,
            phone=phone,
            playwright=pw,
            context=context,
            page=page,
            created_at=time.time(),
            proxy_url=proxy_url,
        )

        logger.info("✓ SMS code requested successfully on hh.ru for user #%d (%s)", user_id, phone)
        return {
            "status": "code_sent",
            "message": f"СМС-код отправлен на номер {phone}. Введите его ниже.",
        }

    except Exception as exc:
        logger.error("Error starting HH login for user #%d: %s", user_id, exc)
        try:
            await context.close()
            await pw.stop()
        except Exception:
            pass
        raise HTTPException_or_RuntimeError(str(exc))


async def verify_hh_code(user_id: int, code: str) -> dict[str, Any]:
    """Verify the SMS/email code entered by the user in the web UI."""
    await _cleanup_expired_flows()

    flow = _active_flows.get(user_id)
    if not flow:
        return {
            "status": "error",
            "message": "Сессия ожидания кода истекла. Пожалуйста, запросите код повторно.",
        }

    page = flow.page
    code_clean = re.sub(r"\D", "", code)

    try:
        logger.info("Entering SMS code for user #%d...", user_id)

        # Check for code inputs (single input or multi-digit inputs)
        multi_inputs = await page.query_selector_all("input[data-qa*='code-character'], input[maxlength='1']")
        if multi_inputs and len(multi_inputs) >= len(code_clean):
            for i, digit in enumerate(code_clean[: len(multi_inputs)]):
                await multi_inputs[i].fill(digit)
                await asyncio.sleep(0.1)
        else:
            code_input = None
            for sel in [
                "[data-qa='magritte-pincode-input-field']",
                "[data-qa*='pincode-input']",
                "[data-qa*='code-input']",
                "[data-qa*='sms-code']",
                "input[autocomplete='one-time-code']",
                "input[name='otp']",
                "input[name*='code']",
                "input[type='tel']",
                "input[type='number']",
                "input[type='text']",
            ]:
                cand = await page.query_selector(sel)
                if cand and await cand.is_visible():
                    code_input = cand
                    break

            if code_input:
                await human_click(page, code_input)
                await code_input.fill(code_clean)
                await asyncio.sleep(0.3)
                await page.keyboard.press("Enter")
            else:
                # Keyboard type directly
                await page.keyboard.type(code_clean)
                await page.keyboard.press("Enter")

        # Click submit button if visible
        submit_btn = await page.query_selector(
            "button[type='submit'], [data-qa='submit-button'], button:has-text('Войти'), button:has-text('Подтвердить')"
        )
        if submit_btn and await submit_btn.is_visible():
            await human_click(page, submit_btn)

        await random_pause(min_s=2.5, max_s=4.0)

        # Check for error
        body = (await page.inner_text("body")).lower()
        if "неверный код" in body or "неправильный код" in body:
            return {"status": "error", "message": "Неверный код подтверждения. Попробуйте ещё раз."}

        # Verify logged in
        cookies = await flow.context.cookies()
        hhtokens = [c for c in cookies if "hhtoken" in c.get("name", "").lower()]

        cookies_file = USERS_DIR / str(user_id) / "session" / "cookies.json"
        cookies_file.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")

        # Fetch resumes
        resumes = []
        try:
            await page.goto("https://hh.ru/applicant/resumes", wait_until="domcontentloaded")
            await random_pause(min_s=1.5, max_s=2.5)

            resume_elements = await page.query_selector_all(
                "[data-qa='resume-title'], [data-qa*='resume-title']"
            )
            for el in resume_elements:
                title = (await el.inner_text()).strip()
                href = (await el.get_attribute("href")) or ""
                m = re.search(r"/resume/([a-f0-9]+)", href)
                r_id = m.group(1) if m else href
                if title:
                    resumes.append({"id": r_id, "title": title})
        except Exception as e:
            logger.warning("Could not fetch resumes automatically: %s", e)

        # Close browser session
        _active_flows.pop(user_id, None)
        try:
            await flow.context.close()
            await flow.playwright.stop()
        except Exception:
            pass

        logger.info("✓ HH.ru successfully connected for user #%d (%d resumes found)", user_id, len(resumes))
        return {
            "status": "success",
            "message": "Аккаунт hh.ru успешно подключен!",
            "resumes": resumes,
            "has_token": len(hhtokens) > 0,
        }

    except Exception as exc:
        logger.error("Error verifying SMS code for user #%d: %s", user_id, exc)
        return {"status": "error", "message": f"Ошибка подтверждения: {exc}"}


async def cancel_hh_login(user_id: int) -> None:
    """Cancel active login flow for user and release browser resources."""
    flow = _active_flows.pop(user_id, None)
    if flow:
        try:
            await flow.context.close()
            await flow.playwright.stop()
        except Exception:
            pass


def HTTPException_or_RuntimeError(msg: str):
    from fastapi import HTTPException
    return HTTPException(status_code=400, detail=msg)
