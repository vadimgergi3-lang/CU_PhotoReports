# Фото-отчётный Telegram-бот CONTROL UNION
# Образ для запуска на AWS (EC2 / ECS Fargate / Lightsail Containers).
# Отчёты только в формате DOCX.
FROM python:3.11-slim

# Системные зависимости: шрифты и curl (health-check).
RUN apt-get update && apt-get install -y --no-install-recommends \
        fonts-dejavu \
        fonts-liberation \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp \
    WORK_DIR=/data/work \
    OUT_DIR=/data/out

WORKDIR /app

# Сначала зависимости (лучше кешируется при пересборке).
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Затем весь код.
COPY . .

# Рабочие папки для данных + непривилегированный пользователь.
RUN mkdir -p /data/work /data/out \
    && useradd -m -u 10001 appuser \
    && chown -R appuser:appuser /app /data
USER appuser

# app.py поднимает health-эндпойнт на :3000 и запускает polling бота.
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD curl -fsS http://127.0.0.1:3000/health || exit 1

CMD ["python", "app.py"]
