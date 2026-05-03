# app/handlers/diary.py
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from app.database.queries import (
    get_diary_dates, get_diary_entries_by_date, get_diary_entry,
    get_game_logs_without_diary, get_game_log, mark_diary_generated,
    upsert_diary_entry, is_admin,
)
from app.keyboards.main_kb import diary_dates_keyboard, diary_games_keyboard
from app.services.sheets_service import sync_diary_from_sheets
from app.services.logs_service import sync_logs_players, sync_game_details
from app.services.ai_service import generate_diary_entry

logger = logging.getLogger(__name__)
router = Router()


# ── Щоденник для гравців ─────────────────────────────────────

@router.message(F.text == "📖 Щоденник Ребеки Найт")
async def diary_menu(message: Message):
    dates = await get_diary_dates()
    if not dates:
        await message.answer(
            "📖 <b>Щоденник Ребеки Найт</b>\n\n"
            "<i>«У цьому місті кожен зберігає таємниці...»</i>\n\n"
            "🔒 Сторінки щоденника ще порожні.\n\n"
            "Адміністратор завантажить записи з таблиці Логи.",
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
        f"{'─'*22}\n\n"
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


# ══════════════════════════════════════════════
# АДМІН: синхронізація і генерація
# ══════════════════════════════════════════════

@router.message(F.text == "📖 Синх. щоденник")
async def admin_diary_menu(message: Message):
    if not await is_admin(message.from_user.id):
        return

    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(
        text="🔄 Синхронізувати логи гравців (Players)",
        callback_data="sync_logs_players"
    ))
    b.row(InlineKeyboardButton(
        text="🔄 Синхронізувати партії (GameDetails)",
        callback_data="sync_game_details"
    ))
    b.row(InlineKeyboardButton(
        text="✨ Згенерувати щоденник через ШІ",
        callback_data="ai_generate_menu"
    ))
    b.row(InlineKeyboardButton(
        text="📖 Синх. ручний щоденник (Google Sheets)",
        callback_data="sync_manual_diary"
    ))

    await message.answer(
        "📖 <b>Управління Щоденником</b>\n\n"
        "Оберу дію:",
        parse_mode="HTML",
        reply_markup=b.as_markup()
    )


@router.callback_query(F.data == "sync_logs_players")
async def sync_logs_players_cb(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нема прав", show_alert=True)
        return
    await callback.message.edit_text("⏳ Синхронізую бали гравців з таблиці Логи...")
    count, err = await sync_logs_players()
    if err:
        await callback.message.edit_text(f"❌ {err}", parse_mode="HTML")
    else:
        await callback.message.edit_text(
            f"✅ Бали гравців оновлено!\nОброблено гравців: <b>{count}</b>",
            parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data == "sync_game_details")
async def sync_game_details_cb(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нема прав", show_alert=True)
        return
    await callback.message.edit_text("⏳ Зчитую логи партій з GameDetails...")
    count, err = await sync_game_details()
    if err:
        await callback.message.edit_text(f"❌ {err}", parse_mode="HTML")
    else:
        await callback.message.edit_text(
            f"✅ Логи партій завантажено!\nПартій збережено: <b>{count}</b>\n\n"
            f"Тепер можна генерувати Щоденник через ШІ.",
            parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data == "sync_manual_diary")
async def sync_manual_diary_cb(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нема прав", show_alert=True)
        return
    await callback.message.edit_text("⏳ Завантажую ручний щоденник з Google Sheets...")
    count, err = await sync_diary_from_sheets()
    if err:
        await callback.message.edit_text(f"❌ {err}", parse_mode="HTML")
    else:
        await callback.message.edit_text(
            f"✅ Ручний щоденник оновлено! Записів: <b>{count}</b>",
            parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data == "ai_generate_menu")
async def ai_generate_menu(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нема прав", show_alert=True)
        return

    logs = await get_game_logs_without_diary(20)
    if not logs:
        await callback.answer(
            "Немає партій для генерації.\nСпочатку синхронізуй GameDetails.",
            show_alert=True
        )
        return

    b = InlineKeyboardBuilder()
    for log in logs:
        label = f"{log['game_date']} — Партія #{log['game_number']}"
        if log.get("winner_faction"):
            label += f" ({log['winner_faction']})"
        b.row(InlineKeyboardButton(
            text=label,
            callback_data=f"ai_gen_{log['id']}"
        ))
    b.row(InlineKeyboardButton(text="◀️ Назад", callback_data="diary_admin_back"))

    await callback.message.edit_text(
        "✨ <b>Генерація Щоденника через ШІ</b>\n\n"
        "Обери партію для генерації:",
        parse_mode="HTML",
        reply_markup=b.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ai_gen_"))
async def ai_generate_entry(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нема прав", show_alert=True)
        return

    log_id = int(callback.data.split("_")[-1])
    log    = await get_game_log(log_id)
    if not log:
        await callback.answer("Лог не знайдено", show_alert=True)
        return

    await callback.message.edit_text(
        f"⏳ Генерую текст для партії {log['game_date']} #{log['game_number']}...\n\n"
        f"<i>Claude API обробляє лог...</i>",
        parse_mode="HTML"
    )

    text, err = await generate_diary_entry(
        log_text=log.get("raw_log", ""),
        winner=log.get("winner_faction", ""),
        game_date=log["game_date"],
        game_number=log["game_number"],
    )

    if err:
        await callback.message.edit_text(err, parse_mode="HTML")
        await callback.answer()
        return

    # Зберігаємо в diary_entries і позначаємо лог як оброблений
    title = f"Партія #{log['game_number']} — {log['game_date']}"
    await upsert_diary_entry(
        log["game_date"],
        str(log["game_number"]),
        title,
        text
    )
    await mark_diary_generated(log_id, text)

    # Показуємо результат адміну
    preview = text[:500] + "..." if len(text) > 500 else text
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✨ Генерувати ще", callback_data="ai_generate_menu"))
    b.row(InlineKeyboardButton(text="◀️ Назад", callback_data="diary_admin_back"))

    await callback.message.edit_text(
        f"✅ <b>Щоденник згенеровано!</b>\n\n"
        f"Збережено: {title}\n\n"
        f"<b>Попередній перегляд:</b>\n{preview}",
        parse_mode="HTML",
        reply_markup=b.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data == "diary_admin_back")
async def diary_admin_back(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer()
        return
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔄 Синхр. логи гравців",    callback_data="sync_logs_players"))
    b.row(InlineKeyboardButton(text="🔄 Синхр. партії",           callback_data="sync_game_details"))
    b.row(InlineKeyboardButton(text="✨ Генерувати через ШІ",      callback_data="ai_generate_menu"))
    b.row(InlineKeyboardButton(text="📖 Ручний щоденник з Sheets", callback_data="sync_manual_diary"))
    await callback.message.edit_text(
        "📖 <b>Управління Щоденником</b>\n\nОбери дію:",
        parse_mode="HTML",
        reply_markup=b.as_markup()
    )
    await callback.answer()
