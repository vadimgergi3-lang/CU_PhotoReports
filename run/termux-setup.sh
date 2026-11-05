#!/data/data/com.termux/files/usr/bin/bash
# =====================================================================
# ОДИН РАЗ: настройка бота в Termux (Android)
# Запуск:  bash run/termux-setup.sh
# =====================================================================
set -e
cd "$(dirname "$0")/.."

echo "[*] Обновляю пакеты Termux ..."
pkg update -y && pkg upgrade -y

echo "[*] Ставлю Python и системные зависимости ..."
# python-pillow из репо Termux — чтобы не компилировать Pillow вручную
pkg install -y python python-pillow libjpeg-turbo libpng freetype

echo "[*] Создаю виртуальное окружение (с доступом к системному Pillow) ..."
python -m venv --system-site-packages .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip

echo "[*] Ставлю Python-зависимости (без Pillow — он уже системный) ..."
grep -viE '^[[:space:]]*(pillow|redis)' requirements.txt > /tmp/req-termux.txt || true
python -m pip install -r /tmp/req-termux.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "[!] Создан .env — откройте его и впишите BOT_TOKEN:"
  echo "      nano .env"
fi

echo
echo "[i] LibreOffice на Android/Termux недоступен — бот будет отдавать Word (.docx)"
echo "    вместо PDF-предпросмотра. Всё остальное работает как обычно."
echo
echo "[OK] Настройка завершена. Запуск:  bash run/run-termux.sh"
