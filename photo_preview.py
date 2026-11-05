"""Просмотр фотографий отчёта в Telegram без конвертации документов."""
import os

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile, InputMediaPhoto


def photo_preview(data, index, prefix="prev", return_text="К меню отчёта"):
    slots = data.get("slots", [])
    if not 0 <= index < len(slots):
        return None
    slot = slots[index]
    path = data.get("photos", {}).get(slot["id"])
    if not path or not os.path.isfile(path):
        return None
    section = "Вводный блок" if slot["section"] == "intro" else f"Контейнер {slot['container']}"
    caption = f"Фото {index + 1} из {len(slots)}\n{section}\n{slot['caption']}"
    navigation = []
    if index > 0:
        navigation.append(InlineKeyboardButton(text="Назад", callback_data=f"{prefix}:photo:{index - 1}"))
    if index + 1 < len(slots):
        navigation.append(InlineKeyboardButton(text="Далее", callback_data=f"{prefix}:photo:{index + 1}"))
    rows = [navigation] if navigation else []
    rows.append([InlineKeyboardButton(text=return_text, callback_data=f"{prefix}:menu")])
    return path, caption[:1024], InlineKeyboardMarkup(inline_keyboard=rows)


def register_preview(dp, flow_state, preview_menu, meta_text):
    from aiogram import F

    @dp.callback_query(F.data == "prev:view", flow_state)
    async def view(cb, state):
        data = await state.get_data()
        preview = photo_preview(data, 0)
        if not preview:
            await cb.answer("Фото недоступно. Создайте отчёт заново через /start.", show_alert=True)
            return
        await cb.answer()
        await cb.message.answer(
            meta_text(data["meta"]) + "\n\nПредпросмотр фотографий и подписей. "
            "Оформление документа смотрите в Word (.docx).", parse_mode="HTML",
        )
        path, caption, keyboard = preview
        await cb.message.answer_photo(FSInputFile(path), caption=caption, reply_markup=keyboard)

    @dp.callback_query(F.data.startswith("prev:photo:"), flow_state)
    async def photo(cb, state):
        data = await state.get_data()
        try:
            index = int(cb.data.rsplit(":", 1)[1])
        except ValueError:
            await cb.answer("Некорректный номер фото.", show_alert=True)
            return
        preview = photo_preview(data, index)
        if not preview:
            await cb.answer("Фото недоступно. Создайте отчёт заново через /start.", show_alert=True)
            return
        await cb.answer()
        path, caption, keyboard = preview
        await cb.message.edit_media(
            media=InputMediaPhoto(media=FSInputFile(path), caption=caption),
            reply_markup=keyboard,
        )

    @dp.callback_query(F.data == "prev:menu", flow_state)
    async def menu(cb, state):
        await cb.answer()
        await cb.message.edit_reply_markup(reply_markup=None)
        await preview_menu(cb.message, state)


def collected_preview(data, index):
    """Только подтверждённые существующие фото; исходные данные не меняются."""
    available = dict(data)
    available["slots"] = [slot for slot in data.get("slots", [])
        if os.path.isfile(data.get("photos", {}).get(slot["id"]) or "")]
    return photo_preview(available, index, "collect", "К загрузке фото")


def register_collection_preview(dp, collecting_state):
    from aiogram import F

    @dp.callback_query(F.data == "collect:view", collecting_state)
    async def view(cb, state):
        preview = collected_preview(await state.get_data(), 0)
        if not preview:
            await cb.answer("Пока нет подтверждённых фотографий.", show_alert=True)
            return
        await cb.answer()
        path, caption, keyboard = preview
        await cb.message.answer_photo(FSInputFile(path), caption=caption, reply_markup=keyboard)

    @dp.callback_query(F.data.startswith("collect:photo:"), collecting_state)
    async def photo(cb, state):
        try:
            index = int(cb.data.rsplit(":", 1)[1])
        except ValueError:
            await cb.answer("Некорректный номер фото.", show_alert=True)
            return
        preview = collected_preview(await state.get_data(), index)
        if not preview:
            await cb.answer("Фото больше недоступно.", show_alert=True)
            return
        await cb.answer()
        path, caption, keyboard = preview
        await cb.message.edit_media(
            media=InputMediaPhoto(media=FSInputFile(path), caption=caption),
            reply_markup=keyboard,
        )

    @dp.callback_query(F.data == "collect:menu", collecting_state)
    async def back(cb, state):
        await cb.answer()
        await cb.message.delete()
