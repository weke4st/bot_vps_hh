@echo off
chcp 65001 >nul
cd /d "%~dp0"
title HH Auto-Apply Bot — Вход в аккаунт hh.ru
echo =====================================================================
echo           🔑 HH Auto-Apply Bot — Авторизация на hh.ru
echo =====================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ОШИБКА] Виртуальное окружение .venv не найдено!
    echo Запустите сначала setup.bat для автоматической установки.
    echo.
    pause
    exit /b 1
)

echo Открываем браузер для авторизации на hh.ru...
echo Войдите в свой аккаунт, пройдите SMS/капчу если потребуется.
echo Когда вы увидите страницу своего профиля — вернитесь сюда и нажмите Enter.
echo.
.venv\Scripts\python.exe login.py
echo.
pause
