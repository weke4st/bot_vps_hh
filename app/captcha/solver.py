"""Local & API CAPTCHA solver using PaddleOCR-VL / GigaChat-Pro."""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from patchright.async_api import ElementHandle, Page

from app.behavior.mimic import human_click, human_typing, random_pause
from app.browser.context import load_selectors
from app.config import CAPTCHA_DIR, get_settings
from app.db.repositories import create_captcha_attempt

logger = logging.getLogger(__name__)

CAPTCHA_PROMPT = (
    "Распознай текст на изображении капчи (латинские буквы и/или цифры). "
    "Верни только распознанный текст без пояснений и кавычек. "
    "Если текст нечитаем — верни пустую строку."
)


class PaddleOCRSolver:
    """Solves Russian & alphanumeric CAPTCHAs using local PaddleOCR-VL or GigaChat-Pro vision."""

    def __init__(self, auth_key: str | None = None, scope: str | None = None) -> None:
        self.settings = get_settings()
        self.selectors = load_selectors()
        from app.cover_letter.generator import GigaChatTokenManager
        self.token_manager = GigaChatTokenManager(auth_key=auth_key, scope=scope)

    async def recognize_image(self, image_path: Path) -> str:
        """Recognize captcha image via local OCR endpoint or GigaChat-Pro vision fallback."""
        # 1. Try local OCR server (PaddleOCR-VL via llama-server / Ollama)
        try:
            image_bytes = image_path.read_bytes()
            base64_img = base64.b64encode(image_bytes).decode("utf-8")
            data_uri = f"data:image/png;base64,{base64_img}"

            payload = {
                "model": self.settings.ocr_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": CAPTCHA_PROMPT},
                            {"type": "image_url", "image_url": {"url": data_uri}},
                        ],
                    }
                ],
                "temperature": 0.0,
                "max_tokens": 30,
            }
            endpoint = f"{self.settings.ocr_endpoint.rstrip('/')}/chat/completions"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(endpoint, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        raw = choices[0].get("message", {}).get("content", "").strip()
                        cleaned = raw.replace('"', "").replace("'", "").replace("`", "").strip()
                        if cleaned:
                            logger.info("Local OCR recognized text: %r", cleaned)
                            return cleaned
        except Exception:
            pass

        # 2. Try GigaChat-Pro multimodal vision fallback
        try:
            token = await self.token_manager.get_token()
            headers = {"Authorization": f"Bearer {token}"}

            with open(image_path, "rb") as f:
                files = {
                    "file": ("captcha.png", f, "image/png"),
                    "purpose": (None, "general"),
                }
                async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
                    up_resp = await client.post(
                        "https://gigachat.devices.sberbank.ru/api/v1/files",
                        headers=headers,
                        files=files,
                    )
                    if up_resp.status_code == 200:
                        file_id = up_resp.json().get("id")
                        c_prompt = (
                            "Внимательно прочитай текст на изображении капчи (CAPTCHA). "
                            "Текст на английском языке (латинские буквы и/или цифры) или на русском языке. "
                            "Если на изображении латинские буквы — выводи строго латинские буквы, не заменяй их на похожие кириллические. "
                            "Передай в точности написанные буквы и слова, символ за символом, не исправляй опечатки и не заменяй незнакомые слова на словарные. "
                            "Выведи только распознанный текст капчи строчными буквами, без кавычек и знаков препинания."
                        )
                        c_payload = {
                            "model": "GigaChat-Pro",
                            "messages": [
                                {
                                    "role": "user",
                                    "content": c_prompt,
                                    "attachments": [file_id],
                                }
                            ],
                            "temperature": 0.0,
                            "max_tokens": 30,
                        }
                        c_resp = await client.post(
                            "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
                            headers={
                                "Authorization": f"Bearer {token}",
                                "Content-Type": "application/json",
                            },
                            json=c_payload,
                        )
                        if c_resp.status_code == 200:
                            raw = (
                                c_resp.json()["choices"][0]["message"]["content"]
                                .strip()
                                .replace('"', "")
                                .replace("'", "")
                                .replace(".", "")
                            )
                            logger.info("GigaChat-Pro recognized CAPTCHA: %r", raw)
                            return raw
        except Exception as e:
            logger.debug("GigaChat vision fallback error: %s", e)

        return ""

    async def detect_captcha(self, page: Page) -> bool:
        """Check if any CAPTCHA challenge is currently displayed on page."""
        captcha_cfg = self.selectors.get("captcha", {})
        input_sel = captcha_cfg.get(
            "input",
            "[data-qa='account-captcha-input'], [data-qa*='captcha-input'], input[name='captcha'], input[name*='captcha'], .HHCaptcha input, [class*='Hhcaptcha'] input, [data-qa='bottom-sheet-content'] input[type='text']",
        )
        img_sel = captcha_cfg.get(
            "image",
            "[data-qa='account-captcha-picture'], img[src*='captcha/picture'], img[src*='captcha'], [data-qa*='captcha-picture'], .CaptchaImage-module_hhcaptcha-picture, .HHCaptcha img",
        )
        try:
            inp = await page.query_selector(input_sel)
            if inp and await inp.is_visible():
                return True
            img = await page.query_selector(img_sel)
            if img and await img.is_visible():
                return True
            modal = await page.query_selector("[class*='HhcaptchaModal'], .HHCaptcha, [data-qa='bottom-sheet-content']:has(img[src*='captcha'])")
            if modal and await modal.is_visible():
                return True
        except Exception:
            pass
        return False

    async def solve_captcha(
        self, page: Page, application_id: int, db_session: Any
    ) -> bool:
        """Execute up to 3 recognition and submission attempts."""
        captcha_cfg = self.selectors.get("captcha", {})
        img_sel = captcha_cfg.get(
            "image",
            "[data-qa='account-captcha-picture'], img[src*='captcha/picture'], img[src*='captcha'], [data-qa*='captcha-picture'], .CaptchaImage-module_hhcaptcha-picture, .HHCaptcha img",
        )
        input_sel = captcha_cfg.get(
            "input",
            "[data-qa='account-captcha-input'], [data-qa*='captcha-input'], input[name='captcha'], input[name*='captcha'], .HHCaptcha input, [class*='Hhcaptcha'] input, [data-qa='bottom-sheet-content'] input[type='text']",
        )
        submit_sel = captcha_cfg.get(
            "submit",
            "[data-qa='bottom-sheet-content'] button:has-text('Отправить'), [class*='bottom-sheet'] button:has-text('Отправить'), [data-qa='captcha-submit'], button[data-qa*='submit'], button:has-text('Отправить'), button:has-text('Submit'), button:has-text('Подтвердить')",
        )
        refresh_sel = captcha_cfg.get(
            "refresh",
            "[data-qa='captcha-renew-text'], [class*='captcha-renew'], button:has-text('Обновить'), a:has-text('Обновить'), .HHCaptcha .captcha__refresh",
        )
        error_sel = captcha_cfg.get(
            "error",
            "[data-qa*='captcha-error'], [data-qa='account-captcha-error'], [class*='captcha__error'], [class*='HHCaptcha-error'], :has-text('Неправильный код'), :has-text('Попробуйте ещё раз'), :has-text('Попробуйте еще раз'), :has-text('Неверно')",
        )

        max_attempts = self.settings.ocr_max_retries

        lang_sel = captcha_cfg.get(
            "language",
            "[data-qa='captcha-language'], button:has-text('English'), a:has-text('English')",
        )
        try:
            lang_btns = await page.query_selector_all(lang_sel)
            for lang_btn in lang_btns:
                if not await lang_btn.is_visible():
                    continue
                lang_txt = (await lang_btn.inner_text() or "").strip().lower()
                lang_aria = (await lang_btn.get_attribute("aria-label") or "").lower()
                if "english" in lang_txt or "english" in lang_aria or lang_txt == "eng":
                    logger.info("Switching CAPTCHA language to English (%r)...", lang_txt)
                    await human_click(page, lang_btn)
                    await random_pause(min_s=0.8, max_s=1.5)
                    break
        except Exception as lang_err:
            logger.debug("Could not switch CAPTCHA language to English: %s", lang_err)

        for attempt in range(1, max_attempts + 1):
            logger.info("CAPTCHA solving attempt %d of %d", attempt, max_attempts)

            img_el: ElementHandle | None = await page.query_selector(img_sel)
            if not img_el:
                logger.warning("CAPTCHA image element not found on page")
                return False

            # Capture screenshot of captcha image
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
            img_path = CAPTCHA_DIR / f"captcha_{application_id}_{attempt}_{ts}.png"
            await img_el.screenshot(path=str(img_path))

            recognized_text = ""
            try:
                recognized_text = await self.recognize_image(img_path)
            except Exception as e:
                logger.error("OCR error during attempt %d: %s", attempt, e)

            # Record attempt in database
            if db_session:
                await create_captcha_attempt(
                    db_session,
                    application_id=application_id,
                    image_path=str(img_path),
                    model_answer=recognized_text,
                    correct=None,
                )
                await db_session.commit()

            if recognized_text:
                # Enter recognized text
                input_el = await page.query_selector(input_sel)
                if input_el:
                    await human_click(page, input_el)
                    await input_el.fill(recognized_text)
                    await random_pause(min_s=0.5, max_s=1.0)

                    # Look for actual submit button (avoiding close/refresh/language buttons!)
                    submit_candidates = await page.query_selector_all(
                        "[data-qa='bottom-sheet-content'] button, [class*='bottom-sheet'] button, button"
                    )
                    clicked_btn = False
                    for b in submit_candidates:
                        if not await b.is_visible():
                            continue
                        txt = (await b.inner_text()).strip().lower()
                        aria = (await b.get_attribute("aria-label") or "").lower()
                        dqa = (await b.get_attribute("data-qa") or "").lower()
                        # Strictly skip close, refresh, or language buttons
                        if any(k in txt or k in aria or k in dqa for k in ["закрыть", "close", "renew", "обновить", "language", "русский", "english"]):
                            continue
                        if any(k in txt or k in aria or k in dqa for k in ["отправить", "submit", "подтвердить", "продолжить"]):
                            logger.info("Clicking verified CAPTCHA submit button (%r)...", txt)
                            await human_click(page, b)
                            clicked_btn = True
                            break

                    if not clicked_btn:
                        logger.info("Submit button not found by text, submitting via Enter key...")
                        await input_el.press("Enter")

                    # Wait and verify if captcha disappeared and no error appeared
                    await random_pause(min_s=2.5, max_s=4.0)

                    # Check for explicit error message
                    has_error = False
                    try:
                        err = await page.query_selector(error_sel)
                        if err and await err.is_visible():
                            has_error = True
                    except Exception:
                        pass

                    still_visible = await self.detect_captcha(page)
                    if not still_visible and not has_error:
                        logger.info("✓ CAPTCHA solved successfully on attempt %d!", attempt)
                        return True
                    else:
                        logger.warning("CAPTCHA attempt %d rejected (still visible=%s, error=%s)", attempt, still_visible, has_error)

            # If still visible or error, click refresh to get a fresh captcha
            logger.warning("Refreshing CAPTCHA for attempt %d...", attempt + 1)
            refresh_btn = await page.query_selector(refresh_sel)
            if refresh_btn and await refresh_btn.is_visible():
                await human_click(page, refresh_btn)
                await random_pause(min_s=1.5, max_s=2.5)

        logger.warning("All %d CAPTCHA attempts failed", max_attempts)
        return False
