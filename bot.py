# -*- coding: utf-8 -*-
"""Telegram-бот: создание фото-отчётов Word по шаблону.

Запуск:  python bot.py   (предварительно укажите токен в config.py или BOT_TOKEN)
Требования: aiogram>=3.4, python-docx  (см. requirements.txt)
"""

import asyncio
import logging
import os
import shutil
import re
import uuid
from html import escape

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, FSInputFile,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

import config
from docgen import build_slots, generate_report
from continue_report import parse_report, ContinueError

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("photo_report_bot")


def _build_storage():
    """Redis-хранилище, если USE_REDIS=1 и пакет redis доступен; иначе — память."""
    if not config.USE_REDIS:
        log.info("FSM storage: MemoryStorage (USE_REDIS=0)")
        return MemoryStorage()
    try:
        from aiogram.fsm.storage.redis import RedisStorage
        storage = RedisStorage.from_url(config.REDIS_URL)
        log.info("FSM storage: RedisStorage")
        return storage
    except Exception as e:  # нет пакета redis или неверный URL
        log.warning("Ошибка настройки Redis (%s) — откат на MemoryStorage", type(e).__name__)
        return MemoryStorage()


bot = Bot(config.BOT_TOKEN)
dp = Dispatcher(storage=_build_storage())

os.makedirs(config.WORK_DIR, exist_ok=True)
os.makedirs(config.OUT_DIR, exist_ok=True)


# -------------------------------------------------------------------------
# Состояния диалога
# -------------------------------------------------------------------------
class Flow(StatesGroup):
    choosing_template = State()
    awaiting_report_file = State()  # ждём .docx для продолжения отчёта
    meta_menu = State()
    editing_meta = State()
    entering_containers = State()
    collecting = State()         # ждём фото
    confirming_photo = State()   # ждём Подтвердить/Переснять (одно фото)
    confirming_batch = State()   # ждём Подтвердить/Переснять (пачка)
    preview = State()            # итоговое меню: предпросмотр / выдача Word


# Буфер для альбомов (фото, отправленные одной пачкой).
_album_buf = {}
_document_slots = asyncio.Semaphore(1)

ALBUM_DEBOUNCE = 1.2  # сек: сколько ждём остальные фото альбома


# Поля метаданных, которые можно редактировать (ключ, подпись)
META_FIELDS = [
    ("report_no", "Номер отчёта (PHOTO REPORT No.)"),
    ("place", "PLACE OF INSPECTION"),
    ("goods", "DESCRIPTION OF GOODS"),
    ("scope", "SCOPE OF SERVICES"),
    ("date", "DATE OF INSPECTION"),
]


def _user_dir(uid):
    d = os.path.join(config.WORK_DIR, str(uid))
    os.makedirs(d, exist_ok=True)
    return d


def _doc_preview_button():
    """Генерация черновика Word по собранным фото."""
    return InlineKeyboardButton(text="Сформировать Word (.docx)", callback_data="collect:doc")


def _meta_text(meta):
    return (
        f"📋 <b>Текущие метаданные:</b>\n\n"
        f"<b>No.</b> {escape(str(meta['report_no']))}\n"
        f"<b>PLACE OF INSPECTION:</b> {escape(str(meta['place']))}\n"
        f"<b>DESCRIPTION OF GOODS:</b> {escape(str(meta['goods']))}\n"
        f"<b>SCOPE OF SERVICES:</b> {escape(str(meta['scope']))}\n"
        f"<b>DATE OF INSPECTION:</b> {escape(str(meta['date']))}"
    )


def _progress(data):
    slots = data["slots"]
    i = data["index"]
    s = slots[i]
    where = "Вводный блок" if s["section"] == "intro" else f"Контейнер {s['container']}"
    # сколько фото осталось в текущем блоке (секция intro или конкретный контейнер)
    block_left = 1
    for sl in slots[i + 1:]:
        if sl["section"] == s["section"] and sl.get("container") == s.get("container"):
            block_left += 1
        else:
            break
    nxt = slots[i:i + max(block_left, 1)]
    nxt_txt = "\n\nСледующие подписи (для пачки):\n" + "\n".join(
        f"  • {j + 1}. {sl['caption']}" for j, sl in enumerate(nxt)
    )
    hint = (
        f"\n\n💡 Можно отправить сразу <b>{block_left}</b> фото пачкой (альбомом) — "
        f"они заполнят ячейки этого блока по порядку."
        if s["section"] == "container"
        else "\n\n💡 Можно отправлять фото пачкой (альбомом, до 10 шт.) — заполняют ячейки по порядку."
    )
    return (
        f"📷 Фото {i + 1} из {len(slots)}\n"
        f"<b>{where}</b>\n"
        f"Подпись: <b>{s['caption']}</b>\n\n"
        f"Отправьте фото для этой ячейки."
        f"{hint}{nxt_txt}"
    )


# <<CHUNK2>>


# -------------------------------------------------------------------------
# /start — выбор шаблона
# -------------------------------------------------------------------------
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    # подчищаем возможные остатки фото от предыдущего отчёта
    old_data = await state.get_data()
    uid = old_data.get("uid", message.from_user.id)
    shutil.rmtree(_user_dir(uid), ignore_errors=True)
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["title"], callback_data=f"tpl:{key}")]
        for key, t in config.TEMPLATES.items()
    ] + [
        [InlineKeyboardButton(text="▶️ Продолжить (пришлите файл)", callback_data="cont_report")],
    ])
    await message.answer(
        "👋 Бот создания фото-отчётов.\n\n"
        "Выберите тип шаблона или продолжите ранее начатый отчёт:",
        reply_markup=kb,
    )
    await state.set_state(Flow.choosing_template)


@dp.callback_query(F.data.startswith("tpl:"), Flow.choosing_template)
async def on_template(cb: CallbackQuery, state: FSMContext):
    key = cb.data.split(":", 1)[1]
    tpl = config.TEMPLATES[key]
    meta = dict(tpl["meta"])  # копия, чтобы не портить дефолт
    await state.update_data(template_key=key, meta=meta)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Оставить как есть", callback_data="meta:keep")],
        [InlineKeyboardButton(text="✏️ Изменить поля (можно пропускать)", callback_data="meta:edit")],
    ])
    await cb.message.edit_text(_meta_text(meta), reply_markup=kb, parse_mode="HTML")
    await state.set_state(Flow.meta_menu)
    await cb.answer()


# -------------------------------------------------------------------------
# Продолжение ранее начатого отчёта (присланный .docx)
# -------------------------------------------------------------------------
@dp.callback_query(F.data == "cont_report", Flow.choosing_template)
async def on_continue(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Flow.awaiting_report_file)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(
        "📎 <b>Продолжение отчёта</b>\n\n"
        "Пришлите файл <b>.docx</b> — ранее созданный этим ботом отчёт.\n"
        "Я определю шаблон, сохраню уже вставленные фото и продолжу заполнение "
        "с первой пустой ячейки.\n\nОтмена — /start",
        parse_mode="HTML",
    )
    await cb.answer()


@dp.message(Flow.awaiting_report_file, F.document)
async def on_report_file(message: Message, state: FSMContext):
    doc = message.document
    name = (doc.file_name or "").lower()
    if not name.endswith(".docx"):
        await message.answer(
            "Нужен файл формата <b>.docx</b> (Word). Пришлите его как документ.",
            parse_mode="HTML",
        )
        return
    uid = message.from_user.id
    ud = _user_dir(uid)
    shutil.rmtree(ud, ignore_errors=True)
    os.makedirs(ud, exist_ok=True)
    src = os.path.join(ud, "_incoming.docx")
    status = await message.answer("⚙️ Читаю файл и восстанавливаю отчёт…")
    try:
        await bot.download(doc, destination=src)
        parsed = await asyncio.to_thread(parse_report, src, ud)
    except ContinueError as e:
        try:
            await status.delete()
        except Exception:  # noqa: BLE001
            pass
        await message.answer(f"⚠️ {e}")
        return
    except Exception as e:  # noqa: BLE001
        log.exception("Ошибка разбора продолжаемого отчёта: %s", e)
        try:
            await status.delete()
        except Exception:  # noqa: BLE001
            pass
        await message.answer(
            "⚠️ Не удалось разобрать файл. Убедитесь, что это отчёт, созданный этим ботом, "
            "или начните заново — /start",
        )
        return
    try:
        os.remove(src)
    except OSError:
        pass

    await state.update_data(
        template_key=parsed["template_key"],
        meta=parsed["meta"],
        containers=parsed["containers"],
        slots=parsed["slots"],
        photos=parsed["photos"],
        index=parsed["index"],
        uid=uid,
        cont_mode=None,
        doc_path=None,
        
    )
    tpl = config.TEMPLATES[parsed["template_key"]]
    labels = ", ".join(escape(str(c)) for c in parsed["containers"])
    try:
        await status.delete()
    except Exception:  # noqa: BLE001
        pass
    await message.answer(
        "✅ <b>Отчёт распознан.</b>\n\n"
        f"Шаблон: <b>{escape(tpl['title'])}</b>\n"
        f"Контейнеры ({len(parsed['containers'])}): <b>{labels}</b>\n"
        f"Уже заполнено фото: <b>{parsed['filled']} из {parsed['total']}</b>\n\n"
        + ("Все ячейки уже заполнены — можно сразу получить документ."
           if parsed["index"] >= parsed["total"]
           else "Продолжаем с первой пустой ячейки!"),
        parse_mode="HTML",
    )
    if parsed["index"] >= parsed["total"]:
        await _preview_menu(message, state)
    else:
        await _ask_photo(message, state)


@dp.message(Flow.awaiting_report_file)
async def report_file_not_doc(message: Message):
    await message.answer(
        "Пришлите файл <b>.docx</b> как документ (не фото и не текст). Отмена — /start",
        parse_mode="HTML",
    )


# -------------------------------------------------------------------------
# Метаданные: оставить / редактировать поле за полем (с пропуском)
# -------------------------------------------------------------------------
def _meta_field_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⏭ Пропустить (оставить)", callback_data="meta:skip"),
        InlineKeyboardButton(text="🗑 Очистить (пусто)", callback_data="meta:clear"),
    ]])


async def _prompt_meta_field(target: Message, state: FSMContext):
    data = await state.get_data()
    idx = data["meta_field_idx"]
    key, label = META_FIELDS[idx]
    cur = data["meta"].get(key, "")
    await target.answer(
        f"✏️ Поле ({idx + 1}/{len(META_FIELDS)}): <b>{label}</b>\n"
        f"Текущее: <code>{escape(str(cur)) or '—'}</code>\n\n"
        "Введите новое значение или выберите действие ниже.",
        parse_mode="HTML", reply_markup=_meta_field_kb(),
    )


async def _advance_meta(target: Message, state: FSMContext):
    data = await state.get_data()
    idx = data["meta_field_idx"] + 1
    if idx < len(META_FIELDS):
        await state.update_data(meta_field_idx=idx)
        await _prompt_meta_field(target, state)
    else:
        meta = data["meta"]
        await target.answer(_meta_text(meta), parse_mode="HTML")
        if data.get("edit_return") == "preview":
            await state.update_data(edit_return=None, doc_path=None)
            await _preview_menu(target, state)
        else:
            await _ask_containers(target, state)


@dp.callback_query(F.data == "meta:keep", Flow.meta_menu)
async def meta_keep(cb: CallbackQuery, state: FSMContext):
    await _ask_containers(cb.message, state)
    await cb.answer()


@dp.callback_query(F.data == "meta:edit", Flow.meta_menu)
async def meta_edit(cb: CallbackQuery, state: FSMContext):
    await state.update_data(meta_field_idx=0)
    await state.set_state(Flow.editing_meta)
    await _prompt_meta_field(cb.message, state)
    await cb.answer()


@dp.message(Flow.editing_meta, F.text)
async def meta_collect(message: Message, state: FSMContext):
    data = await state.get_data()
    idx = data["meta_field_idx"]
    meta = data["meta"]
    key, _ = META_FIELDS[idx]
    meta[key] = message.text.strip()
    await state.update_data(meta=meta, doc_path=None)
    await _advance_meta(message, state)


@dp.callback_query(F.data == "meta:skip", Flow.editing_meta)
async def meta_skip(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer("Поле оставлено без изменений")
    await _advance_meta(cb.message, state)


@dp.callback_query(F.data == "meta:clear", Flow.editing_meta)
async def meta_clear(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    idx = data["meta_field_idx"]
    meta = data["meta"]
    key, _ = META_FIELDS[idx]
    meta[key] = ""
    await state.update_data(meta=meta, doc_path=None)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer("Поле очищено")
    await _advance_meta(cb.message, state)


# -------------------------------------------------------------------------
# Номера контейнеров
#   Два режима на выбор:
#     • serial — ввести серийные номера (MSKU7578640; MRKU9900882; ...)
#     • count  — указать только количество (1, 2, 3 …); контейнеры тогда
#                нумеруются по порядку: 1, 2, 3 … N.
# -------------------------------------------------------------------------
MAX_CONTAINERS = 60  # разумный предел для режима «количество»


def _containers_mode_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔤 Ввести номера контейнеров", callback_data="cont:mode:serial")],
        [InlineKeyboardButton(text="🔢 Указать количество", callback_data="cont:mode:count")],
    ])


async def _ask_containers(message: Message, state: FSMContext):
    await state.update_data(cont_mode=None)
    await message.answer(
        "📦 <b>Как задать контейнеры?</b>\n\n"
        "🔤 <b>Ввести номера</b> — укажите серийные номера, например:\n"
        "<code>MSKU7578640; MRKU9900882; MRKU7927539</code>\n\n"
        "🔢 <b>Указать количество</b> — просто число контейнеров (1, 2, 3 …); "
        "в отчёте они будут пронумерованы по порядку: 1, 2, 3 …\n\n"
        "Выберите вариант ниже или сразу отправьте номера / число.",
        parse_mode="HTML", reply_markup=_containers_mode_kb(),
    )
    await state.set_state(Flow.entering_containers)


@dp.callback_query(F.data == "cont:mode:serial", Flow.entering_containers)
async def cont_mode_serial(cb: CallbackQuery, state: FSMContext):
    await state.update_data(cont_mode="serial")
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(
        "🔤 Введите <b>номера контейнеров</b> — один или несколько.\n"
        "Разделите запятой, точкой с запятой или переносом строки.\n\n"
        "Пример: <code>MSKU7578640; MRKU9900882; MRKU7927539; TEMU1408878</code>",
        parse_mode="HTML",
    )
    await cb.answer()


@dp.callback_query(F.data == "cont:mode:count", Flow.entering_containers)
async def cont_mode_count(cb: CallbackQuery, state: FSMContext):
    await state.update_data(cont_mode="count")
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(
        "🔢 Введите <b>количество контейнеров</b> — просто число.\n"
        "Например: <code>3</code> → в отчёте будут контейнеры 1, 2, 3.",
        parse_mode="HTML",
    )
    await cb.answer()


@dp.message(Flow.entering_containers, F.text)
async def on_containers(message: Message, state: FSMContext):
    data0 = await state.get_data()
    mode = data0.get("cont_mode")
    text = message.text.strip()
    is_number = bool(re.fullmatch(r"\d{1,3}", text))

    # Режим «количество» (выбран кнопкой) ИЛИ автоопределение: прислали одно число.
    if mode == "count" or (mode is None and is_number):
        if not is_number:
            await message.answer(
                "Нужно одно число — количество контейнеров (например <code>3</code>).",
                parse_mode="HTML",
            )
            return
        n = int(text)
        if not (1 <= n <= MAX_CONTAINERS):
            await message.answer(
                f"Количество должно быть от 1 до {MAX_CONTAINERS}. Попробуйте ещё раз."
            )
            return
        containers = [str(i) for i in range(1, n + 1)]
    else:
        # Режим «серийные номера» (или свободный ввод списка)
        raw = text.replace("\n", ";").replace(",", ";")
        containers = [c.strip() for c in raw.split(";") if c.strip()]
        if not containers:
            await message.answer("Не распознал номера. Попробуйте ещё раз.")
            return
    data = await state.get_data()
    tpl = config.TEMPLATES[data["template_key"]]
    slots = build_slots(tpl, containers)
    await state.update_data(
        containers=containers, slots=slots, index=0, photos={},
        uid=message.from_user.id, doc_path=None, 
    )
    ud = _user_dir(message.from_user.id)
    shutil.rmtree(ud, ignore_errors=True)
    os.makedirs(ud, exist_ok=True)
    labels = ", ".join(escape(str(c)) for c in containers)
    await message.answer(
        f"Принято контейнеров: <b>{len(containers)}</b>\n"
        f"Контейнеры: <b>{labels}</b>\n"
        f"Всего нужно фото: <b>{len(slots)}</b>\n\nНачинаем!",
        parse_mode="HTML",
    )
    await _ask_photo(message, state)


# <<CHUNK3>>


# -------------------------------------------------------------------------
# Сбор фото
# -------------------------------------------------------------------------
async def _ask_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    if data["index"] >= len(data["slots"]):
        await _preview_menu(message, state)
        return
    rows = []
    if data["index"] > 0:
        rows.append([InlineKeyboardButton(
            text="⬅️ Назад (переснять пред. ячейку)",
            callback_data="nav:back",
        )])
    rows.append([_doc_preview_button()])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await message.answer(_progress(data), parse_mode="HTML", reply_markup=kb)
    await state.set_state(Flow.collecting)


@dp.callback_query(F.data == "nav:back", Flow.collecting)
async def nav_back(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data["index"] <= 0:
        await cb.answer("Это первая ячейка")
        return
    new_index = data["index"] - 1
    prev_slot = data["slots"][new_index]
    photos = data["photos"]
    old = photos.pop(prev_slot["id"], None)
    if old:
        try:
            os.remove(old)
        except OSError:
            pass
    await state.update_data(index=new_index, photos=photos, doc_path=None)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer("Возврат к предыдущей ячейке")
    await _ask_photo(cb.message, state)


@dp.message(Flow.collecting, F.photo, F.media_group_id.is_(None))
async def on_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    slot = data["slots"][data["index"]]
    ud = _user_dir(message.from_user.id)
    path = os.path.join(ud, f"{slot['id']}.jpg")
    await bot.download(message.photo[-1], destination=path)
    await state.update_data(pending_photo=path)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="ph:ok"),
            InlineKeyboardButton(text="🔄 Переснять", callback_data="ph:retake"),
        ],
        [_doc_preview_button()],
    ])
    await message.answer_photo(
        FSInputFile(path),
        caption=f"Фото для «{slot['caption']}». Подтвердить?",
        reply_markup=kb,
    )
    await state.set_state(Flow.confirming_photo)


# --- Загрузка пачкой (альбом) ---
@dp.message(Flow.collecting, F.photo, F.media_group_id)
async def on_album_photo(message: Message, state: FSMContext):
    mgid = message.media_group_id
    key = (message.chat.id, mgid)
    ud = _user_dir(message.from_user.id)
    tmp = os.path.join(ud, f"_album_{mgid}_{message.message_id}.jpg")
    await bot.download(message.photo[-1], destination=tmp)
    buf = _album_buf.get(key)
    if buf is None:
        buf = {"items": [], "task": None}
        _album_buf[key] = buf
    buf["items"].append((message.message_id, tmp))
    if buf["task"]:
        buf["task"].cancel()
    buf["task"] = asyncio.create_task(_flush_album(key, message, state))


async def _flush_album(key, message: Message, state: FSMContext):
    """Ждём, пока придут все фото альбома, затем раскладываем по слотам."""
    try:
        await asyncio.sleep(ALBUM_DEBOUNCE)
    except asyncio.CancelledError:
        return
    buf = _album_buf.pop(key, None)
    if not buf or not buf["items"]:
        return
    items = sorted(buf["items"], key=lambda x: x[0])  # порядок отправки
    data = await state.get_data()
    slots = data["slots"]
    index = data["index"]
    remaining = len(slots) - index
    use = items[:remaining]
    extra = len(items) - len(use)
    ud = _user_dir(message.from_user.id)
    pending = []
    for off, (mid, tmp) in enumerate(use):
        slot = slots[index + off]
        dest = os.path.join(ud, f"{slot['id']}.jpg")
        shutil.move(tmp, dest)
        pending.append((slot["id"], dest, slot["caption"]))
    for mid, tmp in items[len(use):]:
        try:
            os.remove(tmp)
        except OSError:
            pass
    await state.update_data(pending_batch=pending)
    lines = "\n".join(
        f"  {index + n + 1}. {cap}" for n, (sid, dest, cap) in enumerate(pending)
    )
    txt = f"📦 Получено фото: <b>{len(pending)}</b>\nЗаполняют ячейки:\n{lines}"
    if extra > 0:
        txt += (
            f"\n\n⚠️ Лишние <b>{extra}</b> фото проигнорированы — ячейки закончились."
        )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить всё", callback_data="batch:ok"),
            InlineKeyboardButton(text="🔄 Переснять пачку", callback_data="batch:retake"),
        ],
        [_doc_preview_button()],
    ])
    await message.answer(txt, reply_markup=kb, parse_mode="HTML")
    await state.set_state(Flow.confirming_batch)


@dp.callback_query(F.data == "batch:ok", Flow.confirming_batch)
async def batch_ok(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    photos = data["photos"]
    pending = data.get("pending_batch") or []
    for sid, dest, cap in pending:
        photos[sid] = dest
    await state.update_data(
        photos=photos, index=data["index"] + len(pending),
        pending_batch=None, doc_path=None, 
    )
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer(f"Сохранено: {len(pending)}")
    await _ask_photo(cb.message, state)


@dp.callback_query(F.data == "batch:retake", Flow.confirming_batch)
async def batch_retake(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    for sid, dest, cap in (data.get("pending_batch") or []):
        try:
            os.remove(dest)
        except OSError:
            pass
    await state.update_data(pending_batch=None)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer("Пачка отменена")
    await _ask_photo(cb.message, state)


@dp.message(Flow.collecting)
async def not_a_photo(message: Message):
    await message.answer("Отправьте именно фото (как изображение).")


@dp.callback_query(F.data == "ph:ok", Flow.confirming_photo)
async def photo_ok(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    slot = data["slots"][data["index"]]
    photos = data["photos"]
    photos[slot["id"]] = data["pending_photo"]
    await state.update_data(
        photos=photos, index=data["index"] + 1,
        pending_photo=None, doc_path=None, 
    )
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer("Сохранено")
    await _ask_photo(cb.message, state)


@dp.callback_query(F.data == "ph:retake", Flow.confirming_photo)
async def photo_retake(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer("Отправьте фото заново")
    await _ask_photo(cb.message, state)


# <<CHUNK4>>


# -------------------------------------------------------------------------
# Генерация документа Word
# -------------------------------------------------------------------------
async def _build_doc(state: FSMContext, cache: bool) -> str:
    """Собирает .docx. cache=True — итоговый файл (кэш в doc_path);
    cache=False — черновик-предпросмотр в рабочей папке пользователя.
    """
    data = await state.get_data()
    tpl = config.TEMPLATES[data["template_key"]]
    meta = data["meta"]
    containers = data["containers"]
    photos = data["photos"]
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", str(meta.get("report_no", "")))[:80] or "new"
    if cache:
        out_path = os.path.join(config.OUT_DIR, f"Photo_Report_{safe}_{uuid.uuid4().hex}.docx")
    else:
        ud = _user_dir(data["uid"])
        out_path = os.path.join(ud, f"_draft_{uuid.uuid4().hex}.docx")
    async with _document_slots:
        await asyncio.to_thread(generate_report, tpl, meta, containers, photos, out_path)
    if cache:
        await state.update_data(doc_path=out_path)
    return out_path


async def _generate_doc(state: FSMContext) -> str:
    """Итоговый документ с кэшированием пути."""
    return await _build_doc(state, cache=True)


# Черновик Word во время сбора фото.
@dp.callback_query(F.data == "collect:doc")
async def collect_doc(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("slots") or not data.get("containers"):
        await cb.answer("Документ пока недоступен — сначала выберите шаблон и контейнеры.", show_alert=True)
        return
    await cb.answer()
    draft = None
    status = await cb.message.answer("Собираю документ Word…")
    try:
        draft = await _build_doc(state, cache=False)
        filled = sum(1 for s in data["slots"] if s["id"] in data["photos"])
        await cb.message.answer_document(
            FSInputFile(draft),
            caption=(f"Черновик Word (.docx). Фото: {filled} из {len(data['slots'])}. "
                     "Пустые ячейки можно заполнить, продолжив загрузку фото."),
        )
    finally:
        if draft and os.path.isfile(draft):
            try:
                os.remove(draft)
            except OSError:
                pass
        try:
            await status.delete()
        except Exception:
            pass


# <<CHUNK5>>


# -------------------------------------------------------------------------
# Итоговое меню: предпросмотр и выдача Word
# -------------------------------------------------------------------------
def _preview_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Предпросмотр фото", callback_data="prev:view")],
        [InlineKeyboardButton(text="📅 Получить Word (.docx)", callback_data="prev:word")],
        [InlineKeyboardButton(text="✏️ Изменить метаданные", callback_data="prev:editmeta")],
        [InlineKeyboardButton(text="🔄 Начать заново", callback_data="prev:restart")],
    ])


def _summary_text(data):
    meta = data["meta"]
    containers = data["containers"]
    slots = data["slots"]
    filled = sum(1 for s in slots if s["id"] in data["photos"])
    return (
        "🧾 <b>Отчёт готов к сборке</b>\n\n"
        + _meta_text(meta)
        + f"\n\n<b>Контейнеры ({len(containers)}):</b> "
        + ", ".join(escape(str(c)) for c in containers)
        + f"\n<b>Фото собрано:</b> {filled} из {len(slots)}\n\n"
        "Выберите действие ниже."
    )


async def _preview_menu(message: Message, state: FSMContext):
    """Показывает итоговое меню с кнопкой предпросмотра."""
    await state.set_state(Flow.preview)
    data = await state.get_data()
    await message.answer(
        _summary_text(data), parse_mode="HTML", reply_markup=_preview_kb()
    )


@dp.callback_query(F.data == "prev:word", Flow.preview)
async def prev_word(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    data = await state.get_data()
    doc_path = data.get("doc_path")
    if not doc_path or not os.path.exists(doc_path):
        await cb.message.answer("⚙️ Собираю документ…")
        doc_path = await _generate_doc(state)
    await cb.message.answer_document(
        FSInputFile(doc_path),
        caption="✅ Готово! Ваш фото-отчёт (Word). Для нового — /start",
        reply_markup=_preview_kb(),
    )


# Совместимость со старыми кнопками: выдаём только DOCX.
@dp.callback_query(F.data == "prev:pdf", Flow.preview)
async def legacy_document(cb: CallbackQuery, state: FSMContext):
    await prev_word(cb, state)


@dp.callback_query(F.data == "prev:editmeta", Flow.preview)
async def prev_editmeta(cb: CallbackQuery, state: FSMContext):
    await state.update_data(
        meta_field_idx=0, edit_return="preview", doc_path=None
    )
    await state.set_state(Flow.editing_meta)
    await _prompt_meta_field(cb.message, state)
    await cb.answer()


@dp.callback_query(F.data == "prev:restart", Flow.preview)
async def prev_restart(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    uid = data.get("uid")
    if uid is not None:
        shutil.rmtree(_user_dir(uid), ignore_errors=True)
    await state.clear()
    await cb.answer("Начинаем заново")
    # cb.message.from_user is the bot, not the person pressing Restart.
    await state.update_data(uid=cb.from_user.id)
    await cmd_start(cb.message, state)


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено. Для начала — /start")


async def _start_healthcheck():
    """Опциональный HTTP-эндпойнт для health-check платформы."""
    port = os.getenv("HEALTHCHECK_PORT")
    if not port:
        return
    from aiohttp import web

    async def ok(_req):
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/", ok)
    app.router.add_get("/health", ok)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(port))
    await site.start()
    log.info("Healthcheck HTTP на порту %s", port)


from photo_preview import register_preview
register_preview(dp, Flow.preview, _preview_menu, _meta_text)


async def main():
    await _start_healthcheck()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
