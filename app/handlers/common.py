# app/handlers/common.py
import asyncio, logging, os, sys
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database.queries import (
    get_or_create_user, is_admin, get_player_by_linked_user,
    create_player_auto, get_user_language, set_user_language,
    link_player_to_user,
)
from app.keyboards.main_kb import main_menu_player, main_menu_admin
from app.services.sheets_service import register_user_to_sheets
from app.services.logs_service import register_player_to_mafiagame, fetch_player_stats_by_nickname, find_similar_nicknames
from app.utils.states import RegState
from app.utils.i18n import t
from app.config import USERINFOBOT_LINK

logger = logging.getLogger(__name__)
router = Router()


def lang_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="🇺🇦 Українська", callback_data="lang_UA"),
        InlineKeyboardButton(text="🌊 Одеський",    callback_data="lang_RU"),
    )
    return b.as_markup()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    u = message.from_user
    await get_or_create_user(u.id, u.username or "", u.full_name or "")
    admin  = await is_admin(u.id)
    player = await get_player_by_linked_user(u.id)

    if admin:
        await state.clear()
        lang = await get_user_language(u.id)
        await message.answer(
            f"🔑 Адмін-панель\nПривіт, <b>{u.full_name}</b>!",
            parse_mode="HTML", reply_markup=main_menu_admin(lang)
        )
        return

    if player:
        await state.clear()
        lang = await get_user_language(u.id)
        await message.answer(
            t("welcome_back", lang, nickname=player["nickname"]),
            parse_mode="HTML", reply_markup=main_menu_player(lang)
        )
        return

    # Мова завжди UA — кнопка вибору прибрана
    await set_user_language(u.id, "UA")
    lang_text = (
        "🎭 Ласкаво просимо до клубу <b>Lu's Bluff Business</b>!\n\n"
        "Введіть свій ігровий псевдонім:\n"
        "<i>(той нік, під яким граєте за столом)</i>\n\n"
        "⚠️ <b>Просимо писати Ваш Псевдонім українською чи англійською</b>"
    )
    await message.answer(lang_text, parse_mode="HTML")
    await state.set_state(RegState.enter_nickname)


@router.message(RegState.enter_nickname)
async def reg_nickname(message: Message, state: FSMContext, bot: Bot):
    nickname = message.text.strip()
    lang = "UA"
    if len(nickname) < 2 or len(nickname) > 32:
        await message.answer("❌ Псевдонім має бути від 2 до 32 символів. Спробуйте ще:")
        return

    # Шукаємо схожі нікнейми в MAFIAGAME Players
    similar = await find_similar_nicknames(nickname)

    if similar:
        # Є схожі — показуємо вибір
        await state.update_data(entered_nickname=nickname)
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton
        b = InlineKeyboardBuilder()
        for nick in similar:
            b.row(InlineKeyboardButton(
                text=f"👤 {nick}",
                callback_data=f"reg_pick_{nick[:40]}"
            ))
        b.row(InlineKeyboardButton(
            text=f"✏️ Залишити «{nickname}»",
            callback_data="reg_keep_own"
        ))
        await message.answer(
            "🔍 Знайдено схожі псевдоніми в таблиці:\n\nОберіть свій або залиште введений:",
            reply_markup=b.as_markup()
        )
        await state.set_state(RegState.confirm_nickname)
        return

    # Схожих немає — реєструємо з введеним нікнеймом
    await _do_register(message, state, bot, nickname, lang)


@router.callback_query(RegState.confirm_nickname, lambda c: c.data.startswith("reg_pick_"))
async def reg_pick_similar(callback, state: FSMContext, bot: Bot):
    picked = callback.data.replace("reg_pick_", "")
    data   = await state.get_data()
    own    = data.get("entered_nickname", picked)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text=f"✅ Так, це я ({picked})", callback_data=f"reg_use_{picked[:40]}"),
        InlineKeyboardButton(text=f"✏️ Ні, залишити «{own}»",  callback_data="reg_keep_own"),
    )
    await callback.message.edit_text(
        f"Ви обрали: <b>{picked}</b>\n\nПідтвердити цей псевдонім або залишити власний <b>{own}</b>?",
        parse_mode="HTML",
        reply_markup=b.as_markup()
    )
    await callback.answer()


@router.callback_query(RegState.confirm_nickname, lambda c: c.data.startswith("reg_use_"))
async def reg_use_picked(callback, state: FSMContext, bot: Bot):
    nickname = callback.data.replace("reg_use_", "")
    await callback.message.delete()
    await _do_register(callback.message, state, bot, nickname, "UA", user_override=callback.from_user)
    await callback.answer()


@router.callback_query(RegState.confirm_nickname, lambda c: c.data == "reg_keep_own")
async def reg_keep_own(callback, state: FSMContext, bot: Bot):
    data     = await state.get_data()
    nickname = data.get("entered_nickname", "")
    await callback.message.delete()
    await _do_register(callback.message, state, bot, nickname, "UA", user_override=callback.from_user)
    await callback.answer()


async def _do_register(message, state: FSMContext, bot, nickname: str, lang: str, user_override=None):
    """Фінальна реєстрація після підтвердження нікнейму."""
    u = user_override or message.from_user
    user   = await get_or_create_user(u.id, u.username or "", u.full_name or "")
    player = await create_player_auto(nickname, u.id, u.username or "", u.full_name or "")
    if player and not player.get("linked_user_id"):
        await link_player_to_user(player["id"], user["id"])
        logger.info(f"Прив'язка: player_id={player['id']} → user_id={user['id']}")
    ok, err = await register_user_to_sheets(u.id, u.username or "", u.full_name or "", nickname)
    if not ok:
        logger.warning(f"Sheets: {err}")
    await fetch_player_stats_by_nickname(nickname, player["id"], u.id)
    await register_player_to_mafiagame(nickname, u.id, u.username or "", u.full_name or "")
    await state.clear()
    welcome = t("welcome_letter", lang, nickname=nickname)
    await bot.send_message(
        u.id,
        f"✅ Реєстрацію завершено!\n<b>{nickname}</b>",
        parse_mode="HTML",
        reply_markup=main_menu_player(lang)
    )
    await bot.send_message(u.id, welcome, parse_mode="HTML", disable_web_page_preview=True)
    logger.info(f"Зареєстровано: {nickname} (tg={u.id}, lang={lang})")


@router.callback_query(F.data == "close_msg")
async def close_msg_cb(callback: CallbackQuery):
    try:
        await callback.message.delete()
    except Exception:
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()


@router.message(F.text == "♻️ ПереСтарт")
async def restart_bot(message: Message, bot: Bot):
    admin = await is_admin(message.from_user.id)
    lang  = await get_user_language(message.from_user.id)
    kb    = main_menu_admin(lang) if admin else main_menu_player(lang)
    await message.answer("♻️ Оновлюю меню...", reply_markup=kb)
    if admin:
        async def do_restart():
            await asyncio.sleep(1)
            await bot.session.close()
            os.execv(sys.executable, [sys.executable, "-m", "app.main"])
        asyncio.create_task(do_restart())



