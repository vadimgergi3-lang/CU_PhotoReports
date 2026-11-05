@echo off
REM ====================================================================
REM  Запуск бота на ПК (Windows)
REM  Первый запуск сам создаст venv и поставит зависимости.
REM ====================================================================
setlocal
cd /d "%~dp0.."

if not exist .venv (
  echo [*] Создаю виртуальное окружение .venv ...
  python -m venv .venv
)

call .venv\Scripts\activate.bat

python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt

if not exist .env (
  copy .env.example .env >nul
  echo [!] Создан .env — откройте его, впишите BOT_TOKEN и запустите снова.
  pause
  exit /b 1
)

where soffice >nul 2>nul || where libreoffice >nul 2>nul
if errorlevel 1 (
  echo [i] LibreOffice не найден — бот будет отдавать Word без PDF-предпросмотра.
  echo     Установка: https://www.libreoffice.org/download/
)

REM Load KEY=VALUE entries from .env without printing the token.
for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do set "%%A=%%B"
if not defined BOT_TOKEN (
  echo [x] BOT_TOKEN is empty in .env
  exit /b 1
)

echo [*] Запускаю бота (Ctrl+C — остановка) ...
python app.py

endlocal
