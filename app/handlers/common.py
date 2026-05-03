# app/handlers/common.py
import asyncio
import logging
import os
import sys
from aiogram import Router, F, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database.queries import (
    get_or_create_user, is_admin, get_player_by_linked_user,
    create_player_auto, get_user_language, set_user_language,
)
from app.keyboards.main_kb import main_menu_player, main_menu_admin
from app.services.sheets_service import register_user_to_sheets
from app.utils.states import RegState
from app.utils.i18n import TEXTS
from app.config import USERINFOBOT_LINK

logger = logging.getLogger(__name__)
router = Router()


def t(key: str, lang: str, **kwargs) -> str:
    """Повертає текст по ключу і мові."""
    text = TEXTS.get(key, {}).get(lang, TEXTS.get(key, {}).get("UA", key))
    if kwargs:
        text = text.format(**kwargs)
    return text


def lang_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="🇺🇦 Українська", callback_data="lang_UA"),
        InlineKeyboardButton(text="🇷🇺 Русский",    callback_data="lang_RU"),
    )
    return b.as_markup()


# ── /start ───────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    u = message.from_user
    await get_or_create_user(u.id, u.username or "", u.full_name or "")

    admin  = await is_admin(u.id)
    player = await get_player_by_linked_user(u.id)

    if admin:
        await state.clear()
        await message.answer(
            f"🔑 Адмін-панель\nПривіт, <b>{u.full_name}</b>!",
            parse_mode="HTML",
            reply_markup=main_menu_admin()
        )
        return

    if player:
        await state.clear()
        lang = await get_user_language(u.id)
        await message.answer(
            t("welcome_back", lang, nickname=player["nickname"]),
            parse_mode="HTML",
            reply_markup=main_menu_player()
        )
        return

    # Новий гравець — вибір мови
    await message.answer(
        t("choose_lang", "UA"),
        reply_markup=lang_keyboard()
    )
    await state.set_state(RegState.choose_lang)


# ── Вибір мови при реєстрації ────────────────────────────────

@router.callback_query(RegState.choose_lang, F.data.startswith("lang_"))
async def reg_lang_chosen(callback, state: FSMContext):
    lang = callback.data.split("_")[1]  # UA або RU
    await state.update_data(lang=lang)
    await set_user_language(callback.from_user.id, lang)

    await callback.message.edit_text(
        t("enter_nickname", lang),
        parse_mode="HTML"
    )
    await state.set_state(RegState.enter_nickname)
    await callback.answer()


# ── Введення псевдоніму ──────────────────────────────────────

@router.message(RegState.enter_nickname)
async def reg_nickname(message: Message, state: FSMContext, bot: Bot):
    nickname = message.text.strip()
    data     = await state.get_data()
    lang     = data.get("lang", "UA")

    if len(nickname) < 2 or len(nickname) > 32:
        await message.answer(t("nickname_too_short", lang))
        return

    u = message.from_user
    await create_player_auto(nickname, u.id, u.username or "", u.full_name or "")

    # Записуємо в Google Sheets (асинхронно)
    ok, err = await register_user_to_sheets(u.id, u.username or "", u.full_name or "", nickname)
    if not ok:
        logger.warning(f"Sheets реєстрація не вдалась: {err}")

    await state.clear()

    # Показуємо головне меню
    await message.answer(
        f"✅ {'Реєстрацію завершено' if lang == 'UA' else 'Регистрация завершена'}!\n\n"
        f"{'Псевдонім' if lang == 'UA' else 'Псевдоним'}: <b>{nickname}</b>",
        parse_mode="HTML",
        reply_markup=main_menu_player()
    )

    # Надсилаємо привітальний лист
    welcome = t("welcome_letter", lang, nickname=nickname)
    await bot.send_message(u.id, welcome, parse_mode="HTML", disable_web_page_preview=True)

    logger.info(f"Зареєстровано: {nickname} (tg={u.id}, lang={lang})")


# ── ПереСтарт ────────────────────────────────────────────────

@router.message(F.text == "♻️ ПереСтарт")
async def restart_bot(message: Message, bot: Bot):
    admin = await is_admin(message.from_user.id)
    kb    = main_menu_admin() if admin else main_menu_player()
    await message.answer("♻️ Оновлюю меню...", reply_markup=kb)
    if admin:
        async def do_restart():
            await asyncio.sleep(1)
            await bot.session.close()
            os.execv(sys.executable, [sys.executable, "-m", "app.main"])
        asyncio.create_task(do_restart())


# ── Зміна мови (з профілю) ───────────────────────────────────

@router.callback_query(F.data.startswith("setlang_"))
async def change_language(callback, state: FSMContext):
    lang = callback.data.split("_")[1]
    await set_user_language(callback.from_user.id, lang)

    if lang == "UA":
        text = t("language_changed_ua", "UA")
    else:
        text = t("language_changed_ru", "RU")

    await callback.answer(text, show_alert=True)
    # Оновлюємо меню
    await callback.message.delete()
    kb = main_menu_admin() if await is_admin(callback.from_user.id) else main_menu_player()
    await callback.message.answer(text, reply_markup=kb)
