"""HH.ru interaction client: vacancy inspection, cover letter entry, and application submission."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from patchright.async_api import Page
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.state import bot_state
from app.behavior.mimic import (
    delay_between_applies,
    human_click,
    human_typing,
    imitate_reading,
    random_pause,
)
from app.browser.context import BrowserManager, load_selectors
from app.captcha.solver import PaddleOCRSolver
from app.config import get_settings
from app.cover_letter.generator import CoverLetterGenerator
from app.hh.questionnaire import QuestionnaireSolver
from app.db.models import Application, ApplicationStatus, Vacancy, VacancyStatus
from app.db.repositories import (
    create_application,
    get_setting,
    get_vacancy_by_hh_id,
    update_application_status,
    update_vacancy_status,
    upsert_daily_stats,
    upsert_vacancy,
)
from app.hh.parser import SearchParser, build_search_url, is_vacancy_relevant

logger = logging.getLogger(__name__)


class HHClient:
    """Automates searching, inspecting, and applying to vacancies on hh.ru."""

    def __init__(
        self,
        browser_manager: BrowserManager,
        user_id: int = 1,
        auth_key: str | None = None,
        scope: str | None = None,
        target_salary: str = "180000",
    ) -> None:
        self.browser_manager = browser_manager
        self.user_id = user_id or getattr(browser_manager, "user_id", 1) or 1
        self.settings = get_settings()
        self.selectors = load_selectors()
        self.parser = SearchParser()
        self.target_salary = target_salary
        self.captcha_solver = PaddleOCRSolver(auth_key=auth_key, scope=scope)
        self.letter_generator = CoverLetterGenerator(auth_key=auth_key, scope=scope)
        self.questionnaire_solver = QuestionnaireSolver(auth_key=auth_key, scope=scope)

    async def search_and_collect(
        self, session: AsyncSession, page_num: int = 0
    ) -> list[Vacancy]:
        """Navigate to search results and upsert new vacancies into the database."""
        page = await self.browser_manager.get_page()

        # Load active search settings (with runtime DB overrides if any)
        query = await get_setting(session, self.user_id, "search_query") or self.settings.search_query
        region_raw = await get_setting(session, self.user_id, "search_region")
        region = int(region_raw) if region_raw else self.settings.search_region
        salary_raw = await get_setting(session, self.user_id, "salary_from")
        salary_from = int(salary_raw) if salary_raw else self.settings.salary_from
        exp = await get_setting(session, self.user_id, "experience") or self.settings.experience
        fmt = await get_setting(session, self.user_id, "work_format") or self.settings.work_format

        url = build_search_url(
            query=query,
            region=region,
            salary_from=salary_from,
            experience=exp,
            work_format=fmt,
            page=page_num,
        )

        logger.info("Opening search URL for user #%d: %s", self.user_id, url)
        bot_state.set_running(action=f"Поиск вакансий: {query} (стр. {page_num})")

        try:
            await page.goto(url, wait_until="domcontentloaded")
        except Exception as nav_err:
            err_str = str(nav_err).lower()
            if "crash" in err_str or "target" in err_str or "closed" in err_str:
                logger.warning("Browser crashed on search goto. Restarting browser and retrying once...")
                page = await self.browser_manager.restart()
                await page.goto(url, wait_until="domcontentloaded")
            else:
                raise nav_err

        await random_pause(min_s=2.0, max_s=4.0)

        raw_items = await self.parser.parse_search_page(page)
        collected_vacancies: list[Vacancy] = []

        for item in raw_items:
            title = item.get("title", "")
            is_rel, reason = is_vacancy_relevant(title, query)
            if not is_rel:
                logger.info(
                    "User #%d: пропуск нерелевантной вакансии #%s ('%s'): %s",
                    self.user_id,
                    item["hh_id"],
                    title,
                    reason,
                )
                continue

            vac = await upsert_vacancy(
                session,
                user_id=self.user_id,
                hh_id=item["hh_id"],
                title=item["title"],
                company=item.get("company", ""),
                description="",
                url=item["url"],
                salary=item.get("salary"),
            )
            collected_vacancies.append(vac)

        await session.commit()
        logger.info("Saved/updated %d relevant vacancies from search for user #%d", len(collected_vacancies), self.user_id)
        return collected_vacancies

    async def _is_response_successful(self, page: Page, vacancy_hh_id: str) -> bool:
        """Check if vacancy response was accepted via multiple resilient signals without selector errors."""
        # If captcha is visible, the application is blocked and not yet successful
        if await self.captcha_solver.detect_captcha(page):
            return False

        # If error retry modal is visible ("Ваш отклик не завершился"), response is not yet successful
        for r_sel in ["button:has-text('Повторить отклик')", "button:has-text('Повторить')"]:
            try:
                r_el = await page.query_selector(r_sel)
                if r_el and await r_el.is_visible():
                    return False
            except Exception:
                pass

        signals = [
            "[data-qa='vacancy-response-already-applied']",
            "[data-qa='vacancy-response-link-view-topic']",
            "[data-qa='cover-letter-after-send snackbar']",
            "[data-qa='vacancy-response-letter-informer']",
            "[data-qa*='already-applied']",
            "[data-qa*='view-topic']",
            "[data-qa*='responded']",
            ":has-text('Вы откликнулись')",
            ":has-text('Отклик отправлен')",
            ":has-text('отклик отправлен')",
            ":has-text('Отклик доставлен')",
            ":has-text('Резюме отправлено')",
        ]
        for sel in signals:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    return True
            except Exception:
                continue

        # Visible page text check (uses inner_text to avoid matching hidden <script> translation dictionaries)
        try:
            body_text = await page.inner_text("body")
            lower = body_text.lower()
            if any(
                p in lower
                for p in ["вы откликнулись", "отклик отправлен", "отклик доставлен", "резюме отправлено"]
            ):
                return True
        except Exception:
            pass

        # Redirect check: if returned to /vacancy/{id} and no response modal is present
        try:
            if "vacancy_response" not in page.url and vacancy_hh_id in page.url:
                for sel in [
                    "[data-qa='vacancy-response-already-applied']",
                    "[data-qa='vacancy-response-link-view-topic']",
                ]:
                    el = await page.query_selector(sel)
                    if el and await el.is_visible():
                        return True
        except Exception:
            pass

        return False

    async def apply_to_vacancy(
        self, session: AsyncSession, vacancy: Vacancy, stop_event: asyncio.Event | None = None
    ) -> bool:
        """Process a single vacancy: inspect, generate letter, submit application, solve captcha."""
        page = await self.browser_manager.get_page()
        bot_state.set_running(
            action="Анализ описания вакансии", vacancy=f"{vacancy.title} ({vacancy.company})"
        )

        logger.info("Processing vacancy #%s: %s (%s)", vacancy.hh_id, vacancy.title, vacancy.url)

        # 0. Check title relevance and stop words before spending tokens or browser actions
        query = await get_setting(session, self.user_id, "search_query") or self.settings.search_query
        is_rel, rel_reason = is_vacancy_relevant(vacancy.title, query)
        if not is_rel:
            logger.info("User #%d: пропуск нерелевантной вакансии #%s ('%s'): %s", self.user_id, vacancy.hh_id, vacancy.title, rel_reason)
            await update_vacancy_status(session, vacancy.id, VacancyStatus.manual)
            await session.commit()
            return False

        try:
            try:
                await page.goto(vacancy.url, wait_until="domcontentloaded")
            except Exception as nav_err:
                err_str = str(nav_err).lower()
                if "crash" in err_str or "target" in err_str or "closed" in err_str:
                    logger.warning(
                        "Browser crashed on navigation to #%s. Restarting browser and retrying once...",
                        vacancy.hh_id,
                    )
                    page = await self.browser_manager.restart()
                    await page.goto(vacancy.url, wait_until="domcontentloaded")
                else:
                    raise nav_err

            await random_pause(min_s=2.0, max_s=4.0)

            # 1. Update company and description details from full page if missing
            vac_cfg = self.selectors.get("vacancy", {})
            title_el = await page.query_selector(vac_cfg.get("title", "[data-qa='vacancy-title']"))
            if title_el:
                vacancy.title = (await title_el.inner_text()).strip()

            comp_el = await page.query_selector(
                vac_cfg.get("company", "[data-qa='vacancy-company-name']")
            )
            if comp_el:
                vacancy.company = (await comp_el.inner_text()).strip()

            desc_el = await page.query_selector(
                vac_cfg.get("description", "[data-qa='vacancy-description']")
            )
            if desc_el:
                vacancy.description = (await desc_el.inner_text()).strip()

            sal_el = await page.query_selector(
                vac_cfg.get("salary", "[data-qa='vacancy-salary']")
            )
            if sal_el:
                vacancy.salary = (await sal_el.inner_text()).strip()

            await session.commit()

            # 2. Check if already applied
            already_applied_sel = vac_cfg.get(
                "already_applied", "[data-qa='vacancy-response-already-applied']"
            )
            already_applied = await page.query_selector(already_applied_sel)
            if already_applied and await already_applied.is_visible():
                logger.info("Already applied to vacancy #%s earlier. Skipping.", vacancy.hh_id)
                await update_vacancy_status(session, vacancy.id, VacancyStatus.applied)
                await session.commit()
                return False

            # 3. Reading imitation: scroll through description naturally
            await imitate_reading(page, desc_el)

            # 4. Generate cover letter
            resume_text = (
                await get_setting(session, self.user_id, "resume_text")
                or await get_setting(session, "resume_text")
                or ""
            )
            if not resume_text:
                logger.warning("No candidate resume configured for user #%d! Set resume via web UI.", self.user_id)

            bot_state.set_running(
                action="Генерация сопроводительного письма (LLM)",
                vacancy=f"{vacancy.title} ({vacancy.company})",
            )

            cover_letter = ""
            try:
                cover_letter = await self.letter_generator.generate(
                    vacancy_title=vacancy.title,
                    company=vacancy.company,
                    description=vacancy.description,
                    resume_text=resume_text,
                    session=session,
                )
            except Exception as e:
                logger.error(
                    "Cover letter generation failed: %s. Postponing vacancy (cannot apply without letter).",
                    e,
                )
                await update_vacancy_status(session, vacancy.id, VacancyStatus.manual)
                await session.commit()
                return False

            # 5. Create pending application record
            application = await create_application(
                session, user_id=vacancy.user_id, vacancy_id=vacancy.id, cover_letter=cover_letter
            )
            await session.commit()

            # 6. Click Apply button
            apply_btn_sel = vac_cfg.get(
                "apply_button",
                "[data-qa='vacancy-response-link-top'], [data-qa='vacancy-response-link-bottom'], [data-qa='vacancy-response-link-view'], button:has-text('Откликнуться'), a:has-text('Откликнуться'), [data-qa*='response-link'], [data-qa*='apply']",
            )
            apply_btn = await page.query_selector(apply_btn_sel)
            if not apply_btn:
                logger.warning("Apply button not found on page for vacancy #%s", vacancy.hh_id)
                await update_application_status(session, application.id, ApplicationStatus.manual)
                await update_vacancy_status(session, vacancy.id, VacancyStatus.manual)
                await session.commit()
                return False

            bot_state.set_running(
                action="Отклик на вакансию", vacancy=vacancy.title
            )
            await human_click(page, apply_btn)
            await random_pause(min_s=1.5, max_s=2.5)

            # Ensure apply click triggered on mobile view (if button still visible and no popup/redirect, retry with force)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=2000)
            except Exception:
                pass

            try:
                still_apply = await page.query_selector(apply_btn_sel)
                if still_apply and await still_apply.is_visible():
                    modal = await page.query_selector(
                        "[class*='bottom-sheet'], [class*='modal'], [data-qa*='popup'], [data-qa*='responded']"
                    )
                    if not modal and "vacancy_response" not in page.url:
                        logger.info("Retrying click on Apply button directly...")
                        try:
                            await still_apply.click(force=True)
                            await random_pause(min_s=1.5, max_s=2.5)
                        except Exception:
                            pass
            except Exception as e:
                logger.debug("Page navigated or execution context reset after apply click: %s", e)

            # Close minor nuisance surveys / post-apply survey sheets if present
            for survey_btn_sel in [
                "button:has-text('Сохранить и продолжить')",
                "[data-qa='additional-data-collector__popup-close']",
            ]:
                try:
                    s_btn = await page.query_selector(survey_btn_sel)
                    if s_btn and await s_btn.is_visible():
                        await s_btn.click()
                        await asyncio.sleep(0.5)
                        break
                except Exception:
                    pass

            # 7. Immediate CAPTCHA check: if hh.ru presented a challenge, solve or abort immediately
            if await self.captcha_solver.detect_captcha(page):
                bot_state.set_running(
                    action="Обнаружена CAPTCHA: попытка решения...", vacancy=vacancy.title
                )
                logger.info("CAPTCHA detected on vacancy #%s. Attempting solve...", vacancy.hh_id)
                solved = await self.captcha_solver.solve_captcha(page, application.id, session)
                if not solved:
                    logger.error(
                        "CAPTCHA cannot be resolved automatically for vacancy #%s. "
                        "Marking vacancy as manual. (Run 'python login.py' to clear checkpoint in browser).",
                        vacancy.hh_id,
                    )
                    await self.browser_manager.capture_screenshot(
                        name_prefix=f"captcha_failed_{vacancy.hh_id}"
                    )
                    await update_application_status(
                        session, application.id, ApplicationStatus.manual
                    )
                    await update_vacancy_status(session, vacancy.id, VacancyStatus.manual)
                    await session.commit()
                    return False
                logger.info("✓ CAPTCHA successfully resolved for vacancy #%s", vacancy.hh_id)
                await random_pause(min_s=1.5, max_s=2.5)

            # 8. Employer Questionnaire & Test Solving (LLM)
            has_questions = await self.questionnaire_solver.detect_questions(page)
            if has_questions:
                bot_state.set_running(
                    action="Ответы на тест/вопросы работодателя (LLM)",
                    vacancy=f"{vacancy.title} ({vacancy.company})",
                )
                logger.info(
                    "Employer questionnaire/test detected for vacancy #%s. Answering with LLM...",
                    vacancy.hh_id,
                )
                target_salary = (
                    await get_setting(session, vacancy.user_id, "target_salary")
                    or self.target_salary
                    or getattr(self.settings, "target_salary", "180000")
                    or "180000"
                )
                await self.questionnaire_solver.solve_all_questions(
                    page=page,
                    vacancy_title=vacancy.title,
                    company=vacancy.company,
                    resume_text=resume_text,
                    target_salary=target_salary,
                )
                await random_pause(min_s=1.0, max_s=2.0)

            # 9. Fill and submit cover letter
            form_cfg = self.selectors.get("apply_form", {})
            toggle_sel = form_cfg.get(
                "cover_letter_toggle",
                "[data-qa='responded-success-attach-cover-letter'], [data-qa='vacancy-response-letter-toggle'], [data-qa='vacancy-response-popup-letter'], [data-qa*='cover-letter'], [data-qa*='letter-toggle'], [data-qa*='add-letter'], button:has-text('сопроводительное'), a:has-text('сопроводительное'), button:has-text('письмо'), a:has-text('письмо')",
            )
            textarea_sel = form_cfg.get(
                "cover_letter_textarea",
                "textarea[data-qa='vacancy-response-popup-form-letter-input'], [data-qa='vacancy-response-letter-text'], [data-qa*='magritte-textarea'], textarea[name='letter'], textarea[placeholder*='сопроводит'], [data-qa*='letter'] textarea, textarea",
            )
            submit_sel = form_cfg.get(
                "submit_button",
                "[data-qa='vacancy-response-submit-popup'], [data-qa='vacancy-response-letter-submit'], [data-qa='vacancy-response-submit'], button:has-text('Отправить'), button:has-text('Откликнуться')",
            )

            letter_attached = False

            if cover_letter:
                bot_state.set_running(
                    action="Прикрепление сопроводительного письма", vacancy=vacancy.title
                )
                letter_input = None

                # Poll up to 6 seconds for toggle button or direct textarea
                for _ in range(8):
                    # Check if textarea is already visible
                    cand_ta = await page.query_selector(textarea_sel)
                    if cand_ta and await cand_ta.is_visible():
                        letter_input = cand_ta
                        break

                    # Check if toggle button appeared (e.g. after 1-click apply AJAX completes)
                    toggle_btn = await page.query_selector(toggle_sel)
                    if toggle_btn and await toggle_btn.is_visible():
                        logger.info("Found cover letter toggle button, opening input...")
                        await human_click(page, toggle_btn)
                        await random_pause(min_s=0.8, max_s=1.5)
                        # Re-check textarea
                        cand_ta = await page.query_selector(textarea_sel)
                        if cand_ta and await cand_ta.is_visible():
                            letter_input = cand_ta
                            break

                    await asyncio.sleep(0.7)

                if letter_input:
                    logger.info("Entering cover letter into textarea...")
                    await human_typing(page, letter_input, cover_letter)
                    await random_pause(min_s=0.8, max_s=1.5)

                    # Ensure text is properly recognized by React/Magritte state
                    try:
                        cur_val = await letter_input.input_value()
                        if not cur_val or len(cur_val.strip()) < 10:
                            logger.info("Textarea value short/empty after typing, applying fill()...")
                            await letter_input.fill(cover_letter)
                        await letter_input.dispatch_event("input")
                        await letter_input.dispatch_event("change")
                    except Exception as ev_err:
                        logger.debug("Failed to dispatch input/change events: %s", ev_err)

                    # Submit the letter with exhaustive selectors
                    submit_candidates = [
                        "[data-qa='vacancy-response-letter-submit']",
                        "[data-qa='vacancy-response-submit-popup']",
                        "[data-qa='vacancy-response-submit']",
                        "[data-qa*='letter-submit']",
                        "[data-qa*='bottom-sheet'] button:has-text('Прикрепить')",
                        "[data-qa*='bottom-sheet'] button:has-text('Отправить')",
                        "[data-qa*='bottom-sheet'] button:has-text('Сохранить')",
                        "[data-qa*='bottom-sheet'] button:has-text('Откликнуться')",
                        "[class*='bottom-sheet'] button:has-text('Прикрепить')",
                        "[class*='bottom-sheet'] button:has-text('Отправить')",
                        "[class*='bottom-sheet'] button:has-text('Сохранить')",
                        "[class*='bottom-sheet'] button:has-text('Откликнуться')",
                        "[data-qa*='popup'] button:has-text('Прикрепить')",
                        "[data-qa*='popup'] button:has-text('Отправить')",
                        "button:has-text('Прикрепить к отклику')",
                        "button:has-text('Прикрепить')",
                        "button:has-text('Сохранить')",
                        "button:has-text('Отправить письмо')",
                        "button:has-text('Отправить отклик')",
                        "button:has-text('Отправить')",
                        "button:has-text('Откликнуться')",
                        "button[type='submit']",
                    ]

                    submit_btn = None
                    for cand_sel in submit_candidates:
                        try:
                            btn = await page.query_selector(cand_sel)
                            if btn and await btn.is_visible():
                                submit_btn = btn
                                break
                        except Exception:
                            continue

                    if submit_btn:
                        try:
                            await submit_btn.scroll_into_view_if_needed()
                        except Exception:
                            pass
                        await human_click(page, submit_btn)
                        await random_pause(min_s=1.5, max_s=3.0)
                        logger.info("✓ Cover letter submitted successfully for #%s", vacancy.hh_id)
                        letter_attached = True

                        # Handle post-cover-letter CAPTCHA immediately
                        if await self.captcha_solver.detect_captcha(page):
                            bot_state.set_running(
                                action="Обнаружена CAPTCHA после отправки письма: решение...",
                                vacancy=vacancy.title,
                            )
                            logger.info("CAPTCHA appeared after cover letter submission for #%s. Solving...", vacancy.hh_id)
                            solved = await self.captcha_solver.solve_captcha(page, application.id, session)
                            if solved:
                                logger.info("✓ CAPTCHA resolved after cover letter submission for #%s", vacancy.hh_id)
                            else:
                                logger.warning("Failed to solve CAPTCHA after cover letter submission for #%s", vacancy.hh_id)
                            await random_pause(min_s=1.5, max_s=2.5)
                    else:
                        logger.warning("Cover letter submit button not visible for #%s", vacancy.hh_id)
                else:
                    logger.warning(
                        "Cover letter input not found for vacancy #%s.",
                        vacancy.hh_id,
                    )

                if not letter_attached:
                    logger.warning(
                        "Vacancy #%s: Cover letter was generated but could NOT be attached on hh.ru! Updating application record.",
                        vacancy.hh_id,
                    )
                    await session.execute(
                        update(Application)
                        .where(Application.id == application.id)
                        .values(cover_letter=f"[НЕ ПРИКРЕПЛЕНО К HH.RU]\n\n{cover_letter}")
                    )
                    await session.commit()

            # 10. STRICT VERIFICATION & SUBMISSION LOOP
            # On hh.ru, solving a CAPTCHA bottom sheet does NOT auto-submit the underlying form!
            # The bot must re-click the submit button after CAPTCHA is solved until response is confirmed.
            is_successful = await self._is_response_successful(page, vacancy.hh_id)

            for cycle in range(3):
                if is_successful:
                    break

                # Step A: If CAPTCHA is currently active, solve it first
                if await self.captcha_solver.detect_captcha(page):
                    bot_state.set_running(
                        action="Обнаружена CAPTCHA: решение...", vacancy=vacancy.title
                    )
                    logger.info("CAPTCHA detected for #%s (cycle %d). Attempting solve...", vacancy.hh_id, cycle + 1)
                    solved = await self.captcha_solver.solve_captcha(page, application.id, session)
                    if not solved:
                        logger.warning("CAPTCHA solve failed for #%s in cycle %d", vacancy.hh_id, cycle + 1)
                        break
                    await random_pause(min_s=1.5, max_s=2.5)
                    is_successful = await self._is_response_successful(page, vacancy.hh_id)
                    if is_successful:
                        break

                # Step A1: Check for "Повторить отклик" / "Повторить" error modal button
                retry_btn = None
                for r_sel in [
                    "button:has-text('Повторить отклик')",
                    "button:has-text('Повторить')",
                    "[data-qa*='retry']",
                ]:
                    try:
                        r_el = await page.query_selector(r_sel)
                        if r_el and await r_el.is_visible():
                            retry_btn = r_el
                            break
                    except Exception:
                        continue

                if retry_btn:
                    logger.info("Модальное окно 'Отклик не завершился'. Нажатие кнопки 'Повторить' для #%s...", vacancy.hh_id)
                    await human_click(page, retry_btn)
                    await random_pause(min_s=2.5, max_s=4.0)
                    if await self.captcha_solver.detect_captcha(page):
                        await self.captcha_solver.solve_captcha(page, application.id, session)
                    is_successful = await self._is_response_successful(page, vacancy.hh_id)
                    if is_successful:
                        break

                # Step B: Check if form submit button or apply link is still visible on page
                submit_candidate = None
                for candidate_sel in [
                    "[data-qa='vacancy-response-submit-popup']",
                    "[data-qa='vacancy-response-letter-submit']",
                    "[data-qa='vacancy-response-submit']",
                    "[data-qa='vacancy-response-link-top']",
                    "[data-qa='vacancy-response-link-bottom']",
                    "button:has-text('Откликнуться')",
                    "button:has-text('Отправить')",
                    "a:has-text('Откликнуться')",
                    "a:has-text('Отправить')",
                ]:
                    try:
                        cand = await page.query_selector(candidate_sel)
                        if cand and await cand.is_visible():
                            txt = (await cand.inner_text()).strip().lower()
                            if "откликнуться" in txt or "отправить" in txt:
                                submit_candidate = cand
                                break
                    except Exception:
                        continue

                if submit_candidate:
                    logger.info("Submit/apply button still visible for #%s. Clicking (cycle %d)...", vacancy.hh_id, cycle + 1)
                    await human_click(page, submit_candidate)
                    await random_pause(min_s=2.5, max_s=4.0)

                    # Solve captcha if it appeared immediately after clicking submit
                    if await self.captcha_solver.detect_captcha(page):
                        bot_state.set_running(
                            action="Обнаружена CAPTCHA после отправки формы: решение...",
                            vacancy=vacancy.title,
                        )
                        logger.info("CAPTCHA appeared after submit click for #%s. Solving...", vacancy.hh_id)
                        solved = await self.captcha_solver.solve_captcha(page, application.id, session)
                        if not solved:
                            logger.warning("Failed to solve post-submit CAPTCHA for #%s", vacancy.hh_id)
                            break
                        await random_pause(min_s=1.5, max_s=2.5)

                    is_successful = await self._is_response_successful(page, vacancy.hh_id)
                else:
                    # No submit button left on page, re-check success status
                    is_successful = await self._is_response_successful(page, vacancy.hh_id)
                    break

            if not is_successful:
                # Check if captcha or unanswered questions blocked it
                has_captcha = await self.captcha_solver.detect_captcha(page)
                reason = "Blocked by CAPTCHA" if has_captcha else "Response not accepted (questions or external form)"
                logger.error(
                    "✗ Application NOT completed for vacancy #%s: %s. Marking as manual.",
                    vacancy.hh_id,
                    reason,
                )
                await self.browser_manager.capture_screenshot(
                    name_prefix=f"not_applied_{vacancy.hh_id}"
                )
                await update_application_status(
                    session, application.id, ApplicationStatus.manual
                )
                await update_vacancy_status(session, vacancy.id, VacancyStatus.manual)
                await session.commit()
                return False

            # 10. Application successfully submitted and verified!
            now = datetime.now(timezone.utc)
            await update_application_status(
                session, application.id, ApplicationStatus.sent, sent_at=now
            )
            await update_vacancy_status(session, vacancy.id, VacancyStatus.applied)
            await upsert_daily_stats(session, user_id=vacancy.user_id, applications_delta=1)
            await session.commit()

            bot_state.record_application_sent()
            logger.info("✓ Successfully applied to vacancy #%s (%s)", vacancy.hh_id, vacancy.title)

            # 12. Crucial constraint: enforce randomized delay between applications (at least 15s)
            bot_state.set_running(
                action="Пауза безопасности между откликами (мин. 15 сек)..."
            )
            delay = await delay_between_applies(stop_event=stop_event)
            logger.info("Safety cooldown delay completed: %.1f seconds", delay)
            return True

        except Exception as exc:
            logger.error("Error while processing vacancy #%s: %s", vacancy.hh_id, exc, exc_info=True)
            err_str = str(exc).lower()
            if "crash" in err_str or "target" in err_str or "closed" in err_str:
                logger.warning("Browser target crash/close detected. Resetting browser context...")
                try:
                    await self.browser_manager.restart()
                except Exception as r_err:
                    logger.error("Failed to restart browser manager after crash: %s", r_err)
            else:
                try:
                    await self.browser_manager.capture_screenshot(
                        name_prefix=f"error_{vacancy.hh_id}"
                    )
                except Exception:
                    pass
            await update_vacancy_status(session, vacancy.id, VacancyStatus.manual)
            await session.commit()
            return False
        finally:
            await self.browser_manager.cleanup_extra_tabs()
