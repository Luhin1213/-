# app/handlers/bets.py
import logging
import aiosqlite
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.database.queries import (
    is_admin, get_player_by_linked_user, get_wallet,
    create_bet, freeze_chips, unfreeze_chips, change_balance,
    get_active_bets, get_open_redness_bets, get_bet,
    update_bet_status, get_player_by_id,
)
from app.keyboards.main_kb import (
    bets_menu_keyboard, color_keyboard, player_number_keyboard,
    amount_keyboard, active_bets_keyboard, bet_manage_keyboard,
    redness_opponents_keyboard,
)
from app.utils.states import BetRednessState, BetAgainstState, BetSideState
from app.utils.formatters import chips, BET_TYPE_UA, BET_STATUS_UA, COLOR_UA
from app.config import ADMIN_IDS, DATABASE_PATH

logger = logging.getLogger(__name__)
router = Router()
MAX_BET = 5


async def _get_player_or_fail(callback: CallbackQuery):
    p = await get_player_by_linked_user(callback.from_user.id)
    if not p:
        await callback.answer("Профіль не знайдено. Напиши /start", show_alert=True)
    return p


async def _notify_admins(bot: Bot, text: str):
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception:
            pass


# ── Меню ставок ──────────────────────────────────────────────

@router.message(F.text == "🎲 Ставки")
async def bets_menu(message: Message):
    await message.answer(
        "🎲 <b>Ставки</b>\n\nОбери тип:",
        parse_mode="HTML",
        reply_markup=bets_menu_keyboard()
    )


# ── 1. На Червоність ─────────────────────────────────────────

@router.callback_query(F.data == "bet_redness")
async def bet_redness_start(callback: CallbackQuery, state: FSMContext):
    p = await _get_player_or_fail(callback)
    if not p:
        return
    wallet = await get_wallet(p["id"])
    avail = (wallet["balance"] - wallet["frozen_balance"]) if wallet else 0
    cap = min(MAX_BET, avail)
    if cap < 1:
        await callback.answer("Недостатньо шепот!", show_alert=True)
        return
    await state.update_data(player_id=p["id"], player_name=p["nickname"])
    await callback.message.edit_text(
        "🔴 <b>Ставка на свою Червоність</b>\n\n"
        "Це фактичне списання шепот.\n\nОбери суму (1–5):",
        parse_mode="HTML",
        reply_markup=amount_keyboard("redness_amount", cap)
    )
    await state.set_state(BetRednessState.enter_amount)
    await callback.answer()


@router.callback_query(BetRednessState.enter_amount, F.data.startswith("redness_amount_"))
async def bet_redness_amount(callback: CallbackQuery, state: FSMContext, bot: Bot):
    amount = int(callback.data.split("_")[-1])
    data = await state.get_data()
    try:
        await freeze_chips(data["player_id"], amount)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        await state.clear()
        return
    bet_id = await create_bet(data["player_id"], "redness", amount, coefficient=1.0)
    await state.clear()
    await callback.message.edit_text(
        f"✅ Ставку на Червоність створено!\nСума: {chips(amount)}\nID: #{bet_id}\nОчікує підтвердження адміна.",
        parse_mode="HTML"
    )
    await _notify_admins(bot,
        f"🔴 Нова ставка на Червоність\n{data['player_name']}: {chips(amount)}\n#{bet_id}")
    await callback.answer()


# ── 2. Проти гравця ──────────────────────────────────────────

@router.callback_query(F.data == "bet_against")
async def bet_against_start(callback: CallbackQuery, state: FSMContext):
    p = await _get_player_or_fail(callback)
    if not p:
        return
    redness_bets = await get_open_redness_bets()
    await state.update_data(player_id=p["id"], player_name=p["nickname"])
    if redness_bets:
        await callback.message.edit_text(
            "⚔️ <b>Поставити Проти</b>\n\nВідкриті ставки на Червоність (рівна відповідь):",
            parse_mode="HTML",
            reply_markup=redness_opponents_keyboard(redness_bets)
        )
        await state.set_state(BetAgainstState.choose_number)
    else:
        await callback.message.edit_text(
            "⚔️ <b>Поставити Проти</b>\n\nОбери колір гравця-цілі:",
            parse_mode="HTML",
            reply_markup=color_keyboard("against_color")
        )
        await state.set_state(BetAgainstState.choose_color)
    await callback.answer()


@router.callback_query(BetAgainstState.choose_number, F.data.startswith("against_redness_"))
async def against_redness(callback: CallbackQuery, state: FSMContext, bot: Bot):
    orig_id = int(callback.data.split("_")[-1])
    orig_bet = await get_bet(orig_id)
    if not orig_bet or orig_bet["status"] != "open":
        await callback.answer("Ставка вже недоступна.", show_alert=True)
        await state.clear()
        return
    data = await state.get_data()
    amount = orig_bet["amount"]
    wallet = await get_wallet(data["player_id"])
    avail = (wallet["balance"] - wallet["frozen_balance"]) if wallet else 0
    if avail < amount:
        await callback.answer(f"Потрібно {chips(amount)}, є {chips(avail)}", show_alert=True)
        await state.clear()
        return
    await freeze_chips(data["player_id"], amount)
    await update_bet_status(orig_id, "duel", opponent_id=data["player_id"])
    await state.clear()
    await callback.message.edit_text(
        f"⚔️ Дуель розпочато!\nСума: {chips(amount)}\nЧекай рішення адміна.",
        parse_mode="HTML"
    )
    await _notify_admins(bot,
        f"⚔️ Дуель!\n{data['player_name']} vs ставка #{orig_id}\n{chips(amount)} vs {chips(amount)}")
    await callback.answer()


@router.callback_query(BetAgainstState.choose_color, F.data.startswith("against_color_"))
async def against_color(callback: CallbackQuery, state: FSMContext):
    color = callback.data.split("_")[-1]
    await state.update_data(color=color)
    await callback.message.edit_text(
        f"⚔️ Обрано: {COLOR_UA.get(color,color)}\n\nОбери номер гравця (1–15):",
        parse_mode="HTML",
        reply_markup=player_number_keyboard("against_num", 15)
    )
    await state.set_state(BetAgainstState.choose_number)
    await callback.answer()


@router.callback_query(BetAgainstState.choose_number, F.data.startswith("against_num_"))
async def against_number(callback: CallbackQuery, state: FSMContext):
    number = int(callback.data.split("_")[-1])
    await state.update_data(number=number)
    data = await state.get_data()
    wallet = await get_wallet(data["player_id"])
    avail = (wallet["balance"] - wallet["frozen_balance"]) if wallet else 0
    cap = min(MAX_BET, avail)
    if cap < 1:
        await callback.answer("Недостатньо шепот!", show_alert=True)
        await state.clear()
        return
    await callback.message.edit_text(
        f"⚔️ Проти {COLOR_UA.get(data.get('color',''),'?')} гравця #{number}\n\nСума (1–5):",
        parse_mode="HTML",
        reply_markup=amount_keyboard("against_amount", cap)
    )
    await state.set_state(BetAgainstState.enter_amount)
    await callback.answer()


@router.callback_query(BetAgainstState.enter_amount, F.data.startswith("against_amount_"))
async def against_amount(callback: CallbackQuery, state: FSMContext, bot: Bot):
    amount = int(callback.data.split("_")[-1])
    data = await state.get_data()
    try:
        await freeze_chips(data["player_id"], amount)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        await state.clear()
        return
    bet_id = await create_bet(data["player_id"], "against", amount,
                               target_number=data.get("number"),
                               side_color=data.get("color"), coefficient=2.0)
    await state.clear()
    await callback.message.edit_text(
        f"✅ Ставку Проти створено!\nСума: {chips(amount)}\n#{bet_id} — очікує підтвердження.",
        parse_mode="HTML"
    )
    await _notify_admins(bot, f"⚔️ Нова ставка Проти\n{data['player_name']} {chips(amount)}\n#{bet_id}")
    await callback.answer()


# ── 3. На перемогу сторони ───────────────────────────────────

@router.callback_query(F.data == "bet_side")
async def bet_side_start(callback: CallbackQuery, state: FSMContext):
    p = await _get_player_or_fail(callback)
    if not p:
        return
    await state.update_data(player_id=p["id"], player_name=p["nickname"])
    await callback.message.edit_text(
        "🎯 <b>Ставка на перемогу сторони</b>\n\n"
        "🔴/⚫ Червона/Чорна → ×2\n🔘 Сіра → ×3\n\nОбери сторону:",
        parse_mode="HTML",
        reply_markup=color_keyboard("side_color")
    )
    await state.set_state(BetSideState.choose_color)
    await callback.answer()


@router.callback_query(BetSideState.choose_color, F.data.startswith("side_color_"))
async def bet_side_color(callback: CallbackQuery, state: FSMContext):
    color = callback.data.split("_")[-1]
    coeff = 3.0 if color == "grey" else 2.0
    await state.update_data(color=color, coefficient=coeff)
    data = await state.get_data()
    wallet = await get_wallet(data["player_id"])
    avail = (wallet["balance"] - wallet["frozen_balance"]) if wallet else 0
    cap = min(MAX_BET, avail)
    await callback.message.edit_text(
        f"🎯 {COLOR_UA.get(color,color)} (×{coeff})\n\nСума (1–5):",
        parse_mode="HTML",
        reply_markup=amount_keyboard("side_amount", cap)
    )
    await state.set_state(BetSideState.enter_amount)
    await callback.answer()


@router.callback_query(BetSideState.enter_amount, F.data.startswith("side_amount_"))
async def bet_side_amount(callback: CallbackQuery, state: FSMContext, bot: Bot):
    amount = int(callback.data.split("_")[-1])
    data = await state.get_data()
    coeff = data.get("coefficient", 2.0)
    try:
        await freeze_chips(data["player_id"], amount)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        await state.clear()
        return
    bet_id = await create_bet(data["player_id"], "side", amount,
                               side_color=data.get("color"), coefficient=coeff)
    await state.clear()
    await callback.message.edit_text(
        f"✅ Ставку на сторону створено!\n{COLOR_UA.get(data.get('color',''),'')} ×{coeff}\n"
        f"Сума: {chips(amount)} → Виграш: {chips(int(amount*coeff))}\n#{bet_id}",
        parse_mode="HTML"
    )
    await _notify_admins(bot,
        f"🎯 Ставка на сторону\n{data['player_name']} {COLOR_UA.get(data.get('color',''),'')} {chips(amount)}\n#{bet_id}")
    await callback.answer()


# ── 4. Смерть вночі ──────────────────────────────────────────

@router.callback_query(F.data == "bet_night_death")
async def bet_night_death(callback: CallbackQuery, state: FSMContext, bot: Bot):
    p = await _get_player_or_fail(callback)
    if not p:
        return
    wallet = await get_wallet(p["id"])
    avail = (wallet["balance"] - wallet["frozen_balance"]) if wallet else 0
    if avail < 1:
        await callback.answer("Недостатньо шепот!", show_alert=True)
        return
    try:
        await freeze_chips(p["id"], 1)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return
    bet_id = await create_bet(p["id"], "night_death", 1, coefficient=3.0)
    await callback.message.edit_text(
        "💀 <b>Ставку 'Смерть вночі' створено!</b>\n\n"
        "Сума: 1 шепот  |  Виграш: 3 шепоти\n\n"
        "<i>Ставку роблять тільки червоні, невбиваючі гравці</i>\n\n"
        f"#{bet_id} — очікує підтвердження адміна.",
        parse_mode="HTML"
    )
    await _notify_admins(bot,
        f"💀 Ставка 'Смерть вночі'\n{p['nickname']}: 1 шепот ×3\n#{bet_id}")
    await callback.answer()


# ── Адмін: Активні ставки ────────────────────────────────────

@router.message(F.text == "📊 Активні ставки")
async def active_bets_menu(message: Message):
    if not await is_admin(message.from_user.id):
        await message.answer("❌ Тільки для адміністратора.")
        return
    bets = await get_active_bets()
    from app.database.queries import get_pending_spendings
    spendings = await get_pending_spendings()

    if not bets and not spendings:
        await message.answer("📊 Немає активних ставок і запитів.")
        return

    if spendings:
        from app.keyboards.main_kb import pending_spendings_keyboard
        await message.answer(
            f"🛒 <b>Очікуючі витрати ({len(spendings)}):</b>",
            parse_mode="HTML",
            reply_markup=pending_spendings_keyboard(spendings)
        )
    if bets:
        await message.answer(
            f"🎲 <b>Активні ставки ({len(bets)}):</b>",
            parse_mode="HTML",
            reply_markup=active_bets_keyboard(bets)
        )


@router.callback_query(F.data.startswith("bet_manage_"))
async def bet_manage(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нема прав", show_alert=True)
        return
    bet_id = int(callback.data.split("_")[-1])
    bet = await get_bet(bet_id)
    if not bet:
        await callback.answer("Не знайдено", show_alert=True)
        return
    type_ua = BET_TYPE_UA.get(bet["bet_type"], bet["bet_type"])
    status_ua = BET_STATUS_UA.get(bet["status"], bet["status"])
    admin_tag = " [адмін]" if bet.get("created_by_admin") else ""
    tgt = f" ціль #{bet['target_number']}" if bet.get("target_number") else ""
    color_txt = f" {COLOR_UA.get(bet.get('side_color') or '', '')}" if bet.get("side_color") else ""
    await callback.message.edit_text(
        f"Ставка #{bet_id}{admin_tag}\n"
        f"Тип: {type_ua}{tgt}{color_txt}\n"
        f"Гравець: {bet.get('creator_nickname','?')}\n"
        f"Сума: {chips(bet['amount'])}  Коефіцієнт: ×{bet.get('coefficient',2.0)}\n"
        f"Статус: {status_ua}\n\nОбери дію:",
        parse_mode="HTML",
        reply_markup=bet_manage_keyboard(bet_id, bet["status"])
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bet_approve_"))
async def bet_approve(callback: CallbackQuery, bot: Bot):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нема прав", show_alert=True)
        return
    bet_id = int(callback.data.split("_")[-1])
    bet = await get_bet(bet_id)
    if not bet:
        await callback.answer("Не знайдено", show_alert=True)
        return
    await update_bet_status(bet_id, "open")
    await callback.message.edit_text(f"✅ Ставку #{bet_id} підтверджено.")
    await callback.answer()


@router.callback_query(F.data.startswith("bet_cancel_"))
async def bet_cancel(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нема прав", show_alert=True)
        return
    bet_id = int(callback.data.split("_")[-1])
    bet = await get_bet(bet_id)
    if not bet:
        await callback.answer("Не знайдено", show_alert=True)
        return
    await unfreeze_chips(bet["creator_player_id"], bet["amount"])
    if bet.get("opponent_player_id"):
        await unfreeze_chips(bet["opponent_player_id"], bet["amount"])
    await update_bet_status(bet_id, "cancelled")
    await callback.message.edit_text(f"❌ Ставку #{bet_id} скасовано. Шепоти повернуто.")
    await callback.answer()


async def _resolve_bet(callback: CallbackQuery, bet_id: int, winner: str):
    bet = await get_bet(bet_id)
    if not bet or bet["status"] not in ("open", "duel"):
        await callback.answer("Вже закрита або не знайдена.", show_alert=True)
        return
    creator_id  = bet["creator_player_id"]
    opponent_id = bet.get("opponent_player_id")
    amount      = bet["amount"]
    coeff       = bet.get("coefficient") or 2.0
    commission  = 1 if amount >= 3 and opponent_id else 0

    await unfreeze_chips(creator_id, amount)
    if opponent_id:
        await unfreeze_chips(opponent_id, amount)
        # Списуємо ставку з обох
        loser_id  = opponent_id if winner == "creator" else creator_id
        winner_id = creator_id  if winner == "creator" else opponent_id
        await change_balance(loser_id, -amount, "bet_lose",
                             f"Програш ставки #{bet_id}", callback.from_user.id)
        payout = amount * 2 - commission
        await change_balance(winner_id, payout, "bet_win",
                             f"Виграш ставки #{bet_id}", callback.from_user.id)
    else:
        if winner == "creator":
            payout = int(amount * coeff) - commission
            await change_balance(creator_id, payout, "bet_win",
                                 f"Виграш ставки #{bet_id}", callback.from_user.id)
        else:
            await change_balance(creator_id, -amount, "bet_lose",
                                 f"Програш ставки #{bet_id}", callback.from_user.id)

    await update_bet_status(bet_id, "closed", result="win" if winner == "creator" else "lose")

    winner_player = await get_player_by_id(creator_id if winner == "creator" else (opponent_id or creator_id))
    name = winner_player["nickname"] if winner_player else "?"
    comm_txt = f"\n(утримано 1 шепот комісії)" if commission else ""
    await callback.message.edit_text(
        f"🏆 Ставка #{bet_id} закрита!\nПереможець: {name}{comm_txt}",
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bet_win_creator_"))
async def bet_win_creator(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нема прав", show_alert=True)
        return
    await _resolve_bet(callback, int(callback.data.split("_")[-1]), "creator")


@router.callback_query(F.data.startswith("bet_win_opponent_"))
async def bet_win_opponent(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нема прав", show_alert=True)
        return
    await _resolve_bet(callback, int(callback.data.split("_")[-1]), "opponent")


@router.callback_query(F.data == "back_active_bets")
async def back_to_bets(callback: CallbackQuery):
    bets = await get_active_bets()
    if not bets:
        await callback.message.edit_text("Активних ставок немає.")
    else:
        await callback.message.edit_reply_markup(reply_markup=active_bets_keyboard(bets))
    await callback.answer()
