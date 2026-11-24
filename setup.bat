@echo off
chcp 65001 >nul
cd /d "%~dp0"
title HH Auto-Apply Bot — Установка
echo =====================================================================
echo           🤖 HH Auto-Apply Bot — Мастер установки
echo =====================================================================
echo.

:: 1. Проверка наличия Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не найден в системе!
    echo 1. Скачайте Python 3.10+ с официального сайта: https://www.python.org/downloads/
    echo 2. При установке ОБЯЗАТЕЛЬНО поставьте галочку "Add Python to PATH"!
    echo 3. После установки перезапустите этот скрипт.
    echo.
    pause
    exit /b 1
)

echo [✓] Python найден в системе.
echo.

:: 2. Создание виртуального окружения
if not exist ".venv" (
    echo [1/4] Создание виртуального окружения Python (.venv)...
    python -m venv .venv
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось создать виртуальное окружение .venv!
        pause
        exit /b 1
    )
) else (
    echo [1/4] Виртуальное окружение .venv уже существует.
)

:: 3. Обновление pip и установка зависимостей
echo.
echo [2/4] Установка библиотек из requirements.txt...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ОШИБКА] Ошибка при установке Python-библиотек!
    pause
    exit /b 1
)

:: 4. Установка браузера Chromium для Patchright
echo.
echo [3/4] Установка браузера Patchright Chromium...
.venv\Scripts\python.exe -m patchright install chromium
if errorlevel 1 (
    echo [ОШИБКА] Ошибка при установке Chromium для Patchright!
    pause
    exit /b 1
)

:: 5. Подготовка конфигурации .env
echo.
echo [4/4] Проверка файла конфигурации .env...
if not exist ".env" (
    copy .env.example .env >nul
    echo [✓] Файл .env успешно создан из шаблона .env.example!
) else (
    echo [✓] Файл .env уже настроен.
)

echo.
echo =====================================================================
echo   🎉 Установка успешно завершена!
echo.
echo   Что делать дальше:
echo   1. Откройте файл .env (Блокнотом) и вставьте ключ GigaChat:
echo      GIGACHAT_AUTH_KEY=ваш_ключ_здесь
echo.
echo   2. Запустите login.bat, войдите в свой аккаунт на hh.ru
echo      и нажмите клавишу Enter в консоли для сохранения входа.
echo.
echo   3. Запустите start_bot.bat и перейдите в браузере:
echo      👉 http://localhost:8000
echo =====================================================================
echo.
pause
