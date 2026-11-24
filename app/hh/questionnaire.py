"""Automated employer test and questionnaire solver using LLM (GigaChat)."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx
from patchright.async_api import Page

from app.behavior.mimic import human_click, human_typing, random_pause
from app.config import get_settings
from app.cover_letter.generator import GigaChatTokenManager

logger = logging.getLogger(__name__)

SALARY_KEYWORDS = [
    "зарплат",
    "доход",
    "зп",
    "salary",
    "оклад",
    "компенсаци",
    "деньг",
    "руб",
    "ставка",
    "ожидания",
    "вознагражден",
]

TARGET_SALARY = "180000"


class QuestionnaireSolver:
    """Detects employer test questions, passes them to LLM, and fills answers on hh.ru."""

    def __init__(self, auth_key: str | None = None, scope: str | None = None) -> None:
        self.settings = get_settings()
        self.token_manager = GigaChatTokenManager(auth_key=auth_key, scope=scope)

    def _is_salary_question(self, text: str) -> bool:
        """Check if question asks about expected compensation/salary."""
        lower = text.lower()
        return any(kw in lower for kw in SALARY_KEYWORDS)

    async def _query_llm_for_choice(
        self,
        question_title: str,
        options: list[str],
        vacancy_title: str,
        company: str,
        resume_text: str,
    ) -> int:
        """Ask LLM to pick the best option index (0-based) based on candidate's resume."""
        options_formatted = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(options)])
        prompt = (
            f"Ты квалифицированный соискатель (DevOps-инженер), откликающийся на вакансию \"{vacancy_title}\" "
            f"в компании \"{company}\".\n"
            f"Твое резюме и опыт:\n{resume_text}\n\n"
            f"Работодатель задал проверочный вопрос в тесте отклика:\n"
            f"\"{question_title}\"\n\n"
            f"Варианты ответа:\n{options_formatted}\n\n"
            f"Выбери ОДИН наиболее точный, профессиональный и правильный вариант ответа.\n"
            f"Напиши ТОЛЬКО цифру выбранного варианта (например, 1 или 2 или 3), без точек и лишних слов."
        )

        try:
            token = await self.token_manager.get_token()
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
                resp = await client.post(
                    "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
                    headers=headers,
                    json={
                        "model": "GigaChat",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.0,
                        "max_tokens": 10,
                    },
                )
                if resp.status_code == 200:
                    content = resp.json()["choices"][0]["message"]["content"].strip()
                    nums = re.findall(r"\d+", content)
                    if nums:
                        idx = int(nums[0]) - 1
                        if 0 <= idx < len(options):
                            return idx
        except Exception as exc:
            logger.warning("LLM choice resolution failed: %s. Defaulting to first option.", exc)

        return 0

    async def _query_llm_for_text_answer(
        self,
        question_title: str,
        vacancy_title: str,
        resume_text: str,
    ) -> str:
        """Ask LLM to generate a concise answer to an open-ended question."""
        prompt = (
            f"Ты соискатель (DevOps-инженер), проходящий анкету работодателя на hh.ru на вакансию \"{vacancy_title}\".\n"
            f"Твое резюме:\n{resume_text}\n\n"
            f"Вопрос работодателя:\n\"{question_title}\"\n\n"
            f"Дай краткий, уверенный и профессиональный ответ от первого лица (1-2 предложения, строго по делу)."
        )

        try:
            token = await self.token_manager.get_token()
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
                resp = await client.post(
                    "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
                    headers=headers,
                    json={
                        "model": "GigaChat",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                        "max_tokens": 120,
                    },
                )
                if resp.status_code == 200:
                    ans = resp.json()["choices"][0]["message"]["content"].strip()
                    return ans.replace('"', "")
        except Exception as exc:
            logger.warning("LLM text answer generation failed: %s", exc)

        return "Имею соответствующий практический опыт в DevOps, готов детально обсудить на интервью."

    async def detect_questions(self, page: Page) -> bool:
        """Check if page currently presents employer test questions."""
        is_quest_url = "vacancy_response" in page.url or "startedWithQuestion" in page.url
        if is_quest_url:
            return True

        # Check for radio buttons or question containers
        has_radios = await page.query_selector("input[type='radio']")
        if has_radios and await has_radios.is_visible():
            return True

        has_questions_heading = await page.query_selector(
            "text='Ответьте на вопросы', text='вопросы работодателя', [data-qa*='question']"
        )
        return has_questions_heading is not None

    async def solve_all_questions(
        self,
        page: Page,
        vacancy_title: str,
        company: str,
        resume_text: str,
        target_salary: str = TARGET_SALARY,
    ) -> bool:
        """Identify and answer all employer test questions on page."""
        logger.info("Detecting and answering employer test questions for '%s'...", vacancy_title)

        # 1. Extract radio button question groups
        radio_groups = await page.evaluate("""() => {
            let res = [];
            let radios = Array.from(document.querySelectorAll("input[type='radio']"));
            let groups = {};
            for (let r of radios) {
                let name = r.name;
                if (!name) continue;
                if (!groups[name]) groups[name] = [];
                let label = r.labels && r.labels[0] ? r.labels[0].innerText.trim() : (r.parentElement ? r.parentElement.innerText.trim() : '');
                groups[name].push({
                    value: r.value,
                    label: label
                });
            }

            for (let name in groups) {
                let firstRadio = document.querySelector(`input[name='${name}']`);
                let p = firstRadio;
                let title = '';
                // Walk up to find question title
                for (let i = 0; i < 8; i++) {
                    if (!p) break;
                    let text = p.innerText || '';
                    if (text.length > 10 && text.includes('?')) {
                        title = text.split('?')[0].trim() + '?';
                        break;
                    }
                    p = p.parentElement;
                }
                if (!title && firstRadio && firstRadio.parentElement) {
                    let parentBox = firstRadio.closest("fieldset, .magritte-v-spacing-container___mkW1c_2-1, div");
                    if (parentBox) title = (parentBox.innerText || '').split('\\n')[0].trim();
                }
                res.push({
                    name: name,
                    title: title || 'Вопрос работодателя',
                    options: groups[name]
                });
            }
            return res;
        }""")

        # Process radio groups
        for q in radio_groups:
            q_name = q.get("name")
            q_title = q.get("title", "")
            options_data = q.get("options", [])
            options_labels = [opt.get("label", "") for opt in options_data]

            if not options_labels:
                continue

            logger.info("Answering radio question: %s", q_title[:80])

            # Check if salary question
            chosen_idx = 0
            if self._is_salary_question(q_title):
                logger.info("Question relates to salary. Searching for %s tier...", target_salary)
                num_match = re.search(r"\d+", target_salary)
                salary_num = int(num_match.group(0)) if num_match else 180000
                sal_k = str(salary_num // 1000) if salary_num >= 1000 else str(salary_num)
                for idx, opt_text in enumerate(options_labels):
                    if target_salary in opt_text or sal_k in opt_text or "180" in opt_text:
                        chosen_idx = idx
                        break
            else:
                chosen_idx = await self._query_llm_for_choice(
                    question_title=q_title,
                    options=options_labels,
                    vacancy_title=vacancy_title,
                    company=company,
                    resume_text=resume_text,
                )

            chosen_opt = options_data[chosen_idx]
            val = chosen_opt.get("value")
            logger.info("Selected option %d: %s", chosen_idx + 1, chosen_opt.get("label", "")[:60])

            # Click the radio button
            radio_sel = f"input[name='{q_name}'][value='{val}']"
            radio_el = await page.query_selector(radio_sel)
            if radio_el:
                await radio_el.check(force=True)
                await asyncio.sleep(0.3)

        # 2. Extract checkboxes (consent, question choices, and technical skills)
        checkbox_data = await page.evaluate("""() => {
            let res = [];
            let cbs = Array.from(document.querySelectorAll("input[type='checkbox'], [role='checkbox']"));
            for (let cb of cbs) {
                let isInput = cb.tagName.toLowerCase() === 'input';
                let isChecked = isInput ? cb.checked : (cb.getAttribute('aria-checked') === 'true');
                if (isChecked) continue;

                let label = '';
                if (isInput && cb.labels && cb.labels[0]) {
                    label = cb.labels[0].innerText.trim();
                } else if (cb.parentElement) {
                    label = cb.parentElement.innerText.trim();
                }
                if (!label) {
                    label = (cb.getAttribute('aria-label') || '').trim();
                }

                // Find parent question block title
                let title = '';
                let p = cb.parentElement;
                for (let i = 0; i < 7; i++) {
                    if (!p) break;
                    let txt = (p.innerText || '').trim();
                    if (txt.includes('?') || txt.length > 15) {
                        let lines = txt.split('\\n').map(s => s.trim()).filter(s => s.length > 5);
                        for (let l of lines) {
                            if (l.includes('?') || l.toLowerCase().includes('опыт') || l.toLowerCase().includes('готов')) {
                                title = l;
                                break;
                            }
                        }
                    }
                    if (title) break;
                    p = p.parentElement;
                }

                res.push({
                    name: cb.getAttribute('name') || '',
                    id: cb.id || '',
                    value: cb.getAttribute('value') || '',
                    role: cb.getAttribute('role') || '',
                    label: label,
                    title: title
                });
            }
            return res;
        }""")

        for cb in checkbox_data:
            cb_label = cb.get("label", "").strip()
            cb_label_lower = cb_label.lower()
            cb_name = cb.get("name", "")
            cb_id = cb.get("id", "")
            cb_val = cb.get("value", "")

            # Never check "Нет" or "Свой вариант" when answering qualification questions
            if cb_label_lower in ["нет", "нет, не готов", "нет опыта", "нет, не имею", "свой вариант"]:
                continue

            # Check if affirmative answer to qualification question ("Да", "Да, готов", etc.)
            is_affirmative = (
                cb_label_lower == "да"
                or cb_label_lower.startswith("да,")
                or cb_label_lower.startswith("да ")
                or "готов" in cb_label_lower
                or "имею" in cb_label_lower
            )

            # Check if consent / policy / terms checkbox or positive DevOps skill
            is_consent_or_skill = any(
                term in cb_label_lower
                for term in [
                    "соглас",
                    "персональн",
                    "политик",
                    "правил",
                    "услови",
                    "подтвержд",
                    "docker",
                    "kubernetes",
                    "k8s",
                    "linux",
                    "ci/cd",
                    "git",
                    "bash",
                    "python",
                    "ansible",
                    "terraform",
                    "postgres",
                    "grafana",
                    "prometheus",
                    "astra",
                    "редос",
                ]
            )

            if is_affirmative or is_consent_or_skill:
                logger.info("Checking required/affirmative checkbox: %s", cb_label[:60])
                sel = (
                    f"input[name='{cb_name}'][value='{cb_val}']"
                    if cb_name and cb_val
                    else (f"input#{cb_id}" if cb_id else (f"input[name='{cb_name}']" if cb_name else f"label:has-text('{cb_label}')"))
                )
                cb_el = await page.query_selector(sel)
                if cb_el:
                    try:
                        await cb_el.check(force=True)
                    except Exception:
                        await human_click(page, cb_el)
                    await asyncio.sleep(0.2)
                else:
                    # Fallback click on label
                    lbl = await page.query_selector(f"label:has-text('{cb_label}'), [role='checkbox']:has-text('{cb_label}')")
                    if lbl and await lbl.is_visible():
                        await human_click(page, lbl)
                        await asyncio.sleep(0.2)

        # 3. Extract text / number inputs
        text_inputs = await page.evaluate("""() => {
            let res = [];
            let inps = Array.from(document.querySelectorAll("input[type='text'], input[type='number']"));
            for (let inp of inps) {
                if (inp.name && inp.name.includes('_xsrf')) continue;
                let label = inp.labels && inp.labels[0] ? inp.labels[0].innerText.trim() : (inp.parentElement ? inp.parentElement.innerText.trim() : '');
                let ph = inp.placeholder || '';
                res.push({
                    name: inp.name || '',
                    id: inp.id || '',
                    title: label || ph || 'Поле ввода',
                    placeholder: ph,
                    value: inp.value || ''
                });
            }
            return res;
        }""")

        for inp in text_inputs:
            inp_title = inp.get("title", "") + " " + inp.get("placeholder", "")
            inp_name = inp.get("name", "")
            inp_id = inp.get("id", "")

            # If salary field: fill target salary
            if self._is_salary_question(inp_title) or self._is_salary_question(inp_name):
                logger.info("Found salary input ('%s'). Filling target salary: %s", inp_title[:50], target_salary)
                answer_text = target_salary
            else:
                answer_text = await self._query_llm_for_text_answer(
                    question_title=inp_title,
                    vacancy_title=vacancy_title,
                    resume_text=resume_text,
                )

            selector = f"input[name='{inp_name}']" if inp_name else f"input#{inp_id}"
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                await human_click(page, el)
                await el.fill(answer_text)
                await asyncio.sleep(0.3)

        # 4. Extract question textareas (excluding cover letter textarea)
        question_textareas = await page.evaluate("""() => {
            let res = [];
            let tas = Array.from(document.querySelectorAll("textarea"));
            for (let idx = 0; idx < tas.length; idx++) {
                let ta = tas[idx];
                let dqa = ta.getAttribute('data-qa') || '';
                let name = ta.getAttribute('name') || '';
                let label = ta.labels && ta.labels[0] ? ta.labels[0].innerText.trim() : '';
                let ph = ta.getAttribute('placeholder') || '';
                let title = label || ph;
                if (!title) {
                    // Walk up parent nodes to find question title
                    let p = ta.parentElement;
                    for (let i = 0; i < 6; i++) {
                        if (!p) break;
                        let text = (p.innerText || '').trim();
                        if (text.length > 5) {
                            let lines = text.split('\\n').map(s => s.trim()).filter(s => s.length > 4);
                            for (let l of lines) {
                                let l_low = l.toLowerCase();
                                if (l_low.includes('зарплат') || l_low.includes('ожидан') || l_low.includes('вопрос') || l_low.includes('?')) {
                                    title = l;
                                    break;
                                }
                            }
                        }
                        if (title) break;
                        p = p.parentElement;
                    }
                }
                let lower = (label + ' ' + ph + ' ' + dqa + ' ' + name + ' ' + (title || '')).toLowerCase();
                // Skip if it is the cover letter textarea
                if (lower.includes('letter') || lower.includes('сопроводит')) {
                    continue;
                }
                res.push({
                    index: idx,
                    name: name,
                    id: ta.id || '',
                    dqa: dqa,
                    title: title || 'Вопрос работодателя'
                });
            }
            return res;
        }""")

        all_dom_tas = await page.query_selector_all("textarea")
        for q_ta in question_textareas:
            q_idx = q_ta.get("index", 0)
            q_title = q_ta.get("title", "")
            q_name = q_ta.get("name", "")
            q_id = q_ta.get("id", "")

            # If salary question: fill target_salary!
            if self._is_salary_question(q_title):
                logger.info("Textarea question relates to salary ('%s'). Filling target salary: %s", q_title[:50], target_salary)
                ans = target_salary
            else:
                logger.info("Answering open textarea question: %s", q_title[:80])
                ans = await self._query_llm_for_text_answer(
                    question_title=q_title,
                    vacancy_title=vacancy_title,
                    resume_text=resume_text,
                )

            el = None
            if q_idx < len(all_dom_tas):
                el = all_dom_tas[q_idx]
            if not el or not await el.is_visible():
                sel = f"textarea[name='{q_name}']" if q_name else (f"textarea#{q_id}" if q_id else "textarea")
                el = await page.query_selector(sel)

            if el and await el.is_visible():
                await human_click(page, el)
                await el.fill(ans)
                await asyncio.sleep(0.3)

        logger.info("✓ All employer questions filled successfully.")
        return True
