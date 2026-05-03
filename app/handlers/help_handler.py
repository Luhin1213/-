# app/handlers/help_handler.py
# Вкладка "Допомога" з усіма правилами по блоках
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from app.database.queries import get_user_language, is_admin
from app.utils.i18n import RULES, RULES_RU

logger = logging.getLogger(__name__)
router = Router()


def get_rules(lang: str) -> dict:
    if lang == "RU":
        # Для рос. мови — правила UA + рос. описи бота
        merged = dict(RULES)
        merged.update(RULES_RU)
        return merged
    return RULES


def rules_main_keyboard(lang: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if lang == "UA":
        b.row(InlineKeyboardButton(text="👮 Правила гри",           callback_data="help_rules_game"))
        b.row(InlineKeyboardButton(text="🌙 Фази гри",               callback_data="help_rules_phases"))
        b.row(InlineKeyboardButton(text="💬 Обговорення та голосування", callback_data="help_rules_discussion"))
        b.row(InlineKeyboardButton(text="🏆 Умови перемоги",         callback_data="help_rules_victory"))
        b.row(InlineKeyboardButton(text="🏅 Рейтинг та бали",        callback_data="help_rules_rating"))
        b.row(InlineKeyboardButton(text="🎰 Шепоти",                 callback_data="help_rules_whispers"))
        b.row(InlineKeyboardButton(text="✅ Дозволи",                callback_data="help_rules_permissions"))
        b.row(InlineKeyboardButton(text="🌞 Денні заборони",         callback_data="help_rules_bans_day"))
        b.row(InlineKeyboardButton(text="🌙 Нічні заборони",         callback_data="help_rules_bans_night"))
        b.row(InlineKeyboardButton(text="❌ Система фолів",           callback_data="help_rules_fols"))
        b.row(InlineKeyboardButton(text="📝 Умови запису на сесії",  callback_data="help_rules_registration"))
        b.row(InlineKeyboardButton(text="🤖 Як користуватись Ботом", callback_data="help_bot_help"))
    else:
        b.row(InlineKeyboardButton(text="👮 Правила игры (UA)",      callback_data="help_rules_game"))
        b.row(InlineKeyboardButton(text="🌙 Фазы игры (UA)",          callback_data="help_rules_phases"))
        b.row(InlineKeyboardButton(text="💬 Обсуждение (UA)",         callback_data="help_rules_discussion"))
        b.row(InlineKeyboardButton(text="🏆 Победа (UA)",             callback_data="help_rules_victory"))
        b.row(InlineKeyboardButton(text="🏅 Рейтинг (UA)",            callback_data="help_rules_rating"))
        b.row(InlineKeyboardButton(text="🎰 Шёпоты (UA)",             callback_data="help_rules_whispers"))
        b.row(InlineKeyboardButton(text="✅ Разрешения (UA)",         callback_data="help_rules_permissions"))
        b.row(InlineKeyboardButton(text="🌞 Дневные запреты (UA)",    callback_data="help_rules_bans_day"))
        b.row(InlineKeyboardButton(text="🌙 Ночные запреты (UA)",     callback_data="help_rules_bans_night"))
        b.row(InlineKeyboardButton(text="❌ Система фолов (UA)",      callback_data="help_rules_fols"))
        b.row(InlineKeyboardButton(text="📝 Запись на сессии (UA)",   callback_data="help_rules_registration"))
        b.row(InlineKeyboardButton(text="🤖 Как пользоваться Ботом", callback_data="help_bot_help"))
    return b.as_markup()


def back_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="◀️ Назад", callback_data="help_back"))
    return b.as_markup()


# ── Головне меню допомоги ────────────────────────────────────

@router.message(F.text == "❓ Допомога")
async def help_menu(message: Message):
    lang  = await get_user_language(message.from_user.id)
    rules = get_rules(lang)
    await message.answer(
        rules["main_menu"],
        parse_mode="HTML",
        reply_markup=rules_main_keyboard(lang)
    )


# ── Блоки правил ─────────────────────────────────────────────

RULE_KEYS = [
    "rules_game", "rules_phases", "rules_discussion", "rules_victory",
    "rules_rating", "rules_whispers", "rules_permissions",
    "rules_bans_day", "rules_bans_night", "rules_fols",
    "rules_registration", "bot_help",
]


@router.callback_query(F.data.startswith("help_") & ~F.data.in_(["help_back"]))
async def help_section(callback: CallbackQuery):
    section_key = callback.data.replace("help_", "")
    lang        = await get_user_language(callback.from_user.id)
    rules       = get_rules(lang)

    text = rules.get(section_key)
    if not text:
        await callback.answer("Розділ не знайдено", show_alert=True)
        return

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=back_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "help_back")
async def help_back(callback: CallbackQuery):
    lang  = await get_user_language(callback.from_user.id)
    rules = get_rules(lang)
    await callback.message.edit_text(
        rules["main_menu"],
        parse_mode="HTML",
        reply_markup=rules_main_keyboard(lang)
    )
    await callback.answer()
