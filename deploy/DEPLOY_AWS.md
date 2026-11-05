# Развёртывание бота CONTROL UNION на AWS

Бот работает в режиме **long-polling** (aiogram 3) — сам обращается к Telegram, входящие подключения ему не нужны.
Ему нужен **постоянно запущенный контейнер** (не Lambda), потому что:
- polling должен работать непрерывно;
- для генерации PDF используется LibreOffice (`soffice`) — тяжёлая зависимость, не подходит для Lambda.

Ниже два пути. **Рекомендую вариант A (EC2)** — проще и дешевле для одного бота.

---

## Что в комплекте

- `Dockerfile` — образ `python:3.11-slim` + LibreOffice Writer + шрифты, запуск от непривилегированного пользователя, `HOME=/tmp` (нужно `soffice`), HEALTHCHECK на `/health`.
- `docker-compose.yml` — локальный/EC2 запуск с авторестартом.
- `deploy/aws-ec2-userdata.sh` — скрипт авто-развёртывания для Amazon Linux 2023 (User data).
- `deploy/ecs-task-definition.json` — шаблон задачи для ECS Fargate.

Переменные окружения (см. `.env.example`):

| Переменная | Назначение | По умолчанию в образе |
|-----------|-----------|---------------------|
| `BOT_TOKEN` | токен бота от @BotFather | — (обязательно) |
| `USE_REDIS` | 1 — хранить FSM в Redis | `0` (MemoryStorage) |
| `REDIS_URL` | адрес Redis при `USE_REDIS=1` | — |
| `WORK_DIR` | временные рабочие файлы | `/data/work` |
| `OUT_DIR` | готовые документы | `/data/out` |

> FSM хранится в памяти. При рестарте контейнера незавершённые диалоги теряются. Для одного бота это обычно приемлемо; если важно — включите Redis (`USE_REDIS=1` + ElastiCache).

---

## Вариант A — EC2 + Docker (рекомендуемый)

### A1. Создать инстанс

1. EC2 → Launch instance.
2. AMI: **Amazon Linux 2023**.
3. Тип: `t3.small` (2 ГБ RAM — LibreOffice любит память; `t3.micro` может хватить, но впритык).
4. Security Group: входящие правила — только SSH (22) с вашего IP. **Порт 3000 открывать НЕ нужно** — polling не принимает входящие.
5. Storage: 15–20 ГБ gp3.

### A2. Авто-развёртывание через User data

В разделе **Advanced → User data** вставьте содержимое `deploy/aws-ec2-userdata.sh`,
предварительно подправив:
- `REPO_URL` — если код в Git (иначе зальёте код вручную, см. A3);
- `BOT_TOKEN` — токен (или оставьте заглушку и впишите в `.env` позже).

Инстанс сам поставит Docker, соберёт образ и запустит контейнер с `--restart unless-stopped`.

### A3. Ручной запуск (если без Git)

С локальной машины скопируйте папку на инстанс и соберите:

```bash
# на локальной машине
scp -i key.pem -r fotoreportcu-bot ec2-user@<EC2_IP>:/opt/

# по SSH на инстансе
sudo dnf install -y docker && sudo systemctl enable --now docker
cd /opt/fotoreportcu-bot
cp .env.example .env && nano .env        # впишите BOT_TOKEN
sudo docker build -t fotoreportcu-bot:latest .
sudo docker volume create botdata
sudo docker run -d --name fotoreportcu-bot \
  --restart unless-stopped --env-file .env -v botdata:/data \
  fotoreportcu-bot:latest
```

### A4. Проверка

```bash
sudo docker ps
sudo docker logs -f fotoreportcu-bot     # должно быть "Start polling"
# health внутри контейнера:
sudo docker exec fotoreportcu-bot curl -fsS http://127.0.0.1:3000/health
```

Напишите боту в Telegram — он должен ответить.

---

## Вариант B — ECS Fargate (без управления сервером)

Дороже, но не нужно админить EC2.

### B1. Подготовить ECR и залить образ

```bash
AWS_REGION=eu-central-1
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REPO=fotoreportcu-bot

aws ecr create-repository --repository-name $REPO --region $AWS_REGION || true
aws ecr get-login-password --region $AWS_REGION \
  | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

docker build -t $REPO:latest .
docker tag $REPO:latest $ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$REPO:latest
docker push $ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$REPO:latest
```

### B2. Токен в SSM Parameter Store

```bash
aws ssm put-parameter --region $AWS_REGION \
  --name /fotoreportcu-bot/BOT_TOKEN --type SecureString \
  --value "123456:ABC..."
```
Убедитесь, что у `ecsTaskExecutionRole` есть право `ssm:GetParameters` на этот параметр.

### B3. Зарегистрировать задачу

В `deploy/ecs-task-definition.json` замените `<ACCOUNT_ID>` и `<REGION>`, затем:

```bash
aws ecs register-task-definition --region $AWS_REGION \
  --cli-input-json file://deploy/ecs-task-definition.json
```

### B4. Создать кластер и сервис

```bash
aws ecs create-cluster --cluster-name fotoreportcu --region $AWS_REGION

aws ecs create-service --region $AWS_REGION \
  --cluster fotoreportcu \
  --service-name fotoreportcu-bot \
  --task-definition fotoreportcu-bot \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[<SUBNET_ID>],securityGroups=[<SG_ID>],assignPublicIp=ENABLED}"
```

- `assignPublicIp=ENABLED` и публичная подсеть — чтобы был выход в интернет к Telegram (или приватная подсеть + NAT Gateway).
- Security Group: входящие правила не нужны, только исходящий трафик (443).

Логи — в CloudWatch группе `/ecs/fotoreportcu-bot`.

---

## Заметки

- **Стоимость:** EC2 `t3.small` около ~15 USD/мес (on-demand). Fargate 0.5 vCPU/1 ГБ дороже при постоянной работе.
- **Почему не Lambda:** polling + LibreOffice не вписываются в модель коротких событий и лимиты размера.
- **Безопасность токена:** не коммитьте `.env` в Git (он уже в `.gitignore`/`.dockerignore`). На Fargate токен идёт через SSM.
- **Обновление:** EC2 — `git pull && docker build && docker rm -f ... && docker run ...`; Fargate — залить новый образ в ECR и `aws ecs update-service --force-new-deployment`.
- **Очистка:** генерируемые файлы короткоживущие; том `/data` можно периодически чистить.
