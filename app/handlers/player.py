# app/handlers/player.py
import logging
from typing import Optional
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from app.database.queries import (
    get_player_by_linked_user, get_wallet,
    get_transactions, count_transactions,
    get_top_players, get_all_players_sorted,
    get_user_language,
)
from app.keyboards.main_kb import rating_keyboard, history_nav_keyboard
from app.utils.formatters import (
    format_profile, format_wallet_short,
    format_transactions_page, format_rating, format_points,
)

logger = logging.getLogger(__name__)
router = Router()
PER_PAGE = 5


async def _get_player(message: Message) -> Optional[dict]:
    p = await get_player_by_linked_user(message.from_user.id)
    if not p:
        await message.answer("😔 Профіль не знайдено.\nНапишіть /start щоб зареєструватись.")
    return p


def lang_switch_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="🇺🇦 Українська", callback_data="setlang_UA"),
        InlineKeyboardButton(text="🇷🇺 Русский",    callback_data="setlang_RU"),
    )
    return b.as_markup()


# ── Профіль ──────────────────────────────────────────────────

@router.message(F.text == "👤 Мій профіль")
async def my_profile(message: Message):
    p = await _get_player(message)
    if not p:
        return
    text = format_profile(p) + format_points(p)
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=lang_switch_keyboard()
    )


# ── Фішки ────────────────────────────────────────────────────

@router.message(F.text == "🎰 Мої фішки")
async def my_chips(message: Message):
    p = await _get_player(message)
    if not p:
        return
    wallet = await get_wallet(p["id"])
    txs    = await get_transactions(p["id"], limit=3)
    await message.answer(format_wallet_short(wallet, txs), parse_mode="HTML")


# ── Рейтинг ──────────────────────────────────────────────────

@router.message(F.text == "🏆 Рейтинг")
async def rating_menu(message: Message):
    await message.answer(
        "🏆 <b>Рейтинг гравців</b>",
        parse_mode="HTML",
        reply_markup=rating_keyboard()
    )


@router.callback_query(F.data == "rat_my")
async def rating_my(callback: CallbackQuery):
    p = await get_player_by_linked_user(callback.from_user.id)
    if not p:
        await callback.answer("Профіль не знайдено.", show_alert=True)
        return
    ranked = sorted(await get_all_players_sorted(),
                    key=lambda x: x.get("rating", 0), reverse=True)
    pos    = next((i+1 for i, x in enumerate(ranked) if x["id"] == p["id"]), None)
    wallet = await get_wallet(p["id"])
    bal    = wallet["balance"] if wallet else 0
    frz    = wallet["frozen_balance"] if wallet else 0
    await callback.message.edit_text(
        f"📍 <b>Мій рейтинг</b>\n\n"
        f"Гравець: <b>{p['nickname']}</b>\n"
        f"Рейтинг: <b>{p.get('rating',0):.1f}</b>\n"
        f"Місце: <b>#{pos}</b> з {len(ranked)}\n"
        f"Статус: {p.get('status','Новачок')}\n\n"
        f"🎰 Шепоти: {bal} (доступно {bal-frz})",
        parse_mode="HTML",
        reply_markup=rating_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "rat_top10")
async def rating_top10(callback: CallbackQuery):
    players = await get_top_players(10)
    await callback.message.edit_text(
        format_rating(players, "Топ-10"),
        parse_mode="HTML",
        reply_markup=rating_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "rat_all")
async def rating_all(callback: CallbackQuery):
    players = await get_top_players(50)
    await callback.message.edit_text(
        format_rating(players, "Загальний рейтинг"),
        parse_mode="HTML",
        reply_markup=rating_keyboard()
    )
    await callback.answer()


# ── Історія операцій ─────────────────────────────────────────

@router.message(F.text == "📋 Історія операцій")
async def op_history(message: Message):
    p = await _get_player(message)
    if not p:
        return
    await _send_history_page(message, p["id"], page=0, edit=False)


async def _send_history_page(target, player_db_id: int, page: int, edit: bool = True):
    total = await count_transactions(player_db_id)
    txs   = await get_transactions(player_db_id, limit=PER_PAGE, offset=page * PER_PAGE)
    text  = format_transactions_page(txs, page, total, PER_PAGE)
    kb    = history_nav_keyboard(player_db_id, page, total, PER_PAGE)
    if edit:
        await target.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("hist_"))
async def history_page_cb(callback: CallbackQuery):
    parts        = callback.data.split("_")
    player_db_id = int(parts[1])
    page         = int(parts[2])
    await _send_history_page(callback, player_db_id, page, edit=True)
    await callback.answer()
