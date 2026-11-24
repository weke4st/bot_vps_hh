"""Unit tests for employer questionnaire solver and Windows power management."""

from __future__ import annotations

import pytest

from app.hh.questionnaire import TARGET_SALARY, QuestionnaireSolver
from app.utils.power import prevent_sleep


def test_questionnaire_salary_detection() -> None:
    solver = QuestionnaireSolver()

    # Positive salary queries
    assert solver._is_salary_question("Укажите ваши зарплатные ожидания")
    assert solver._is_salary_question("Желаемый уровень дохода (net)")
    assert solver._is_salary_question("Какая зп вас интересует?")
    assert solver._is_salary_question("Expected salary?")
    assert solver._is_salary_question("Минимальный оклад")
    assert solver._is_salary_question("Сколько денег хотите получать в рублях?")

    # Negative non-salary queries
    assert not solver._is_salary_question("Опишите опыт работы с Kubernetes")
    assert not solver._is_salary_question("Какой у вас уровень английского языка?")
    assert not solver._is_salary_question("Готовы ли вы к гибридному графику?")


def test_target_salary_constant() -> None:
    # Must be 180k as requested by user
    assert TARGET_SALARY == "180000"


def test_prevent_sleep_invocations() -> None:
    # Prevent sleep should succeed or safely return on platform without raising exceptions
    res_on = prevent_sleep(True)
    res_off = prevent_sleep(False)
    assert isinstance(res_on, bool)
    assert isinstance(res_off, bool)
