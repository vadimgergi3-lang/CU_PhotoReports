# -*- coding: utf-8 -*-
"""
Конфигурация бота и схемы шаблонов фото-отчётов.

Здесь описана вся "начинка" отчёта:
  * INTRO_BLOCK      — фиксированный вводный блок (меняются только фото);
  * PER_CONTAINER    — набор из 8 фото на каждый контейнер (единый порядок);
  * DEFAULT_META     — дефолтные метаданные из шаблона.

Чтобы добавить новый тип шаблона — скопируйте блок в TEMPLATES с новым ключом.
"""

import os

# =========================================================================
# ТОКЕН БОТА
# Получите у @BotFather и подставьте сюда или в переменную окружения BOT_TOKEN.
# =========================================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# =========================================================================
# ХРАНИЛИЩЕ СОСТОЯНИЯ (FSM)
# USE_REDIS=1  — состояние диалога хранится в Redis и переживает перезапуск бота.
# USE_REDIS=0  — хранение в памяти (при перезапуске незавершённые отчёты теряются).
# =========================================================================
USE_REDIS = os.getenv("USE_REDIS", "0") == "1"
# Формат: redis://[:password@]host:port/db   или  unix://[:password@]/path?db=0
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Рабочие папки (создаются автоматически).
# На хостах с постоянным хранилищем (например Amvera — /data)
# укажите пути через переменные WORK_DIR / OUT_DIR,
# чтобы файлы не терялись при пересборке (напр. /data/work, /data/out).
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.getenv("WORK_DIR", os.path.join(BASE_DIR, "work"))
OUT_DIR = os.getenv("OUT_DIR", os.path.join(BASE_DIR, "out"))

# Логотип предприятия для колонтитула/шапки документа (CONTROL UNION).
# Можно переопределить переменной LOGO_PATH.
LOGO_PATH = os.getenv("LOGO_PATH", os.path.join(BASE_DIR, "assets", "logo.png"))


# =========================================================================
# СХЕМЫ ШАБЛОНОВ
# =========================================================================
# Вводный блок — один на весь отчёт, подписи фиксированы, меняются только фото.
# Каждый элемент: (подпись, количество фото).
INTRO_BLOCK = [
    ("Condition of container", 6),
    ("Condition of flexitank", 5),
    ("View of hose connection", 1),
    ("Loading process", 4),
    ("Sampling point", 2),
    ("Sampling", 2),
    ("Loaded flexitank", 4),
]

# Набор фото на ОДИН контейнер — единый порядок (8 фото).
PER_CONTAINER = [
    "Loaded flexitank",
    "Loaded flexitank",
    "Flexitank number",
    "Control Union valve seal",
    "Line seal on container",
    "Factory seal on container",
    "Control Union seal on container",
    "Loaded container with seals",
]

# Дефолтные метаданные (из вашего шаблона). Пользователь может оставить или изменить.
DEFAULT_META = {
    "report_no": "10126-26",
    "place": "GIDROSAND LLC, VLASIVKA, KIROVOGRAD REGION",
    "goods": "RBDW SUNFLOWER OIL",
    "scope": "SUPERVISION OF OIL LOADING INTO FLEXITANKS, WEIGHT CONTROL AND SAMPLING",
    "date": "04-05.03.2026",
    "footer": "March, 05, 2026   CONTROL UNION UKRAINE",
}

# ------------------------- ШАБЛОН 2 -------------------------
# Вводный блок такой же (INTRO_BLOCK). На контейнер — 10 фото.
PER_CONTAINER_2 = [
    "Loaded flexitank",
    "Loaded flexitank",
    "Flexitank number",
    "Valve seals",
    "Factory valve seal",
    "Control Union valve seal",
    "Factory seal on container",
    "Line seal on container",
    "Control Union seal on container",
    "Loaded container with seals",
]

DEFAULT_META_2 = {
    "report_no": "9960-25",
    "place": "GIDROSAND LLC, VLASIVKA, KIROVOGRAD REGION",
    "goods": "RBDW SUNFLOWER OIL",
    "scope": "SUPERVISION OF OIL LOADING INTO FLEXITANKS, WEIGHT CONTROL AND SAMPLING",
    "date": "13-16.11.2025",
    "footer": "November, 16, 2025   CONTROL UNION UKRAINE",
}

# ------------------------- ШАБЛОН «Агриойл/Авто (стикер+проба)» -------------------------
# Источник: Photo_Report_10208-26. Вводный блок тот же (INTRO_BLOCK).
# На контейнер — 12 фото (добавлены Sample + Label).
PER_CONTAINER_AGRIOIL = [
    "Loaded flexitank",
    "Loaded flexitank",
    "Flexitank number",
    "Valve seals",
    "Factory valve seal",
    "Control Union valve seal",
    "Sample",
    "Label",
    "Line seal on container",
    "Factory seal on container",
    "Control Union seal on container",
    "Loaded container with seals",
]

DEFAULT_META_AGRIOIL = {
    "report_no": "10208-26",
    "place": "GIDROSAND LLC, VLASIVKA, KIROVOGRAD REGION",
    "goods": "SUNFLOWER OIL REFINED DEODORIZED CHILLED GRADE P",
    "scope": "SUPERVISION OF OIL LOADING INTO FLEXITANKS, WEIGHT CONTROL AND SAMPLING",
    "date": "17-18.04.2026",
    "footer": "April, 18, 2026   CONTROL UNION UKRAINE",
}

# ------------------------- ШАБЛОН «10 фото ЖД +стикер» -------------------------
# Источник: Photo_Report_10234. На контейнер — 10 фото (с Label).
PER_CONTAINER_ZD10 = [
    "Loaded flexitank",
    "Loaded flexitank",
    "Flexitank number",
    "Valve seal",
    "Label",
    "Control Union valve seal",
    "Line seal on container",
    "Factory seal on container",
    "Control Union seal on container",
    "Loaded container with seals",
]

DEFAULT_META_ZD10 = {
    "report_no": "10234",
    "place": "GIDROSAND LLC, VLASIVKA, KIROVOGRAD REGION",
    "goods": "RBDW SUNFLOWER OIL",
    "scope": "SUPERVISION OF OIL LOADING INTO FLEXITANKS, WEIGHT CONTROL AND SAMPLING",
    "date": "03-04.06.2026",
    "footer": "June, 04, 2026   CONTROL UNION UKRAINE",
}

# ------------------------- ШАБЛОН «Авто 12 фото стикер+жд пломба» -------------------------
# Источник: Photo_Report_10127 (внутри No. 10192). На контейнер — 12 фото.
PER_CONTAINER_AUTO12 = [
    "Loaded flexitank",
    "Loaded flexitank",
    "Flexitank number",
    "Valve seals",
    "Control Union valve seal",
    "Factory valve seal",
    "Label",
    "Factory seal on container",
    "Factory seal on container",
    "Line seal on container",
    "Control Union seal on container",
    "Loaded container with seals",
]

DEFAULT_META_AUTO12 = {
    "report_no": "10192",
    "place": "GIDROSAND LLC, VLASIVKA, KIROVOGRAD REGION",
    "goods": "RBDW SUNFLOWER OIL",
    "scope": "SUPERVISION OF OIL LOADING INTO FLEXITANKS, WEIGHT CONTROL AND SAMPLING",
    "date": "30.04.2026 – 01.05.2026",
    "footer": "May, 02, 2026   CONTROL UNION UKRAINE",
}

# ------------------------- ШАБЛОН «Viktor&K (14 фото, без вводного блока)» -------------------------
# Источник: Photo_Report_10504. ОТЛИЧАЕТСЯ от остальных:
#   * НЕТ общего вводного блока (intro = []);
#   * на каждый контейнер — 14 фото (7 рядов по 2);
#   * у ПЕРВОГО и ПОСЛЕДНЕГО ряда подпись ОБЩАЯ (ячейка объединена на 2 колонки):
#       ряд 0  → «Condition of container»
#       ряд 6  → «Weighing of truck, tare and gross weight»
#   Индексы этих рядов перечислены в merged_caption_rows.
# Полный список из 14 подписей (по 2 на ряд). Для объединённых рядов подпись
# продублирована намеренно — так создаётся 14 слотов под фото, а визуально
# подпись объединяется в одну ячейку (см. merged_caption_rows).
PER_CONTAINER_VIKTORK = [
    "Condition of container", "Condition of container",                       # ряд 0 (объединён)
    "Condition of container", "Condition of container",                       # ряд 1
    "Condition of flexitank", "Flexitank number",                             # ряд 2
    "Loading", "Loaded flexitank",                                            # ряд 3
    "Control Union seal (flexitank valve)", "Factory seal (container door)",   # ряд 4
    "Control Union seal (container door)", "Carrier seal (container door)",    # ряд 5
    "Weighing of truck, tare and gross weight",                               # ряд 6 (объединён)
    "Weighing of truck, tare and gross weight",
]

DEFAULT_META_VIKTORK = {
    "report_no": "10504",
    "place": 'PE "Viktor&K", VLASIVKA, KIROVOGRAD REGION, UKRAINE',
    "goods": "RBD SUNFLOWER OIL",
    "scope": "SUPERVISION OF OIL LOADING INTO FLEXITANKS, WEIGHT CONTROL AND SAMPLING",
    "date": "28.10.2026 – 30.10.2026",
    "footer": "April 20, 2026   CONTROL UNION UKRAINE",
}


# Реестр типов шаблонов. Ключ — внутренний id, title — текст на кнопке.
TEMPLATES = {
    "flexitank": {
        "title": "8 фото ж/д без всего",
        "intro": INTRO_BLOCK,
        "per_container": PER_CONTAINER,
        "meta": DEFAULT_META,
    },
    "flexitank_v2": {
        "title": "10 фото авто без всего",
        "intro": INTRO_BLOCK,
        "per_container": PER_CONTAINER_2,
        "meta": DEFAULT_META_2,
    },
    "agrioil_auto": {
        "title": "Агриойл/Авто(стикер+проба)",
        "intro": INTRO_BLOCK,
        "per_container": PER_CONTAINER_AGRIOIL,
        "meta": DEFAULT_META_AGRIOIL,
    },
    "zd_10_sticker": {
        "title": "10 фото ЖД +стикер",
        "intro": INTRO_BLOCK,
        "per_container": PER_CONTAINER_ZD10,
        "meta": DEFAULT_META_ZD10,
    },
    "auto_12_sticker": {
        "title": "Авто 12 фото стикер+жд пломба",
        "intro": INTRO_BLOCK,
        "per_container": PER_CONTAINER_AUTO12,
        "meta": DEFAULT_META_AUTO12,
    },
    "viktork_14": {
        "title": "Viktor&K 14 фото (без вводного)",
        "intro": [],                       # вводного блока нет
        "per_container": PER_CONTAINER_VIKTORK,
        "meta": DEFAULT_META_VIKTORK,
        # индексы рядов (0-based, ряд = 2 фото), у которых подпись объединена
        "merged_caption_rows": [0, 6],
    },
}
