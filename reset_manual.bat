@echo off
chcp 65001 >nul
cd /d "%~dp0"
title HH Auto-Apply Bot — Сброс отложенных вакансий
echo =====================================================================
echo    🔄 Сброс вакансий со статусом 'manual' обратно в 'new'
echo =====================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ОШИБКА] Виртуальное окружение .venv не найдено!
    pause
    exit /b 1
)

.venv\Scripts\python.exe reset_manual.py
echo.
pause
