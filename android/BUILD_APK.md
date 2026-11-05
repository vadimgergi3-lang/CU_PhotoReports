# APK — полноценное offline-приложение CONTROL UNION (фото-отчёты)

Версия **2.0** — без Telegram. Полный UI на Kivy:

- Новый отчёт / Продолжить из .docx / Восстановить последний
- Выбор шаблона (те же 6 шаблонов из config.py)
- Редактирование метаданных
- Контейнеры (количество или серийные номера)
- Пошаговый сбор фото (галерея + камера)
- Генерация **точно такого же** .docx (logo, шрифты, размеры, merged captions)
- Отправка/шаринг готового файла

Целевой Android: **13 и выше** (minSdk 33, target 34).

## Сборка

### Способ A — GitHub Actions

1. Залейте проект в репозиторий (вместе с `.github/workflows`).
2. Обновите workflow под новые requirements (без aiogram/pydantic/Rust).
3. Actions → build-apk → Run workflow → скачайте APK.

### Способ B — Linux / WSL2

```bash
sudo apt update && sudo apt install -y \
  git zip unzip openjdk-17-jdk autoconf libtool pkg-config \
  zlib1g-dev libncurses-dev cmake libffi-dev libssl-dev build-essential ccache

pip install --user buildozer Cython==0.29.36

cd fotoreportcu-bot   # корень проекта
bash android/prepare.sh
cd android
buildozer -v android debug
# готовый файл: android/bin/fotoreportcu-2.0.0-*-debug.apk
```

Первая сборка долгая (скачивает SDK/NDK).

## Установка

1. Перекиньте `.apk` на телефон.
2. Разрешите «Установка из неизвестных источников».
3. Установите. При первом запуске разрешите доступ к фото/камере.

## Важно

- Шаблоны и оформление документа **идентичны** боту — используется тот же `docgen.py` + `config.py`.
- Состояние незавершённого отчёта сохраняется в приватном каталоге приложения.
- «Продолжить из .docx» разбирает ранее созданный отчёт через `continue_report.py`.
