#!/usr/bin/env bash
# =====================================================================
# Запуск бота на ПК (Linux / macOS)
# Первый запуск сам создаст venv и поставит зависимости.
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")/.."        # корень проекта

PY="${PYTHON:-python3}"

# 1) виртуальное окружение
if [ ! -d .venv ]; then
  echo "[*] Создаю виртуальное окружение .venv ..."
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# 2) зависимости
python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements.txt

# 3) .env с токеном
if [ ! -f .env ]; then
  cp .env.example .env
  echo "[!] Создан .env — откройте его и впишите BOT_TOKEN, затем запустите снова."
  exit 1
fi

# подгружаем переменные из .env
set -a; # shellcheck disable=SC1091
source .env; set +a

if [ -z "${BOT_TOKEN:-}" ]; then
  echo "[x] BOT_TOKEN пуст в .env"; exit 1
fi

# 4) PDF-предпросмотр — опционален (нужен LibreOffice)
if ! command -v soffice >/dev/null && ! command -v libreoffice >/dev/null; then
  echo "[i] LibreOffice не найден — бот будет отдавать Word (без PDF-предпросмотра)."
  echo "    Debian/Ubuntu: sudo apt install libreoffice-writer"
  echo "    macOS:        brew install --cask libreoffice"
fi

# 5) запуск
echo "[*] Запускаю бота (Ctrl+C — остановка) ..."
exec python app.py
