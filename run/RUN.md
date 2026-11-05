# Запуск бота без Docker: ПК и Android (Termux)

Две версии локального запуска одного и того же кода — без контейнеров, напрямую через Python.

Бот работает в режиме long-polling — ему нужен только интернет, входящие порты не нужны.

---

## Версия 1 — ПК (Windows / Linux / macOS)

**Нужно:** Python 3.10+ и (опционально) LibreOffice — для PDF-предпросмотра.

### Windows
1. Установите Python с python.org (галочка «Add to PATH»).
2. Дважды кликните `run\run.bat` (или запустите его из командной строки).
3. При первом запуске создастся `.env` — откройте его, впишите `BOT_TOKEN=...`, запустите снова.

### Linux / macOS
```bash
cd fotoreportcu-bot
bash run/run.sh
# при первом запуске: впишите BOT_TOKEN в .env и запустите снова
```

Скрипт сам: создаст `.venv`, поставит зависимости, проверит LibreOffice и запустит бота.

**LibreOffice (для PDF-предпросмотра, необязательно):**
- Ubuntu/Debian: `sudo apt install libreoffice-writer`
- macOS: `brew install --cask libreoffice`
- Windows: установщик с libreoffice.org

Без LibreOffice бот работает полностью, но отдаёт документ в формате Word (.docx) вместо PDF.

---

## Версия 2 — Android через Termux

**Важно:** на Android LibreOffice недоступен, поэтому PDF-предпросмотра не будет — бот отдаёт Word (.docx). Всё остальное (фото, шапка, генерация документа) работает.

### 1. Установите Termux
Ставьте из **F-Droid** (версия из Google Play устарела и не работает). Желательно также **Termux:API**.

### 2. Скопируйте проект в Termux
```bash
# доступ к памяти телефона (один раз)
termux-setup-storage

# распакуйте zip в телефоне и скопируйте папку, например:
cp -r ~/storage/downloads/fotoreportcu-bot ~/
cd ~/fotoreportcu-bot
```
(Альтернатива: `pkg install git && git clone <ваш-репо>`.)

### 3. Настройка (один раз)
```bash
bash run/termux-setup.sh
nano .env        # впишите BOT_TOKEN=...  (Ctrl+O, Enter, Ctrl+X)
```

### 4. Запуск
```bash
bash run/run-termux.sh
```
- Чтобы бот не засыпал при выключенном экране, скрипт берёт `termux-wake-lock`.
- Для работы в фоне:  `nohup bash run/run-termux.sh &`  (логи в `nohup.out`).
- Остановка: Ctrl+C, затем `termux-wake-unlock`.

### Советы для Termux
- Отключите оптимизацию батареи для Termux (Настройки Android → Приложения → Termux → Батарея → Без ограничений), иначе система может убить процесс.
- Pillow ставится из пакета Termux (`python-pillow`), чтобы не компилировать его вручную — это уже учтено в `termux-setup.sh`.

---

## Общее

| | ПК | Android / Termux |
|---|---|---|
| PDF-предпросмотр | да (если стоит LibreOffice) | нет — отдаёт Word |
| Генерация документа | да | да |
| FSM-состояние | в памяти (теряется при рестарте) | то же |
| Токен | в файле `.env` | в файле `.env` |

`.env` не коммитится в Git (он в `.gitignore`). Держите токен в секрете.
