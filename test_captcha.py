"""Test script to verify CAPTCHA solving on real hh.ru captcha images or live in browser."""

import argparse
import asyncio
import sys
import time
from pathlib import Path

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from app.captcha.solver import PaddleOCRSolver

async def run_offline_test():
    root = Path(__file__).resolve().parent
    solver = PaddleOCRSolver()

    print("====================================================")
    print("      HH Auto-Apply Bot — Тест OCR на сохранённых капчах      ")
    print("====================================================\n")

    test_files = [
        ("Капча на английском (hh.ru English switch)", root / "data" / "captcha_english.png"),
        ("Капча на русском (оригинальная дуга hh.ru)", root / "data" / "captcha_sample.png"),
    ]

    for title, img_path in test_files:
        if not img_path.exists():
            print(f"[-] Файл {img_path.name} не найден, пропускаем.")
            continue

        print(f"[*] Проверяем: {title}")
        print(f"    Путь к картинке: {img_path}")
        start_t = time.time()
        try:
            recognized_text = await solver.recognize_image(img_path)
            duration = time.time() - start_t
            print(f"    [+] Распознанный текст: {recognized_text!r}")
            print(f"    [+] Время распознавания: {duration:.2f} сек.\n")
        except Exception as e:
            print(f"    [-] Ошибка распознавания: {e}\n")

    print("====================================================")
    print("Для живой проверки в браузере запустите:")
    print("  .venv\\Scripts\\python test_captcha.py --live")
    print("====================================================")

async def run_live_test():
    from app.browser.context import BrowserManager
    from app.db.database import get_session
    from app.db.repositories import list_vacancies
    from app.db.models import VacancyStatus

    print("====================================================")
    print("      HH Auto-Apply Bot — Живой тест CAPTCHA в браузере     ")
    print("====================================================\n")

    async with get_session() as s:
        vacs = await list_vacancies(s, status=VacancyStatus.new, limit=1)
        if not vacs:
            print("[-] В базе нет новых вакансий для теста.")
            return
        vac = vacs[0]

    print(f"[*] Открываем вакансию #{vac.hh_id}: {vac.title}")
    bm = BrowserManager()
    page = await bm.start()
    solver = PaddleOCRSolver()

    try:
        await page.goto(vac.url, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        apply_btn = await page.query_selector("[data-qa='vacancy-response-link-top'], [data-qa='vacancy-response-link-bottom']")
        if not apply_btn:
            print("[-] Кнопка 'Откликнуться' не найдена (возможно, уже откликнулись).")
            return

        print("[*] Нажимаем кнопку 'Откликнуться'...")
        await apply_btn.click()
        await asyncio.sleep(2)

        # Check captcha
        has_captcha = await solver.detect_captcha(page)
        if not has_captcha:
            print("[+] Капча НЕ появилась! hh.ru считает эту сессию доверенной.")
            return

        print("[!] ОБНАРУЖЕНА КАПЧА! Запускаем процедуру решения...")
        async with get_session() as s:
            solved = await solver.solve_captcha(page, application_id=0, db_session=s)

        if solved:
            print("\n[✓] УСПЕХ! Капча была успешно решена нейросетью и принята hh.ru!")
        else:
            print("\n[-] Капча не была решена автоматически.")

    finally:
        await bm.close()

def main():
    parser = argparse.ArgumentParser(description="Test CAPTCHA solver.")
    parser.add_argument("--live", action="store_true", help="Run live browser test")
    args = parser.parse_args()

    if args.live:
        asyncio.run(run_live_test())
    else:
        asyncio.run(run_offline_test())

if __name__ == "__main__":
    main()
