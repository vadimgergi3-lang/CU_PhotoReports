# -*- coding: utf-8 -*-
"""Генератор фото-отчёта .docx на основе схемы шаблона.

Воспроизводит оформление фирменного шаблона CONTROL UNION:
  * логотип предприятия в верхнем колонтитуле (повторяется на каждой странице);
  * в нижнем колонтитуле (на каждой странице): «PHOTO REPORT No. ...   Page X of Y»;
  * подпись «Month, DD, YYYY   CONTROL UNION UKRAINE» — ТОЛЬКО в конце документа (в теле).
Каждая страница фото — обычно 6 снимков; новый контейнер всегда начинается с новой страницы.
"""

import os
import re
import tempfile

from docx import Document
from docx.shared import Inches, Pt, Mm, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_BREAK
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ROW_HEIGHT_RULE
from docx.enum.section import WD_SECTION
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

try:
    import config as _config
    _LOGO_PATH = getattr(_config, "LOGO_PATH", None)
except Exception:  # noqa: BLE001
    _LOGO_PATH = None

# Логотип по умолчанию — assets/logo.png рядом с модулем.
if not _LOGO_PATH:
    _LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo.png")


# -------------------------------------------------------------------------
# Построение списка слотов (один слот = одно фото).
# Этот же порядок использует бот, когда ведёт пользователя по фото.
# -------------------------------------------------------------------------
# Максимальный размер ячейки с фото (см): картинка любого размера
# вписывается в этот бокс с сохранением пропорций.
PHOTO_CELL_W_CM = 8.9   # ширина ячейки с фото
PHOTO_CELL_H_CM = 6.5   # высота ячейки с фото
# Кадр самого изображения внутри ячейки (ландшафт). Картинка кроп-заполнением
# заполняет этот кадр целиком (лишнее по краям обрезается, пропорции не искажаются).
# Вертикальные фото предварительно поворачиваются влево на 90°, т.е. их
# «портретный» кадр 6.47×8.63 после поворота превращается в этот ландшафтный 8.63×6.47.
PHOTO_IMG_W_CM = 8.63
PHOTO_IMG_H_CM = 6.47


def _prepare_photo(img_path, frame_w_cm=PHOTO_IMG_W_CM, frame_h_cm=PHOTO_IMG_H_CM):
    """Готовит картинку под ячейку и возвращает путь ко временному файлу.

    1) Учёт EXIF-ориентации.
    2) Вертикальные (высота > ширины) — поворот влево на 90° (против часовой).
    3) Кроп-заполнение ландшафтного кадра frame_w×frame_h без искажения пропорций
       (лишнее по краям обрезается от центра).
    После этого картинку можно вставлять с размером frame_w×frame_h — она заполнит кадр целиком.
    """
    from PIL import Image, ImageOps
    # Decode only a bounded thumbnail; do not embed full-resolution phone photos.
    with Image.open(img_path) as source:
        source.draft("RGB", (1600, 1600))
        im = ImageOps.exif_transpose(source)
        try:
            im.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            if im.mode not in ("RGB", "L"):
                converted = im.convert("RGB")
                im.close()
                im = converted
            if im.height > im.width:
                rotated = im.rotate(90, expand=True)
                im.close()
                im = rotated
            target_size = (1200, max(1, round(1200 * frame_h_cm / frame_w_cm)))
            fitted = ImageOps.fit(im, target_size, method=Image.Resampling.LANCZOS)
            try:
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                    tmp_path = tmp.name
                try:
                    fitted.save(tmp_path, "JPEG", quality=85)
                except BaseException:
                    os.unlink(tmp_path)
                    raise
            finally:
                fitted.close()
        finally:
            im.close()
    return tmp_path


# -------------------------------------------------------------------------
# Помощники отображения контейнеров
# -------------------------------------------------------------------------
def _cont_heading(name):
    """Заголовок блока контейнера. Если задано только число
    (режим «количество») — показываем «CONTAINER N», иначе — серийный номер."""
    s = str(name).strip()
    return f"CONTAINER {s}" if s.isdigit() else s


def _containers_meta(containers):
    """Строка метаданных CONTAINER. Для числового режима — «1, 2, 3»,
    для серийных номеров — через «; »."""
    vals = [str(c).strip() for c in containers]
    if vals and all(v.isdigit() for v in vals):
        return ", ".join(vals)
    return "; ".join(vals)


def build_slots(template, containers):
    """Возвращает упорядоченный список слотов.

    Каждый слот: dict(id, section, caption, container).
    """
    slots = []
    idx = 0
    for caption, count in template["intro"]:
        for _ in range(count):
            slots.append({
                "id": f"intro_{idx}",
                "section": "intro",
                "caption": caption,
                "container": None,
            })
            idx += 1
    for ci, cont in enumerate(containers):
        for j, caption in enumerate(template["per_container"]):
            slots.append({
                "id": f"cont_{ci}_{j}",
                "section": "container",
                "caption": caption,
                "container": cont,
            })
    return slots


# -------------------------------------------------------------------------
# Низкоуровневые помощники
# -------------------------------------------------------------------------
def _add_page_number_field(paragraph):
    """Вставляет авто-поле номера страницы (PAGE)."""
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(end)


def _add_numpages_field(paragraph):
    """Вставляет авто-поле общего числа страниц (NUMPAGES)."""
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " NUMPAGES "
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(end)


def _no_split_row(row):
    """Запрещает разрыв строки таблицы между страницами."""
    trPr = row._tr.get_or_add_trPr()
    trPr.append(OxmlElement("w:cantSplit"))


def _page_break(doc):
    """Жёсткий разрыв страницы."""
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def _spacer(doc, pts):
    """Маленький вертикальный отступ без лишней пустой строки."""
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.line_spacing = 1.0
    p.add_run("").font.size = pts
    return p


def _set_cell_borders(cell):
    tcPr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "000000")
        borders.append(el)
    tcPr.append(borders)


def _caption_cell(cell, text):
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.line_spacing = 1.0
    run = p.add_run(text or "")
    run.font.size = Pt(9)
    run.font.bold = True
    _set_cell_borders(cell)


def _photo_cell(cell, img_path):
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.line_spacing = 1.0
    if img_path and os.path.isfile(img_path):
        try:
            proc = _prepare_photo(img_path)
            try:
                # картинка заполняет кадр 8.63×6.47 см целиком (без белых полей)
                p.add_run().add_picture(proc, width=Cm(PHOTO_IMG_W_CM), height=Cm(PHOTO_IMG_H_CM))
            finally:
                try:
                    os.remove(proc)
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            p.add_run("[фото не вставлено]")
    _set_cell_borders(cell)


def _add_photo_table(doc, chunk, photos, merge_rows=None):
    """chunk — список слотов; строит таблицу 2 колонки: фото / подпись ниже.

    Ячейки с фото фиксированного размера (не больше 8.9×6.5 см), таблица
    выровнена по центру листа. Ячейки с подписями свой размер не меняют.

    merge_rows — множество индексов рядов (0-based, ряд = пара из 2 фото),
    у которых ячейки ПОДПИСИ объединяются в одну на всю ширину (фото сверху
    остаются двумя отдельными ячейками). Для таких рядов берётся подпись
    первого слота пары.
    """
    merge_rows = set(merge_rows or ())
    pairs = [chunk[i:i + 2] for i in range(0, len(chunk), 2)]
    table = doc.add_table(rows=len(pairs) * 2, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    table.allow_autofit = False
    for pi, pair in enumerate(pairs):
        photo_row = table.rows[pi * 2]
        cap_row = table.rows[pi * 2 + 1]
        _no_split_row(photo_row)
        _no_split_row(cap_row)
        # высота ряда с фото — ровно 6.5 см (не больше), ряд подписи не трогаем
        photo_row.height = Cm(PHOTO_CELL_H_CM)
        photo_row.height_rule = WD_ROW_HEIGHT_RULE.EXACTLY
        # фото: всегда две отдельные ячейки
        for col in range(2):
            photo_row.cells[col].width = Cm(PHOTO_CELL_W_CM)
            if col < len(pair):
                _photo_cell(photo_row.cells[col], photos.get(pair[col]["id"]))
            else:
                _photo_cell(photo_row.cells[col], None)
        # подпись: объединённая на всю ширину ИЛИ две отдельные
        if pi in merge_rows and len(pair) == 2:
            merged = cap_row.cells[0].merge(cap_row.cells[1])
            _caption_cell(merged, pair[0]["caption"])
        else:
            for col in range(2):
                cap_row.cells[col].width = Cm(PHOTO_CELL_W_CM)
                if col < len(pair):
                    _caption_cell(cap_row.cells[col], pair[col]["caption"])
                else:
                    _caption_cell(cap_row.cells[col], "")
    return table


# -------------------------------------------------------------------------
# Колонтитулы: логотип (верх) + «PHOTO REPORT No. ... Page X of Y» (низ)
# -------------------------------------------------------------------------
def _put_logo(header):
    """Логотип предприятия в первом абзаце колонтитула."""
    p = header.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    if os.path.isfile(_LOGO_PATH):
        try:
            p.add_run().add_picture(_LOGO_PATH, width=Inches(3.3))
            return
        except Exception:  # noqa: BLE001
            pass
    # фолбэк, если логотип недоступен
    r = p.add_run("CONTROL UNION")
    r.font.bold = True
    r.font.size = Pt(16)


def _setup_page(doc):
    """Формат A4 + компактные поля, чтобы на странице помещалось 6 фото."""
    section = doc.sections[0]
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.top_margin = Inches(0.85)
    section.bottom_margin = Inches(0.75)
    # боковые поля — уже, чтобы вмещались 2 ячейки по 8.9 см (= 17.8 см)
    section.left_margin = Cm(1.3)
    section.right_margin = Cm(1.3)


def _footer_paragraph(footer, report_no):
    """Низ страницы (как в фирменном шаблоне):
    «PHOTO REPORT No. {report_no}   Page {PAGE} of {NUMPAGES}» по центру."""
    p = footer.paragraphs[0]
    p.text = ""
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r1 = p.add_run(f"PHOTO REPORT No. {report_no} ")
    r1.font.size = Pt(10)
    r1.font.bold = True
    r2 = p.add_run("   Page ")
    r2.font.size = Pt(10)
    _add_page_number_field(p)
    r3 = p.add_run(" of ")
    r3.font.size = Pt(10)
    _add_numpages_field(p)


def _build_headers(doc, report_no):
    """Логотип на всех страницах (без бегущего текста — как в оригинале)."""
    section = doc.sections[0]
    # в фирменном шаблоне колонтитулы одинаковы на всех страницах
    section.different_first_page_header_footer = False
    _put_logo(section.header)


def _build_footer(doc, report_no):
    """Нижний колонтитул на всех страницах: PHOTO REPORT No. + Page X of Y."""
    section = doc.sections[0]
    _footer_paragraph(section.footer, report_no)


def _begin_final_section(doc):
    """Открывает финальную (последнюю) секцию для блока подписи.

    Колонтитулы (логотип сверху и «PHOTO REPORT No. ... Page X of Y» снизу)
    наследуются от предыдущей секции — показываются на всех
    страницах, включая последнюю (как в оригинале).
    """
    sec = doc.add_section(WD_SECTION.NEW_PAGE)
    sec.different_first_page_header_footer = False
    return sec


def _signature(doc, footer_text):
    """Подпись ТОЛЬКО в самом конце документа (в теле): дата <...> CONTROL UNION UKRAINE."""
    if not footer_text:
        return
    doc.add_paragraph()
    p = doc.add_paragraph()
    tabs = p.paragraph_format.tab_stops
    tabs.add_tab_stop(Inches(6.5), WD_TAB_ALIGNMENT.RIGHT)
    parts = re.split(r"\s{2,}", footer_text.strip(), maxsplit=1)
    left = parts[0]
    right = parts[1] if len(parts) == 2 else ""
    r1 = p.add_run(left)
    r1.font.size = Pt(11)
    r1.font.bold = True
    if right:
        r1.add_tab()
        r2 = p.add_run(right)
        r2.font.size = Pt(11)
        r2.font.bold = True


def _title(doc, report_no):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(4)
    run = p.add_run(f"PHOTO REPORT No. {report_no}")
    run.font.size = Pt(14)
    run.font.bold = True


def _meta_line(doc, label, value):
    """Строка метаданных: LABEL:\tзначение (таб выравнивает колонку)."""
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(1)
    pf.line_spacing = 1.0
    tabs = pf.tab_stops
    tabs.add_tab_stop(Inches(2.4), WD_TAB_ALIGNMENT.LEFT)
    r1 = p.add_run(f"{label}:")
    r1.font.bold = True
    r1.font.size = Pt(10)
    r1.add_tab()
    r2 = p.add_run(value or "")
    r2.font.size = Pt(10)


# -------------------------------------------------------------------------
# Главная функция генерации
# -------------------------------------------------------------------------
def generate_report(template, meta, containers, photos, out_path):
    """Собирает готовый .docx.

    template   — схема шаблона из config.TEMPLATES
    meta       — dict метаданных (report_no, place, goods, scope, date, footer)
    containers — список номеров контейнеров
    photos     — dict slot_id -> путь к файлу фото
    out_path   — куда сохранить
    """
    report_no = meta.get("report_no", "") or ""
    doc = Document()

    # формат страницы A4 + поля (чтобы вмещалось 6 фото на странице)
    _setup_page(doc)

    # колонтитулы: логотип (верх) + «PHOTO REPORT No. ... Page X of Y» (низ)
    _build_headers(doc, report_no)
    _build_footer(doc, report_no)

    # титул на первой странице
    _title(doc, report_no)

    # блок метаданных (пустые поля допустимы — выводятся пустыми)
    _meta_line(doc, "PLACE OF INSPECTION", meta.get("place", ""))
    _meta_line(doc, "DESCRIPTION OF GOODS", meta.get("goods", ""))
    _meta_line(doc, "SCOPE OF SERVICES", meta.get("scope", ""))
    _meta_line(doc, "DATE OF INSPECTION", meta.get("date", ""))
    _meta_line(doc, "CONTAINER", _containers_meta(containers))
    _spacer(doc, Pt(4))

    slots = build_slots(template, containers)
    intro = [s for s in slots if s["section"] == "intro"]
    conts = [s for s in slots if s["section"] == "container"]

    # Страницы НЕ разбиваются принудительно — контент течёт сам (обычно
    # шапка + 6 фото на первой странице, дальше тоже по ~6). Строки фото
    # не рвутся пополам (cantSplit), а Word переносит целые строки на
    # следующую страницу только когда не вмещается на A4.
    if intro:
        _add_photo_table(doc, intro, photos)

    # Контейнеры: группируем по номеру, сохраняя порядок
    groups = []
    for s in conts:
        if not groups or groups[-1][0] != s["container"]:
            groups.append((s["container"], []))
        groups[-1][1].append(s)

    for cont_name, cslots in groups:
        # Номер контейнера по центру + «keep with next»: если номер
        # с первой строкой фото не вмещается внизу страницы — весь блок
        # переедет на следующую страницу вместе с подписью контейнера).
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pf = p.paragraph_format
        pf.space_before = Pt(6)
        pf.space_after = Pt(2)
        pf.keep_with_next = True
        r = p.add_run(_cont_heading(cont_name))
        r.font.bold = True
        r.font.size = Pt(12)
        _add_photo_table(doc, cslots, photos,
                         merge_rows=template.get("merged_caption_rows"))

    # Финальная секция без нижнего колонтитула — чтобы на последней
    # Финальная секция: подпись в теле (колонтитулы наследуются).
    _begin_final_section(doc)

    # Подпись — только в самом конце документа
    _signature(doc, meta.get("footer", ""))

    doc.save(out_path)
    return out_path
