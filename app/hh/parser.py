"""Vacancy search URL builder and search results parser for hh.ru."""

from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Any

from patchright.async_api import Page

from app.browser.context import load_selectors

logger = logging.getLogger(__name__)


DEFAULT_STOP_WORDS = [
    "стажер",
    "стажёр",
    "intern",
    "практикант",
    "преподаватель",
    "учитель",
    "ментор",
    "автор курса",
    "1с",
    "1c",
    "bitrix",
    "битрикс",
    "менеджер по продажам",
    "sales",
    "аккаунт-менеджер",
    "дизайнер",
    "копирайтер",
    "маркетолог",
    "рекрутер",
    "hr",
    "бухгалтер",
    "юрист",
    "курьер",
    "оператор колл",
    "call-центр",
]

NON_IT_TITLE_STOP_WORDS = [
    "сантехник",
    "водопровод",
    "канализац",
    "отоплен",
    "теплоснабж",
    "вентиляц",
    "кондиционир",
    "овик",
    "котельн",
    "кипиа",
    "кип и а",
    "асу тп",
    "асутп",
    "плк",
    "plc",
    "scada",
    "электромонтаж",
    "электрик",
    "электромеханик",
    "электроэнергет",
    "энергетик",
    "слесарь",
    "монтажник",
    "наладчик",
    "пусконалад",
    "пнр",
    "сварщик",
    "токарь",
    "фрезеровщик",
    "чпу",
    "механик",
    "автомеханик",
    "слаботоч",
    "пожарн",
    "скуд",
    "видеонаблюден",
    "умный дом",
    "жкх",
    "строител",
    "прораб",
    "сметчик",
    "кладовщик",
    "водитель",
    "продавец",
    "кассир",
]

NON_IT_DESCRIPTION_MARKERS = [
    "сантехник",
    "водопровод",
    "канализац",
    "водоснабжен",
    "теплоснабжен",
    "отоплени",
    "вентиляци",
    "котельн",
    "кипиа",
    "кип и а",
    "асу тп",
    "асутп",
    "scada",
    "плк",
    "пусконалад",
    "электромонтаж",
    "электрощит",
    "трубопровод",
    "жкх",
    "слесарн",
    "монтаж систем",
    "умный дом",
]

IT_QUERY_MARKERS = {
    "devops", "девопс", "sre", "сри", "devsecops", "sysadmin", "сисадмин",
    "qa", "sdet", "тестиров", "backend", "frontend", "fullstack", "developer",
    "разработчик", "программист", "python", "golang", "java", "kubernetes",
    "linux", "platform", "mlops", "data",
}

_COMMON_QUERY_STOPWORDS = {
    "or", "and", "not", "и", "или", "для", "на", "в", "с", "по", "от",
    "developer", "разработчик", "инженер", "engineer", "специалист", "middle", "senior", "lead"
}


ROLE_SYNONYMS: dict[str, list[str]] = {
    # DevOps, SRE, Infrastructure, Automation
    "devops": [
        "devops", "девопс", "sre", "сри",
        "инфраструктур", "infrastructure",
        "platform", "платформ",
        "cloud", "облачн",
        "ci/cd", "cicd", "ci-cd",
        "reliability", "надежност",
        "системный инженер", "системный администратор linux", "linux administrator", "сисадмин linux",
        "devsecops", "девсекопс", "kubernetes", "k8s", "linux", "docker", "terraform", "ansible",
    ],
    "sre": [
        "sre", "сри", "devops", "девопс",
        "reliability", "надежност",
        "инфраструктур", "infrastructure",
        "platform", "платформ",
        "cloud", "облачн",
        "системный инженер", "мониторинг",
    ],
    # Sysadmin
    "sysadmin": [
        "системный администратор", "сисадмин", "sysadmin", "system administrator",
        "инженер сопровождения", "инженер поддержки", "дежурный инженер",
        "инфраструктур", "linux", "devops",
    ],
    # QA & Testing
    "qa": [
        "qa", "кьюа", "тестиров", "test", "quality", "sdet", "автотест", "автоматизац",
    ],
    # Backend
    "backend": [
        "backend", "бэкенд", "бекэнд", "разработчик", "developer", "engineer", "архитектор",
    ],
    # Frontend
    "frontend": [
        "frontend", "фронтенд", "верстальщик", "react", "vue", "angular", "javascript", "typescript", "web",
    ],
}


def expand_query_for_hh(query: str) -> str:
    """Format search query with OR syntax for hh.ru to match primary role and related synonyms."""
    if "," in query:
        parts = [p.strip() for p in query.split(",") if p.strip()]
        formatted = []
        for p in parts:
            if " " in p and not (p.startswith('"') and p.endswith('"')):
                formatted.append(f'"{p}"')
            else:
                formatted.append(p)
        return " OR ".join(formatted)

    q_lower = query.strip().lower()
    if q_lower in ("devops", "девопс", "devops sre", "devops / sre"):
        return 'DevOps OR SRE OR DevSecOps OR "platform engineer" OR "инженер инфраструктуры" OR "инженер CI/CD"'
    elif q_lower in ("qa", "тестировщик", "qa engineer"):
        return 'QA OR Тестировщик OR "инженер по тестированию" OR SDET'
    elif q_lower in ("sysadmin", "сисадмин", "системный администратор"):
        return '"системный администратор" OR сисадмин OR "системный инженер"'

    return query.strip()


def is_vacancy_relevant(
    title: str,
    query: str,
    stop_words: list[str] | None = None,
    require_keyword_match: bool = True,
) -> tuple[bool, str]:
    """Verify that vacancy title is relevant to search query, role synonyms, and does not hit stop words."""
    title_lower = title.lower()

    # 1. Stop words check (skip stop-word if user explicitly searched for it)
    query_lower = (query or "").lower()
    active_stops = list(stop_words if stop_words is not None else DEFAULT_STOP_WORDS)
    if stop_words is None and any(m in query_lower for m in IT_QUERY_MARKERS):
        active_stops.extend(NON_IT_TITLE_STOP_WORDS)

    for sw in active_stops:
        sw_clean = sw.strip().lower()
        if not sw_clean or sw_clean in query_lower:
            continue
        if sw_clean in title_lower:
            return False, f"Заголовок содержит стоп-слово '{sw}'"

    if not require_keyword_match:
        return True, "OK"

    # 2. Extract meaningful keywords and expand with known role synonyms
    raw_tokens = re.findall(r"[\w+-]+", query.lower())
    keywords = set(t for t in raw_tokens if len(t) >= 2 and t not in _COMMON_QUERY_STOPWORDS)

    # Check if query matches any known role clusters and add synonyms
    for role_key, syn_list in ROLE_SYNONYMS.items():
        if role_key in query.lower() or any(k in role_key for k in keywords):
            keywords.update(syn_list)

    # Also handle custom multi-word phrases from comma-separated input
    if "," in query:
        for phrase in query.split(","):
            p_clean = phrase.strip().lower()
            if p_clean:
                keywords.add(p_clean)

    if not keywords:
        keywords = set(t for t in raw_tokens if len(t) >= 2)

    if not keywords:
        return True, "OK"

    # Check if at least one meaningful keyword/synonym appears in title
    matched = any(kw in title_lower for kw in keywords)
    if not matched:
        return False, f"Заголовок не содержит ключевых слов или смежных специальностей ({', '.join(sorted(list(keywords))[:5])}...)"

    return True, "OK"


def is_description_it_relevant(title: str, description: str, query: str) -> tuple[bool, str]:
    """Filter out non-IT vacancies (plumbing, HVAC, industrial PLC/SCADA) when searching for IT roles."""
    q_low = (query or "").lower()
    if not any(m in q_low for m in IT_QUERY_MARKERS):
        return True, "OK"

    combined = f"{title}\n{description}".lower()
    for marker in NON_IT_DESCRIPTION_MARKERS:
        if marker in combined:
            return False, f"Описание содержит не-IT маркер '{marker}'"

    return True, "OK"


def build_search_url(
    query: str,
    region: int = 1,
    salary_from: int | None = None,
    experience: str | None = None,
    work_format: str | None = None,
    page: int = 0,
    search_field: str | None = "name",
) -> str:
    """Construct filtered hh.ru search URL.
    
    Setting search_field='name' tells hh.ru to match query keywords strictly
    in vacancy titles, avoiding irrelevant vacancies that merely mention the word.
    """
    effective_text = expand_query_for_hh(query)
    params: dict[str, Any] = {
        "text": effective_text,
        "area": region,
        "page": page,
    }
    if search_field:
        params["search_field"] = search_field
    if salary_from is not None:
        params["salary"] = salary_from
        params["only_with_salary"] = "true"
    if experience is not None:
        params["experience"] = experience
    if work_format is not None:
        params["schedule"] = work_format

    query_str = urllib.parse.urlencode(params)
    return f"https://hh.ru/search/vacancy?{query_str}"


def extract_hh_id_from_url(url: str) -> str:
    """Extract hh_id from a vacancy URL or href."""
    match = re.search(r"/vacancy/(\d+)", url)
    if match:
        return match.group(1)
    # Fallback to query params or hash
    cleaned = url.split("?")[0].rstrip("/").split("/")[-1]
    return cleaned if cleaned.isdigit() else url


class SearchParser:
    """Scrapes vacancy links, titles, employers, and compensation from search results."""

    def __init__(self) -> None:
        self.selectors = load_selectors()

    async def parse_search_page(self, page: Page) -> list[dict[str, Any]]:
        """Parse all vacancy snippets present on the current search results page."""
        vacancies: list[dict[str, Any]] = []

        # Find vacancy link elements using robust fallback selectors
        elements = await page.query_selector_all(
            "a[data-qa='serp-item__title'], a[href*='/vacancy/'], [data-qa='serp-item__title-link-wrapper']"
        )
        logger.info("Found %d candidate vacancy elements on search results page", len(elements))

        for el in elements:
            try:
                href = await el.get_attribute("href")
                title = (await el.inner_text()).strip()

                if not href:
                    a_tag = await el.query_selector("a[href*='/vacancy/'], a")
                    if a_tag:
                        href = await a_tag.get_attribute("href")
                        if not title:
                            title = (await a_tag.inner_text()).strip()

                if not href or "/vacancy/" not in href or not title:
                    continue

                full_url = urllib.parse.urljoin("https://hh.ru", href)
                hh_id = extract_hh_id_from_url(full_url)

                vacancies.append(
                    {
                        "hh_id": hh_id,
                        "title": title,
                        "url": full_url,
                        "company": "",
                        "salary": None,
                    }
                )
            except Exception as e:
                logger.debug("Failed parsing vacancy card snippet: %s", e)

        # Deduplicate by hh_id while maintaining order
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for v in vacancies:
            if v["hh_id"] not in seen:
                seen.add(v["hh_id"])
                deduped.append(v)

        return deduped
