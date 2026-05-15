# app/handlers/player.py
import logging
from typing import Optional
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database.queries import (
    get_player_by_linked_user, get_wallet,
    get_transactions, count_transactions,
    get_top_players, get_all_players_sorted,
    get_user_language, get_player_game_stats,
)
from app.keyboards.main_kb import rating_keyboard, history_nav_keyboard
from app.utils.formatters import format_profile, format_transactions_page, format_rating, format_points, chips
from app.utils.i18n import ui, get_status_by_games

logger = logging.getLogger(__name__)
router = Router()
PER_PAGE = 5


async def _get_player(message: Message) -> Optional[dict]:
    p = await get_player_by_linked_user(message.from_user.id)
    if not p:
        lang = await get_user_language(message.from_user.id)
        await message.answer(ui("no_profile", lang))
    return p


# ── Профіль ──────────────────────────────────────────────────

@router.message(F.text.in_(["👤 Мій профіль", "👤 Мой профиль"]))
async def my_profile(message: Message):
    p = await _get_player(message)
    if not p:
        return
    lang   = await get_user_language(message.from_user.id)
    wallet = await get_wallet(p["id"])
    txs    = await get_transactions(p["id"], limit=3)

    # Динамічне місце в рейтингу
    ranked  = sorted(await get_all_players_sorted(),
                     key=lambda x: x.get("points_total", 0), reverse=True)
    rank_pos = next((i + 1 for i, x in enumerate(ranked) if x["id"] == p["id"]), 0)

    # Статистика з логів (виживаємість і перемоги)
    game_stats = await get_player_game_stats(p["nickname"])

    text = format_profile(p, wallet, txs, lang,
                          rank_pos=rank_pos, game_stats=game_stats) + format_points(p)
    await message.answer(text, parse_mode="HTML")


# ── Рейтинг ──────────────────────────────────────────────────

@router.message(F.text == "🏆 Рейтинг")
async def rating_menu(message: Message):
    lang = await get_user_language(message.from_user.id)
    await message.answer(
        f"🏆 <b>{ui('rating_title', lang)}</b>",
        parse_mode="HTML",
        reply_markup=rating_keyboard()
    )


@router.callback_query(F.data == "rat_my")
async def rating_my(callback: CallbackQuery):
    lang = await get_user_language(callback.from_user.id)
    p    = await get_player_by_linked_user(callback.from_user.id)
    if not p:
        await callback.answer(ui("no_profile", lang), show_alert=True)
        return
    ranked = sorted(await get_all_players_sorted(),
                    key=lambda x: x.get("points_total", 0), reverse=True)
    pos    = next((i+1 for i, x in enumerate(ranked) if x["id"] == p["id"]), None)
    wallet = await get_wallet(p["id"])
    bal    = wallet["balance"] if wallet else 0
    frz    = wallet["frozen_balance"] if wallet else 0
    status = get_status_by_games(p.get("games_played", 0), lang)

    title   = ui("rating_my", lang)
    place   = ui("rating_place", lang)
    from_   = ui("rating_from", lang)
    whisp   = ui("rating_whispers", lang)
    avail   = ui("rating_avail", lang)

    await callback.message.edit_text(
        f"📍 <b>{title}</b>\n\n"
        f"{'Гравець' if lang=='UA' else 'Игрок'}: <b>{p['nickname']}</b>\n"
        f"{ui('rating_status', lang)}: <b>{status}</b>\n"
        f"{'Рейтинг' if lang=='UA' else 'Рейтинг'}: <b>{p.get('rating',0):.1f}</b>\n"
        f"{place}: <b>#{pos}</b> {from_} {len(ranked)}\n\n"
        f"🎰 {whisp}: {bal} ({avail} {bal-frz})",
        parse_mode="HTML",
        reply_markup=rating_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "rat_top15")
async def rating_top15(callback: CallbackQuery):
    players = await get_all_players_sorted()
    ranked  = sorted(players, key=lambda x: x.get("points_total", 0), reverse=True)[:15]
    await callback.message.edit_text(
        format_rating(ranked, "Топ-15"),
        parse_mode="HTML", reply_markup=rating_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "rat_all")
async def rating_all(callback: CallbackQuery):
    players = await get_all_players_sorted()
    ranked  = sorted(players, key=lambda x: x.get("points_total", 0), reverse=True)
    await callback.message.edit_text(
        format_rating(ranked, "Загальний рейтинг"),
        parse_mode="HTML", reply_markup=rating_keyboard()
    )
    await callback.answer()


# ── Історія операцій ─────────────────────────────────────────

@router.message(F.text.in_(["📋 Історія операцій", "📋 История операций"]))
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
