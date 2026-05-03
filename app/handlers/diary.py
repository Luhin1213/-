# app/handlers/diary.py
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from app.database.queries import (
    get_diary_dates, get_diary_entries_by_date,
    get_diary_entry, is_admin,
)
from app.keyboards.main_kb import diary_dates_keyboard, diary_games_keyboard
from app.services.sheets_service import sync_diary_from_sheets

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.text == "📖 Щоденник Ребеки Найт")
async def diary_menu(message: Message):
    dates = await get_diary_dates()
    if not dates:
        await message.answer(
            "📖 <b>Щоденник Ребеки Найт</b>\n\n"
            "<i>«У цьому місті кожен зберігає таємниці...»</i>\n\n"
            "🔒 Сторінки щоденника ще порожні.\n\n"
            "<b>Структура листа «Щоденник» у Google Sheets:</b>\n"
            "<code>game_date | game_number | title | full_text</code>\n\n"
            "<b>Приклад рядка:</b>\n"
            "<code>2024-12-01 | 1 | Ніч підозр | Текст партії...</code>\n\n"
            "<i>Адмін синхронізує через кнопку «📖 Синх. щоденник»</i>",
            parse_mode="HTML"
        )
        return

    await message.answer(
        "📖 <b>Щоденник Ребеки Найт</b>\n\n"
        "<i>«Кожна гра — історія. Кожна історія — урок.»</i>\n\n"
        "Обери дату партії:",
        parse_mode="HTML",
        reply_markup=diary_dates_keyboard(dates)
    )


@router.callback_query(F.data.startswith("diary_date_"))
async def diary_date_chosen(callback: CallbackQuery):
    date    = callback.data[len("diary_date_"):]
    entries = await get_diary_entries_by_date(date)
    if not entries:
        await callback.answer("Немає записів для цієї дати.", show_alert=True)
        return
    await callback.message.edit_text(
        f"📅 <b>{date}</b>\n\nОбери партію:",
        parse_mode="HTML",
        reply_markup=diary_games_keyboard(entries)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("diary_entry_"))
async def diary_entry_view(callback: CallbackQuery):
    entry_id = int(callback.data.split("_")[-1])
    entry    = await get_diary_entry(entry_id)
    if not entry:
        await callback.answer("Запис не знайдено.", show_alert=True)
        return
    body   = entry.get("full_text") or "Текст не додано."
    header = (
        f"📖 <b>{entry['title']}</b>\n"
        f"📅 {entry['game_date']}  |  Гра #{entry['game_number']}\n"
        f"{'─' * 22}\n\n"
    )
    full = header + body
    for i in range(0, len(full), 4096):
        await callback.message.answer(full[i:i+4096], parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "diary_back")
async def diary_back(callback: CallbackQuery):
    dates = await get_diary_dates()
    if not dates:
        await callback.message.edit_text("📖 Щоденник порожній.")
    else:
        await callback.message.edit_text(
            "📖 <b>Щоденник Ребеки Найт</b>\n\nОбери дату:",
            parse_mode="HTML",
            reply_markup=diary_dates_keyboard(dates)
        )
    await callback.answer()


# ── Синхронізація щоденника (тільки адмін) ──────────────────

@router.message(F.text == "📖 Синх. щоденник")
async def sync_diary(message: Message):
    if not await is_admin(message.from_user.id):
        return
    await message.answer("⏳ Завантажую щоденник з Google Sheets...")
    count, err = await sync_diary_from_sheets()
    if err:
        await message.answer(f"❌ {err}", parse_mode="HTML")
    else:
        await message.answer(
            f"✅ Щоденник оновлено!\nЗавантажено записів: <b>{count}</b>",
            parse_mode="HTML"
        )
