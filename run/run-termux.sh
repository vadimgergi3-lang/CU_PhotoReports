#!/data/data/com.termux/files/usr/bin/bash
# =====================================================================
# Запуск бота в Termux (Android)
# Перед первым запуском выполните:  bash run/termux-setup.sh
# =====================================================================
set -e
cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  echo "[x] Окружение не настроено. Сначала:  bash run/termux-setup.sh"
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# подгружаем .env
if [ ! -f .env ]; then
  echo "[x] Нет .env. Скопируйте:  cp .env.example .env  и впишите BOT_TOKEN"
  exit 1
fi
set -a; # shellcheck disable=SC1091
source .env; set +a

if [ -z "${BOT_TOKEN:-}" ]; then
  echo "[x] BOT_TOKEN пуст в .env (nano .env)"; exit 1
fi

# не даём Android усыпить процесс (требует Termux:API или встроен. wake-lock)
termux-wake-lock 2>/dev/null || true

echo "[*] Запускаю бота. Чтобы не закрывался при сворачивании — держите Termux открытым"
echo "    или запустите через:  nohup bash run/run-termux.sh &"
echo "    Остановка — Ctrl+C. Снять wake-lock:  termux-wake-unlock"
echo
exec python app.py
