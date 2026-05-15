# app/handlers/diary.py
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from app.database.queries import (
    get_diary_dates, get_diary_entries_by_date, get_diary_entry,
    get_game_logs_without_diary, get_game_log, mark_diary_generated,
    upsert_diary_entry, is_admin, get_user_language,
)
from app.keyboards.main_kb import diary_dates_keyboard, diary_games_keyboard
from app.services.sheets_service import sync_diary_from_sheets
from app.services.logs_service import sync_logs_players, sync_game_details
from app.services.ai_service import generate_diary_entry
from app.utils.i18n import ui


def prepare_story_text(text: str) -> str:
    """Обробляє текст з Google Sheets — замінює \\n і \n на реальні переноси рядків."""
    if not text:
        return ""
    text = str(text)
    text = text.replace("\\n", "\n")  # подвійне екранування
    text = text.replace("\n", "\n")    # звичайний текстовий символ
    # Також обробляємо літеральний \n що приходить як рядок з 2 символів
    text = text.replace("\\n", "\n")
    text = text.strip()
    return text

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.text.in_(["📖 Щоденник Ребеки Найт", "📖 Дневник Ребекки Найт"]))
async def diary_menu(message: Message):
    lang  = await get_user_language(message.from_user.id)
    dates = await get_diary_dates()
    title = ui("diary_title", lang)
    if not dates:
        await message.answer(
            f"📖 <b>{title}</b>\n\n"
            f"<i>{ui('diary_quote', lang)}</i>\n\n"
            f"{ui('diary_empty', lang)}",
            parse_mode="HTML"
        )
        return
    await message.answer(
        f"📖 <b>{title}</b>\n\n"
        f"<i>{ui('diary_quote', lang)}</i>\n\n"
        f"{ui('diary_choose_date', lang)}",
        parse_mode="HTML",
        reply_markup=diary_dates_keyboard(dates)
    )


@router.callback_query(F.data.startswith("ddate_"))
async def diary_date_chosen(callback: CallbackQuery):
    idx   = int(callback.data.split("_")[-1])
    lang  = await get_user_language(callback.from_user.id)
    dates = await get_diary_dates()
    if idx >= len(dates):
        await callback.answer(ui("diary_no_entry", lang), show_alert=True)
        return
    date    = dates[idx]
    entries = await get_diary_entries_by_date(date)
    if not entries:
        await callback.answer(ui("diary_empty_date", lang), show_alert=True)
        return
    await callback.message.edit_text(
        f"📅 <b>{date}</b>\n\n{ui('diary_choose_game', lang)}",
        parse_mode="HTML",
        reply_markup=diary_games_keyboard(entries, lang)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("dentry_"))
async def diary_entry_view(callback: CallbackQuery):
    entry_id = int(callback.data.split("_")[-1])
    lang     = await get_user_language(callback.from_user.id)
    entry    = await get_diary_entry(entry_id)
    if not entry:
        await callback.answer(ui("diary_no_entry", lang), show_alert=True)
        return
    no_text  = "Текст не додано."
    raw_body = entry.get("full_text") or ""
    body     = prepare_story_text(raw_body) if raw_body else no_text
    header   = (
        f"📖 <b>{entry['title']}</b>\n"
        f"📅 {entry['game_date']}  |  Гра #{entry['game_number']}\n"
        f"{'─'*22}\n\n"
    )
    full = header + body
    # Надсилаємо без parse_mode якщо є підозрілі теги — безпечніше
    # Замінюємо <u> на підкреслення символами, щоб не ламати HTML
    safe_full = full.replace("<u>", "").replace("</u>", "")
    for i in range(0, len(safe_full), 4096):
        try:
            await callback.message.answer(safe_full[i:i+4096], parse_mode="HTML")
        except Exception:
            # Якщо HTML зламаний — надсилаємо як простий текст
            import re
            plain = re.sub(r'<[^>]+>', '', safe_full[i:i+4096])
            await callback.message.answer(plain)
    await callback.answer()


@router.callback_query(F.data == "dback")
async def diary_back(callback: CallbackQuery):
    lang  = await get_user_language(callback.from_user.id)
    dates = await get_diary_dates()
    title = ui("diary_title", lang)
    if not dates:
        await callback.message.edit_text(f"📖 {ui('diary_empty', lang)}")
    else:
        await callback.message.edit_text(
            f"📖 <b>{title}</b>\n\n{ui('diary_choose_date', lang)}",
            parse_mode="HTML",
            reply_markup=diary_dates_keyboard(dates)
        )
    await callback.answer()


# ── Адмін: синхронізація і генерація ────────────────────────

@router.message(F.text == "📖 Синх. щоденник")
async def admin_diary_menu(message: Message):
    if not await is_admin(message.from_user.id):
        return
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔄 Синхр. логи гравців (Players)", callback_data="sync_logs_players"))
    b.row(InlineKeyboardButton(text="🔄 Синхр. партії (GameDetails)",    callback_data="sync_game_details"))
    b.row(InlineKeyboardButton(text="✨ Генерувати щоденник ШІ",          callback_data="ai_generate_menu"))
    b.row(InlineKeyboardButton(text="📖 Ручний щоденник (Google Sheets)", callback_data="sync_manual_diary"))
    await message.answer(
        "📖 <b>Управління Щоденником</b>\n\nОбери дію:",
        parse_mode="HTML", reply_markup=b.as_markup()
    )


@router.callback_query(F.data == "sync_logs_players")
async def sync_logs_players_cb(callback: CallbackQuery):
    await callback.message.edit_text("⏳ Синхронізую бали гравців...")
    count, err = await sync_logs_players()
    await callback.message.edit_text(f"❌ {err}" if err else f"✅ Оновлено {count} гравців.")
    await callback.answer()


@router.callback_query(F.data == "sync_game_details")
async def sync_game_details_cb(callback: CallbackQuery):
    await callback.message.edit_text("⏳ Зчитую логи партій...")
    count, err = await sync_game_details()
    await callback.message.edit_text(f"❌ {err}" if err else f"✅ Логи партій: {count}")
    await callback.answer()


@router.callback_query(F.data == "sync_manual_diary")
async def sync_manual_diary_cb(callback: CallbackQuery):
    await callback.message.edit_text("⏳ Завантажую щоденник...")
    count, err = await sync_diary_from_sheets()
    if err:
        await callback.message.edit_text(f"❌ {err}", parse_mode="HTML")
    else:
        await callback.message.edit_text(f"✅ Щоденник оновлено! Записів: {count}")
    await callback.answer()


@router.callback_query(F.data == "ai_generate_menu")
async def ai_generate_menu(callback: CallbackQuery):
    logs = await get_game_logs_without_diary(20)
    if not logs:
        await callback.answer("Немає партій. Синхронізуй GameDetails.", show_alert=True)
        return
    b = InlineKeyboardBuilder()
    for log in logs:
        label = f"{log['game_date']} — Партія #{log['game_number']}"
        if log.get("winner_faction"):
            label += f" ({log['winner_faction']})"
        b.row(InlineKeyboardButton(text=label, callback_data=f"ai_gen_{log['id']}"))
    b.row(InlineKeyboardButton(text="◀️ Назад", callback_data="diary_admin_back"))
    await callback.message.edit_text(
        "✨ <b>Генерація через ШІ</b>\n\nОбери партію:",
        parse_mode="HTML", reply_markup=b.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ai_gen_"))
async def ai_generate_entry(callback: CallbackQuery):
    log_id = int(callback.data.split("_")[-1])
    log    = await get_game_log(log_id)
    if not log:
        await callback.answer("Не знайдено", show_alert=True)
        return
    await callback.message.edit_text(
        f"⏳ Генерую {log['game_date']} #{log['game_number']}...", parse_mode="HTML"
    )
    text, err = await generate_diary_entry(
        log.get("raw_log",""), log.get("winner_faction",""),
        log["game_date"], log["game_number"]
    )
    if err:
        await callback.message.edit_text(err, parse_mode="HTML")
        await callback.answer()
        return
    title = f"Партія #{log['game_number']} — {log['game_date']}"
    await upsert_diary_entry(log["game_date"], str(log["game_number"]), title, text)
    await mark_diary_generated(log_id, text)
    # Записуємо в Google Sheets лист "Щоденник"
    try:
        from app.services.sheets_service import write_diary_to_sheets
        await write_diary_to_sheets(log["game_date"], str(log["game_number"]), title, text)
    except Exception as e:
        logger.warning(f"Не вдалось записати щоденник в Sheets: {e}")
    preview = text[:500] + "..." if len(text) > 500 else text
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✨ Ще", callback_data="ai_generate_menu"))
    b.row(InlineKeyboardButton(text="◀️ Назад", callback_data="diary_admin_back"))
    await callback.message.edit_text(
        f"✅ <b>Щоденник згенеровано!</b>\n\n{preview}",
        parse_mode="HTML", reply_markup=b.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data == "diary_admin_back")
async def diary_admin_back(callback: CallbackQuery):
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔄 Синхр. логи гравців",    callback_data="sync_logs_players"))
    b.row(InlineKeyboardButton(text="🔄 Синхр. партії",           callback_data="sync_game_details"))
    b.row(InlineKeyboardButton(text="✨ Генерувати ШІ",            callback_data="ai_generate_menu"))
    b.row(InlineKeyboardButton(text="📖 Ручний щоденник",         callback_data="sync_manual_diary"))
    await callback.message.edit_text(
        "📖 <b>Управління Щоденником</b>", parse_mode="HTML", reply_markup=b.as_markup()
    )
    await callback.answer()
