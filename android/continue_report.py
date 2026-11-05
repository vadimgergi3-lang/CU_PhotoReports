# -*- coding: utf-8 -*-
"""Продолжение ранее начатого фото-отчёта.

Разбирает присланный пользователем .docx (собранный этим же ботом
по одному из шаблонов) и восстанавливает состояние:
  * какой шаблон использован (по последовательности подписей ячеек);
  * метаданные (PLACE/GOODS/SCOPE/DATE/No./подпись);
  * список контейнеров;
  * какие ячейки уже заполнены фото (извлекаем их в рабочую папку).

Дальше бот продолжает сбор фото с первой пустой ячейки.
"""

import os

from docx import Document
from docx.oxml.ns import qn

import config
from docgen import build_slots


class ContinueError(Exception):
    """Ошибка разбора присланного файла (с понятным текстом для пользователя)."""


INTRO_LEN = 24  # во всех шаблонах вводный блок = 24 фото

_CONTENT_TYPE_EXT = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/bmp": "bmp",
    "image/tiff": "tiff",
    "image/x-emf": "emf",
    "image/x-wmf": "wmf",
}


def _tpl_intro_captions(tpl):
    """Развёрнутый список подписей вводного блока конкретного шаблона."""
    caps = []
    for caption, count in tpl.get("intro", []):
        caps.extend([caption] * count)
    return caps


def _cell_image_rid(cell):
    """Возвращает r:embed первой картинки в ячейке или None."""
    blips = cell._tc.findall(".//" + qn("a:blip"))
    for b in blips:
        rid = b.get(qn("r:embed")) or b.get(qn("r:link"))
        if rid:
            return rid
    return None


def _collect_photo_cells(doc):
    """Идёт по всем таблицам фото и возвращает упорядоченный список
    (caption, rid) для каждой непустой ячейки. rid=None — ячейка пустая.

    Структура таблицы: чётные ряды — фото, нечётные — подписи.
    Ячейки-заполнители (пустая подпись) пропускаются.
    """
    result = []
    for table in doc.tables:
        rows = table.rows
        if len(rows) < 2 or len(table.columns) != 2:
            continue  # не похоже на таблицу фото
        pairs = len(rows) // 2
        for pi in range(pairs):
            photo_row = rows[pi * 2]
            cap_row = rows[pi * 2 + 1]
            for col in range(2):
                caption = cap_row.cells[col].text.strip()
                if not caption:
                    continue  # ячейка-заполнитель
                rid = _cell_image_rid(photo_row.cells[col])
                result.append((caption, rid))
    return result


def _parse_containers_line(doc):
    """Читает строку метаданных «CONTAINER: ...» → список номеров/идентификаторов.

    Числовой режим записан как «1, 2, 3»; серийный — как «MSKU...; MRKU...».
    """
    for p in doc.paragraphs:
        raw = p.text.strip()
        if raw.upper().startswith("CONTAINER:"):
            val = raw.split(":", 1)[1].replace("\t", " ").strip()
            parts = [x.strip() for x in val.replace(",", ";").split(";")]
            return [x for x in parts if x]
    return []


def _parse_meta(doc, base_meta):
    """Читает метаданные из тела документа, накладывая поверх base_meta."""
    meta = dict(base_meta)
    labels = {
        "PLACE OF INSPECTION": "place",
        "DESCRIPTION OF GOODS": "goods",
        "SCOPE OF SERVICES": "scope",
        "DATE OF INSPECTION": "date",
    }
    for p in doc.paragraphs:
        raw = p.text.strip()
        if not raw:
            continue
        if raw.startswith("PHOTO REPORT No."):
            meta["report_no"] = raw.split("No.", 1)[1].strip()
            continue
        for label, key in labels.items():
            if raw.startswith(label):
                val = raw[len(label):].lstrip(": \t").strip()
                meta[key] = val
                break
        if "CONTROL UNION" in raw.upper() and ("," in raw or "\t" in raw) \
                and not raw.startswith("PHOTO REPORT"):
            # подпись: «дата <tab> CONTROL UNION ...»
            footer = raw.replace("\t", "   ")
            if "CONTROL UNION" in footer:
                meta["footer"] = footer
    return meta


def _match_template(captions):
    """По полной последовательности подписей определяет (template_key, n_containers).

    Поддерживает как шаблоны с вводным блоком, так и без него (intro = []).
    Совпадением считается только точное равенство всей последовательности
    (вводный блок + N ровно повторяющихся блоков контейнера).
    """
    for key, tpl in config.TEMPLATES.items():
        intro_exp = _tpl_intro_captions(tpl)
        il = len(intro_exp)
        if captions[:il] != intro_exp:
            continue
        rest = captions[il:]
        per = tpl["per_container"]
        pl = len(per)
        if pl == 0:
            if len(rest) == 0:
                return key, 0
            continue
        if len(rest) == 0 or len(rest) % pl != 0:
            continue
        n = len(rest) // pl
        if n >= 1 and all(rest[i * pl:(i + 1) * pl] == per for i in range(n)):
            return key, n
    raise ContinueError(
        "Не удалось сопоставить файл ни с одним из шаблонов в памяти. "
        "Похоже, структура отчёта была изменена вручную, либо это не отчёт этого бота."
    )


def parse_report(docx_path, user_dir):
    """Разбирает .docx и возвращает dict с состоянием для продолжения.

    Возвращает: template_key, meta, containers, slots, photos, index, filled, total.
    Бросает ContinueError с понятным текстом при проблемах.
    """
    try:
        doc = Document(docx_path)
    except Exception as e:  # noqa: BLE001
        raise ContinueError(
            "Не удалось открыть файл как Word-документ. Пришлите отчёт в формате .docx."
        ) from e

    cells = _collect_photo_cells(doc)
    if not cells:
        raise ContinueError(
            "В файле не найдено таблиц с фото. Это точно отчёт, созданный этим ботом?"
        )
    captions = [c for c, _ in cells]
    template_key, n = _match_template(captions)
    tpl = config.TEMPLATES[template_key]

    # контейнеры: берём из строки метаданных CONTAINER; если их не N — нумеруем 1..N
    parsed_conts = _parse_containers_line(doc)
    if len(parsed_conts) == n:
        containers = parsed_conts
    else:
        containers = [str(i) for i in range(1, n + 1)]

    meta = _parse_meta(doc, tpl["meta"])
    slots = build_slots(tpl, containers)
    if len(slots) != len(cells):
        raise ContinueError(
            "Структура файла не совпала с ожидаемой по шаблону. Попробуйте начать заново."
        )

    # извлекаем уже вставленные фото в рабочую папку
    os.makedirs(user_dir, exist_ok=True)
    photos = {}
    for slot, (_cap, rid) in zip(slots, cells):
        if not rid:
            continue
        try:
            part = doc.part.related_parts[rid]
        except KeyError:
            continue
        ext = _CONTENT_TYPE_EXT.get(getattr(part, "content_type", ""), "img")
        dest = os.path.join(user_dir, f"{slot['id']}.{ext}")
        with open(dest, "wb") as f:
            f.write(part.blob)
        photos[slot["id"]] = dest

    # индекс — первая пустая ячейка
    index = len(slots)
    for i, slot in enumerate(slots):
        if slot["id"] not in photos:
            index = i
            break

    return {
        "template_key": template_key,
        "meta": meta,
        "containers": containers,
        "slots": slots,
        "photos": photos,
        "index": index,
        "filled": len(photos),
        "total": len(slots),
    }
