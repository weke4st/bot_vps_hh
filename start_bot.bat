@echo off
chcp 65001 >nul
cd /d "%~dp0"
title HH Auto-Apply Bot
echo =====================================================================
echo           🚀 HH Auto-Apply Bot — Запуск сервера
echo =====================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ОШИБКА] Виртуальное окружение .venv не найдено!
    echo Запустите сначала setup.bat для установки.
    echo.
    pause
    exit /b 1
)

.venv\Scripts\python.exe run_bot.py
pause
