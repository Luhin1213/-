# app/handlers/help_handler.py
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database.queries import get_user_language
from app.utils.i18n import get_rules_sections, t

logger = logging.getLogger(__name__)
router = Router()


def rules_nav_keyboard(idx: int, total: int, lang: str) -> InlineKeyboardMarkup:
    b    = InlineKeyboardBuilder()
    nav  = []
    if idx > 0:
        prev = "◀️ Попереднє" if lang == "UA" else "◀️ Пред."
        nav.append(InlineKeyboardButton(text=prev, callback_data=f"help_nav_{idx-1}"))
    nav.append(InlineKeyboardButton(text=f"{idx+1}/{total}", callback_data="noop"))
    if idx < total - 1:
        nxt = "Наступне ▶️" if lang == "UA" else "След. ▶️"
        nav.append(InlineKeyboardButton(text=nxt, callback_data=f"help_nav_{idx+1}"))
    b.row(*nav)
    # Кнопка змісту
    contents = "📋 Зміст" if lang == "UA" else "📋 Оглавление"
    b.row(InlineKeyboardButton(text=contents, callback_data="help_contents"))
    return b.as_markup()


def rules_contents_keyboard(sections: list, lang: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for i, s in enumerate(sections):
        b.row(InlineKeyboardButton(text=s["title"], callback_data=f"help_nav_{i}"))
    return b.as_markup()


@router.message(F.text.in_(["❓ Допомога", "❓ Помощь"]))
async def help_menu(message: Message):
    lang     = await get_user_language(message.from_user.id)
    sections = get_rules_sections(lang)
    title    = "Правила та Допомога" if lang == "UA" else "Правила и Помощь"
    await message.answer(
        f"📋 <b>{title}</b>\n\nОбери розділ:",
        parse_mode="HTML",
        reply_markup=rules_contents_keyboard(sections, lang)
    )


@router.callback_query(F.data == "help_contents")
async def help_contents_cb(callback: CallbackQuery):
    lang     = await get_user_language(callback.from_user.id)
    sections = get_rules_sections(lang)
    title    = "Правила та Допомога" if lang == "UA" else "Правила и Помощь"
    await callback.message.edit_text(
        f"📋 <b>{title}</b>\n\nОбери розділ:",
        parse_mode="HTML",
        reply_markup=rules_contents_keyboard(sections, lang)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("help_nav_"))
async def help_nav(callback: CallbackQuery):
    idx      = int(callback.data.split("_")[-1])
    lang     = await get_user_language(callback.from_user.id)
    sections = get_rules_sections(lang)
    if idx < 0 or idx >= len(sections):
        await callback.answer()
        return
    section = sections[idx]
    await callback.message.edit_text(
        section["text"],
        parse_mode="HTML",
        reply_markup=rules_nav_keyboard(idx, len(sections), lang),
        disable_web_page_preview=True
    )
    await callback.answer()
