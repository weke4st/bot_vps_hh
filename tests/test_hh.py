"""Unit tests for HH.ru search parser and selectors configuration."""

from __future__ import annotations

from app.browser.context import load_selectors
from app.hh.parser import build_search_url, extract_hh_id_from_url


def test_build_search_url() -> None:
    url = build_search_url(
        query="Python",
        region=1,
        salary_from=180000,
        experience="between1And3",
        work_format="remote",
        page=2,
    )
    assert "text=Python" in url
    assert "area=1" in url
    assert "salary=180000" in url
    assert "experience=between1And3" in url
    assert "schedule=remote" in url
    assert "page=2" in url


def test_extract_hh_id_from_url() -> None:
    assert extract_hh_id_from_url("https://hh.ru/vacancy/11223344") == "11223344"
    assert (
        extract_hh_id_from_url("https://hh.ru/vacancy/998877?query=python&area=1")
        == "998877"
    )


def test_selectors_yaml_structure() -> None:
    selectors = load_selectors()
    assert "search" in selectors
    assert "vacancy" in selectors
    assert "apply_form" in selectors
    assert "captcha" in selectors
    assert "auth" in selectors
