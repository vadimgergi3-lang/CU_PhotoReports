#!/bin/bash
# =====================================================================
# EC2 User Data (Amazon Linux 2023) — авто-развёртывание бота.
# Вставьте этот скрипт в поле "User data" при создании EC2-инстанса.
# Предполагает, что код бота лежит в Git-репозитории (замените REPO_URL)
# или вы скопируете его вручную через scp в /opt/fotoreportcu-bot.
# =====================================================================
set -euxo pipefail

# --- НАСТРОЙКИ (подправьте под себя) ---
REPO_URL=""                         # например https://github.com/you/fotoreportcu-bot.git
BOT_TOKEN="PUT_YOUR_TOKEN_HERE"     # лучше переопределить через SSM/Secrets (см. DEPLOY_AWS.md)
APP_DIR="/opt/fotoreportcu-bot"

# --- Установка Docker ---
dnf update -y
dnf install -y docker git
systemctl enable --now docker
usermod -aG docker ec2-user || true

# --- Получаем код ---
mkdir -p "$APP_DIR"
if [ -n "$REPO_URL" ] && [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

# --- .env с токеном (если ещё нет) ---
if [ ! -f .env ]; then
  cat > .env <<EOF
BOT_TOKEN=${BOT_TOKEN}
USE_REDIS=0
WORK_DIR=/data/work
OUT_DIR=/data/out
EOF
fi

# --- Сборка и запуск ---
docker build -t fotoreportcu-bot:latest .
docker rm -f fotoreportcu-bot 2>/dev/null || true
docker volume create botdata || true
docker run -d --name fotoreportcu-bot \
  --restart unless-stopped \
  --env-file .env \
  -v botdata:/data \
  fotoreportcu-bot:latest

# Проверка:   docker logs -f fotoreportcu-bot
