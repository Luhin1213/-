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
    update_bet_status, get_player_by_id, get_user_language,
)
from app.keyboards.main_kb import (
    bets_menu_keyboard, color_keyboard, player_number_keyboard,
    amount_keyboard, active_bets_keyboard, bet_manage_keyboard,
    redness_opponents_keyboard,
)
from app.utils.states import BetRednessState, BetAgainstState, BetSideState
from app.utils.formatters import chips, BET_TYPE_UA, BET_STATUS_UA, COLOR_UA
from app.utils.i18n import ui
from app.config import ADMIN_IDS, DATABASE_PATH

logger = logging.getLogger(__name__)
router = Router()
MAX_BET = 5


async def _get_player_or_fail(callback: CallbackQuery):
    p = await get_player_by_linked_user(callback.from_user.id)
    if not p:
        lang = await get_user_language(callback.from_user.id)
        await callback.answer(ui("no_profile", lang), show_alert=True)
    return p


async def _notify_admins(bot: Bot, text: str):
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception:
            pass


async def _notify_player(bot: Bot, player_db_id: int, text: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "SELECT u.telegram_id FROM users u "
            "JOIN players p ON p.linked_user_id=u.id WHERE p.id=?",
            (player_db_id,)
        )
        row = await cur.fetchone()
        if row:
            try:
                await bot.send_message(row[0], text, parse_mode="HTML")
            except Exception:
                pass


# ── Меню ставок ──────────────────────────────────────────────

@router.message(F.text == "🎲 Ставки")
async def bets_menu(message: Message):
    lang = await get_user_language(message.from_user.id)
    title = ui("bets_title", lang)
    choose = ui("bets_choose", lang)
    await message.answer(
        f"🎲 <b>{title}</b>\n\n{choose}",
        parse_mode="HTML",
        reply_markup=bets_menu_keyboard(lang)
    )


# ── 1. На Червоність ─────────────────────────────────────────

@router.callback_query(F.data == "bet_redness")
async def bet_redness_start(callback: CallbackQuery, state: FSMContext):
    p    = await _get_player_or_fail(callback)
    if not p:
        return
    lang   = await get_user_language(callback.from_user.id)
    wallet = await get_wallet(p["id"])
    avail  = (wallet["balance"] - wallet["frozen_balance"]) if wallet else 0
    cap    = min(MAX_BET, avail)
    if cap < 1:
        await callback.answer(ui("bets_no_chips", lang), show_alert=True)
        return
    await state.update_data(player_id=p["id"], player_name=p["nickname"])
    title = ui("bets_redness_title", lang)
    desc  = ui("bets_redness_desc", lang)
    ask   = ui("bets_choose_amount", lang)
    await callback.message.edit_text(
        f"🔴 <b>{title}</b>\n\n{desc}\n\n{ask}",
        parse_mode="HTML",
        reply_markup=amount_keyboard("redness_amount", cap)
    )
    await state.set_state(BetRednessState.enter_amount)
    await callback.answer()


@router.callback_query(BetRednessState.enter_amount, F.data.startswith("redness_amount_"))
async def bet_redness_amount(callback: CallbackQuery, state: FSMContext, bot: Bot):
    amount = int(callback.data.split("_")[-1])
    data   = await state.get_data()
    lang   = await get_user_language(callback.from_user.id)
    try:
        await freeze_chips(data["player_id"], amount)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        await state.clear()
        return
    bet_id = await create_bet(data["player_id"], "redness", amount, coefficient=1.0)
    await state.clear()
    await callback.message.edit_text(
        ui("bets_created", lang, amount=chips(amount), bet_id=bet_id),
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
    lang         = await get_user_language(callback.from_user.id)
    redness_bets = await get_open_redness_bets()
    await state.update_data(player_id=p["id"], player_name=p["nickname"])
    if redness_bets:
        await callback.message.edit_text(
            f"⚔️ <b>{ui('bets_against_title', lang)}</b>\n\n{ui('bets_redness_open', lang)}",
            parse_mode="HTML",
            reply_markup=redness_opponents_keyboard(redness_bets)
        )
        await state.set_state(BetAgainstState.choose_number)
    else:
        await callback.message.edit_text(
            f"⚔️ <b>{ui('bets_against_title', lang)}</b>\n\n{ui('bets_choose_number', lang)}",
            parse_mode="HTML",
            reply_markup=player_number_keyboard("against_num", 15)
        )
        await state.set_state(BetAgainstState.choose_number)
    await callback.answer()


@router.callback_query(BetAgainstState.choose_number, F.data.startswith("against_redness_"))
async def against_redness(callback: CallbackQuery, state: FSMContext, bot: Bot):
    orig_id  = int(callback.data.split("_")[-1])
    orig_bet = await get_bet(orig_id)
    lang     = await get_user_language(callback.from_user.id)
    if not orig_bet or orig_bet["status"] != "open":
        await callback.answer("Ставка вже недоступна." if lang=="UA" else "Ставка уже недоступна.", show_alert=True)
        await state.clear()
        return
    data   = await state.get_data()
    amount = orig_bet["amount"]
    wallet = await get_wallet(data["player_id"])
    avail  = (wallet["balance"] - wallet["frozen_balance"]) if wallet else 0
    if avail < amount:
        await callback.answer(ui("bets_no_chips", lang), show_alert=True)
        await state.clear()
        return
    await freeze_chips(data["player_id"], amount)
    await update_bet_status(orig_id, "duel", opponent_id=data["player_id"])
    await state.clear()
    await callback.message.edit_text(
        ui("bets_duel_started", lang, amount=chips(amount)), parse_mode="HTML"
    )
    await _notify_admins(bot,
        f"⚔️ Дуель!\n{data['player_name']} vs ставка #{orig_id}\n{chips(amount)}")
    await callback.answer()


@router.callback_query(BetAgainstState.choose_number, F.data.startswith("against_num_"))
async def against_number_chosen(callback: CallbackQuery, state: FSMContext):
    number = int(callback.data.split("_")[-1])
    lang   = await get_user_language(callback.from_user.id)
    await state.update_data(number=number)
    await callback.message.edit_text(
        f"⚔️ {'Ціль' if lang=='UA' else 'Цель'}: <b>#{number}</b>\n\n{ui('bets_choose_color', lang)}",
        parse_mode="HTML",
        reply_markup=color_keyboard("against_color")
    )
    await state.set_state(BetAgainstState.choose_color)
    await callback.answer()


@router.callback_query(BetAgainstState.choose_color, F.data.startswith("against_color_"))
async def against_color(callback: CallbackQuery, state: FSMContext):
    color  = callback.data.split("_")[-1]
    lang   = await get_user_language(callback.from_user.id)
    await state.update_data(color=color)
    data   = await state.get_data()
    wallet = await get_wallet(data["player_id"])
    avail  = (wallet["balance"] - wallet["frozen_balance"]) if wallet else 0
    cap    = min(MAX_BET, avail)
    if cap < 1:
        await callback.answer(ui("bets_no_chips", lang), show_alert=True)
        await state.clear()
        return
    await callback.message.edit_text(
        f"⚔️ {'Ціль' if lang=='UA' else 'Цель'}: <b>#{data['number']}</b> {COLOR_UA.get(color,color)}\n\n{ui('bets_choose_amount', lang)}",
        parse_mode="HTML",
        reply_markup=amount_keyboard("against_amount", cap)
    )
    await state.set_state(BetAgainstState.enter_amount)
    await callback.answer()


@router.callback_query(BetAgainstState.enter_amount, F.data.startswith("against_amount_"))
async def against_amount(callback: CallbackQuery, state: FSMContext, bot: Bot):
    amount = int(callback.data.split("_")[-1])
    data   = await state.get_data()
    lang   = await get_user_language(callback.from_user.id)
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
    color_txt = COLOR_UA.get(data.get("color",""), "")
    tgt_txt   = f" #{data.get('number','')} {color_txt}"
    await callback.message.edit_text(
        ui("bets_created", lang, amount=chips(amount), bet_id=bet_id),
        parse_mode="HTML"
    )
    await _notify_admins(bot,
        f"🎰 Ставка на гравця{tgt_txt}\n{data['player_name']}: {chips(amount)}\n#{bet_id}")
    await callback.answer()


# ── 3. На перемогу сторони ───────────────────────────────────

@router.callback_query(F.data == "bet_side")
async def bet_side_start(callback: CallbackQuery, state: FSMContext):
    p    = await _get_player_or_fail(callback)
    if not p:
        return
    lang = await get_user_language(callback.from_user.id)
    await state.update_data(player_id=p["id"], player_name=p["nickname"])
    await callback.message.edit_text(
        f"🎯 <b>{ui('bets_side_title', lang)}</b>\n\n{ui('bets_side_desc', lang)}",
        parse_mode="HTML",
        reply_markup=color_keyboard("side_color")
    )
    await state.set_state(BetSideState.choose_color)
    await callback.answer()


@router.callback_query(BetSideState.choose_color, F.data.startswith("side_color_"))
async def bet_side_color(callback: CallbackQuery, state: FSMContext, bot: Bot):
    color  = callback.data.split("_")[-1]
    lang   = await get_user_language(callback.from_user.id)
    coeff  = 3.0 if color == "grey" else 2.0
    data   = await state.get_data()
    amount = 1
    wallet = await get_wallet(data["player_id"])
    avail  = (wallet["balance"] - wallet["frozen_balance"]) if wallet else 0
    if avail < 1:
        await callback.answer(ui("bets_no_chips", lang), show_alert=True)
        await state.clear()
        return
    try:
        await freeze_chips(data["player_id"], amount)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        await state.clear()
        return
    bet_id = await create_bet(data["player_id"], "side", amount,
                               side_color=color, coefficient=coeff)
    await state.clear()
    await callback.message.edit_text(
        ui("bets_side_created", lang,
           color=COLOR_UA.get(color,color), coeff=coeff,
           amount=chips(amount), payout=chips(int(amount*coeff)),
           bet_id=bet_id),
        parse_mode="HTML"
    )
    await _notify_admins(bot,
        f"🎯 Ставка на сторону\n{data['player_name']} {COLOR_UA.get(color,'')} {chips(amount)} ×{coeff}\n#{bet_id}")
    await callback.answer()


# ── 4. Смерть вночі ──────────────────────────────────────────

@router.callback_query(F.data == "bet_night_death")
async def bet_night_death_start(callback: CallbackQuery, state: FSMContext):
    """Показуємо опис і вибір номера гравця."""
    p    = await _get_player_or_fail(callback)
    if not p:
        return
    lang   = await get_user_language(callback.from_user.id)
    wallet = await get_wallet(p["id"])
    avail  = (wallet["balance"] - wallet["frozen_balance"]) if wallet else 0
    if avail < 1:
        await callback.answer(ui("bets_no_chips", lang), show_alert=True)
        return
    await state.update_data(player_id=p["id"], player_name=p["nickname"])
    await callback.message.edit_text(
        "💀 <b>Смерть вночі — ×3, 1 шепот</b>\n\n"
        "⚠️ <i>Можуть ставити тільки ЧЕРВОНІ, НЕ вбиваючі Мешканці</i>\n\n"
        "Обери номер гравця на чию смерть ставиш (1–15):",
        parse_mode="HTML",
        reply_markup=player_number_keyboard("night_target", 15)
    )
    from app.utils.states import BetRednessState
    await state.set_state(BetRednessState.enter_amount)
    await callback.answer()


@router.callback_query(BetRednessState.enter_amount, F.data.startswith("night_target_"))
async def bet_night_target(callback: CallbackQuery, state: FSMContext, bot: Bot):
    target = int(callback.data.split("_")[-1])
    data   = await state.get_data()
    lang   = await get_user_language(callback.from_user.id)
    try:
        await freeze_chips(data["player_id"], 1)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        await state.clear()
        return
    bet_id = await create_bet(data["player_id"], "night_death", 1,
                               target_number=target, coefficient=3.0)
    await state.clear()
    await callback.message.edit_text(
        ui("bets_night_title", lang, bet_id=bet_id),
        parse_mode="HTML"
    )
    await _notify_admins(bot,
        f"💀 Ставка Смерть вночі\n{data['player_name']} → гравець #{target}\n#{bet_id}")
    await callback.answer()


# ── Адмін: Активні ставки ────────────────────────────────────

@router.message(F.text == "📊 Активні ставки")
async def active_bets_direct(message: Message):
    from app.database.queries import get_active_bets, get_pending_spendings
    from app.keyboards.main_kb import active_bets_keyboard, pending_spendings_keyboard
    bets      = await get_active_bets()
    spendings = await get_pending_spendings()
    if not bets and not spendings:
        await message.answer("📊 Немає активних ставок і запитів.")
        return
    if spendings:
        await message.answer(
            f"🛒 <b>Очікуючі витрати ({len(spendings)}):</b>",
            parse_mode="HTML", reply_markup=pending_spendings_keyboard(spendings)
        )
    if bets:
        await message.answer(
            f"🎲 <b>Активні ставки ({len(bets)}):</b>",
            parse_mode="HTML", reply_markup=active_bets_keyboard(bets, has_hold=True)
        )


@router.callback_query(F.data == "admin_active_bets")
async def admin_active_bets_cb(callback: CallbackQuery):
    from app.database.queries import get_active_bets, get_pending_spendings
    from app.keyboards.main_kb import active_bets_keyboard, pending_spendings_keyboard
    bets      = await get_active_bets()
    spendings = await get_pending_spendings()
    if not bets and not spendings:
        await callback.message.edit_text("📊 Немає активних ставок і запитів.")
        await callback.answer()
        return
    if spendings:
        await callback.message.answer(
            f"🛒 <b>Очікуючі витрати ({len(spendings)}):</b>",
            parse_mode="HTML", reply_markup=pending_spendings_keyboard(spendings)
        )
    if bets:
        await callback.message.answer(
            f"🎲 <b>Активні ставки ({len(bets)}):</b>",
            parse_mode="HTML", reply_markup=active_bets_keyboard(bets, has_hold=True)
        )
    await callback.answer()


@router.callback_query(F.data.startswith("bet_manage_"))
async def bet_manage(callback: CallbackQuery):
    bet_id = int(callback.data.split("_")[-1])
    bet    = await get_bet(bet_id)
    if not bet:
        await callback.answer("Не знайдено", show_alert=True)
        return
    type_ua   = BET_TYPE_UA.get(bet["bet_type"], bet["bet_type"])
    status_ua = BET_STATUS_UA.get(bet["status"], bet["status"])
    admin_tag = " [Мер]" if bet.get("created_by_admin") else ""
    tgt       = f" ціль #{bet['target_number']}" if bet.get("target_number") else ""
    color_txt = f" {COLOR_UA.get(bet.get('side_color') or '', '')}" if bet.get("side_color") else ""
    nick      = bet.get("creator_nickname", "?")
    await callback.message.edit_text(
        f"Ставка #{bet_id}{admin_tag}\n"
        f"Тип: {type_ua}{tgt}{color_txt}\n"
        f"Гравець: {nick}\n"
        f"Сума: {chips(bet['amount'])}  Коефіцієнт: ×{bet.get('coefficient',2.0)}\n"
        f"Статус: {status_ua}\n\nОбери дію:",
        parse_mode="HTML",
        reply_markup=bet_manage_keyboard(bet_id, bet["status"], bet["bet_type"])
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bet_approve_"))
async def bet_approve(callback: CallbackQuery):
    bet_id = int(callback.data.split("_")[-1])
    bet    = await get_bet(bet_id)
    if not bet:
        await callback.answer("Не знайдено", show_alert=True)
        return
    await update_bet_status(bet_id, "open")
    await callback.message.edit_text(
        ui("bet_approved", "UA", id=bet_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bet_cancel_"))
async def bet_cancel(callback: CallbackQuery):
    bet_id = int(callback.data.split("_")[-1])
    bet    = await get_bet(bet_id)
    if not bet:
        await callback.answer("Не знайдено", show_alert=True)
        return
    await unfreeze_chips(bet["creator_player_id"], bet["amount"])
    if bet.get("opponent_player_id"):
        await unfreeze_chips(bet["opponent_player_id"], bet["amount"])
    await update_bet_status(bet_id, "cancelled")
    await callback.message.edit_text(ui("bet_cancelled", "UA", id=bet_id))
    await callback.answer()


async def _resolve_bet(callback: CallbackQuery, bet_id: int, winner: str):
    bet = await get_bet(bet_id)
    if not bet or bet["status"] not in ("open", "duel"):
        await callback.answer("Вже закрита.", show_alert=True)
        return
    creator_id  = bet["creator_player_id"]
    opponent_id = bet.get("opponent_player_id")
    amount      = bet["amount"]
    coeff       = bet.get("coefficient") or 2.0
    commission  = 1 if amount >= 3 and opponent_id else 0

    await unfreeze_chips(creator_id, amount)
    if opponent_id:
        await unfreeze_chips(opponent_id, amount)
        loser_id  = opponent_id if winner == "creator" else creator_id
        winner_id = creator_id  if winner == "creator" else opponent_id
        await change_balance(loser_id,  -amount, "bet_lose",
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

    await update_bet_status(bet_id, "closed",
                             result="win" if winner == "creator" else "lose")
    winner_player = await get_player_by_id(
        creator_id if winner == "creator" else (opponent_id or creator_id)
    )
    name = winner_player["nickname"] if winner_player else "?"
    comm = "\n(утримано 1 шепот комісії)" if commission else ""
    await callback.message.edit_text(
        ui("bet_closed", "UA", id=bet_id, winner=name) + comm,
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bet_win_creator_"))
async def bet_win_creator(callback: CallbackQuery):
    await _resolve_bet(callback, int(callback.data.split("_")[-1]), "creator")

@router.callback_query(F.data.startswith("bet_win_opponent_"))
async def bet_win_opponent(callback: CallbackQuery):
    await _resolve_bet(callback, int(callback.data.split("_")[-1]), "opponent")

@router.callback_query(F.data == "back_active_bets")
async def back_to_bets(callback: CallbackQuery):
    bets = await get_active_bets()
    if not bets:
        await callback.message.edit_text("Активних ставок немає.")
    else:
        await callback.message.edit_reply_markup(reply_markup=active_bets_keyboard(bets))
    await callback.answer()


# ── Оппонент для ставки на Червоність ────────────────────────

@router.callback_query(F.data.startswith("bet_set_opponent_"))
async def bet_set_opponent_start(callback: CallbackQuery, state: FSMContext):
    """Адмін призначає опонента для ставки на Червоність."""
    bet_id = int(callback.data.split("_")[-1])
    from app.database.queries import get_all_players_sorted
    from app.keyboards.main_kb import players_page_keyboard
    players = await get_all_players_sorted()
    await state.update_data(opponent_bet_id=bet_id)
    await callback.message.answer(
        f"👤 Оберіть опонента для ставки #{bet_id}:",
        reply_markup=players_page_keyboard(players, 0, "set_opp")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_opp_"))
async def bet_set_opponent_chosen(callback: CallbackQuery, state: FSMContext, bot: Bot):
    player_db_id = int(callback.data.split("_")[2])
    data         = await state.get_data()
    bet_id       = data.get("opponent_bet_id")
    if not bet_id:
        await callback.answer("Помилка стану", show_alert=True)
        return
    bet    = await get_bet(bet_id)
    player = await get_player_by_id(player_db_id)
    if not bet or not player:
        await callback.answer("Не знайдено", show_alert=True)
        return
    # Заморожуємо у опонента ту ж суму і прив'язуємо
    try:
        wallet = await get_wallet(player_db_id)
        avail  = (wallet["balance"] - wallet["frozen_balance"]) if wallet else 0
        if avail >= bet["amount"]:
            await freeze_chips(player_db_id, bet["amount"])
        await update_bet_status(bet_id, "duel", opponent_id=player_db_id)
    except Exception as e:
        await callback.answer(str(e), show_alert=True)
        await state.clear()
        return
    await state.clear()
    await callback.message.edit_text(
        f"✅ Опонент призначений!\n"
        f"Ставка #{bet_id}: {bet.get('creator_nickname','?')} vs {player['nickname']}\n"
        f"Тепер можна закрити ставку.",
        parse_mode="HTML"
    )
    await callback.answer()


# ── Відправити Шепоти (закрити але утримати виплату) ─────────

@router.callback_query(F.data.startswith("bet_send_chips_"))
async def bet_send_chips(callback: CallbackQuery, bot: Bot):
    """
    Закриває ставку як 'hold' — переможець визначений але шепоти
    будуть відправлені тільки після окремої команди адміна.
    """
    bet_id = int(callback.data.split("_")[-1])
    bet    = await get_bet(bet_id)
    if not bet or bet["status"] not in ("open", "duel"):
        await callback.answer("Ставка вже закрита.", show_alert=True)
        return

    # Показуємо вибір переможця перед утриманням
    from aiogram.utils.keyboard import InlineKeyboardBuilder as IKB
    from aiogram.types import InlineKeyboardButton as IKBtn
    b = IKB()
    b.row(
        IKBtn(text="🏆 Переміг ставочник", callback_data=f"bet_hold_creator_{bet_id}"),
        IKBtn(text="🏆 Переміг опонент",   callback_data=f"bet_hold_opponent_{bet_id}"),
    )
    b.row(IKBtn(text="◀ Назад", callback_data=f"bet_manage_{bet_id}"))
    await callback.message.edit_text(
        f"💸 <b>Відправити Шепоти — ставка #{bet_id}</b>\n\n"
        f"Хто переміг? Шепоти будуть нараховані ПІСЛЯ натискання кнопки 'Відправити'.",
        parse_mode="HTML",
        reply_markup=b.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bet_hold_"))
async def bet_hold_winner(callback: CallbackQuery):
    """Запам'ятовує переможця але не нараховує шепоти одразу."""
    parts  = callback.data.split("_")
    winner = parts[2]   # creator або opponent
    bet_id = int(parts[3])
    bet    = await get_bet(bet_id)
    if not bet:
        await callback.answer("Не знайдено", show_alert=True)
        return

    # Позначаємо переможця в полі result але статус = 'hold'
    await update_bet_status(bet_id, "hold", result=f"pending_{winner}")

    creator_id  = bet["creator_player_id"]
    opponent_id = bet.get("opponent_player_id")
    amount      = bet["amount"]

    # Розморожуємо у обох — шепоти ще не списуємо
    await unfreeze_chips(creator_id, amount)
    if opponent_id:
        await unfreeze_chips(opponent_id, amount)

    w_name = bet.get("creator_nickname", "?") if winner == "creator" else \
             (f"гравець #{bet.get('opponent_player_id','?')}")

    # Показуємо кнопку "Відправити зараз"
    from aiogram.utils.keyboard import InlineKeyboardBuilder as IKB
    from aiogram.types import InlineKeyboardButton as IKBtn
    b = IKB()
    b.row(IKBtn(
        text=f"💸 Відправити Шепоти → {w_name}",
        callback_data=f"bet_payout_{bet_id}"
    ))
    b.row(IKBtn(text="◀ До ставок", callback_data="back_active_bets"))

    await callback.message.edit_text(
        f"⏸ <b>Ставка #{bet_id} — очікує виплати</b>\n\n"
        f"Переможець: <b>{w_name}</b>\n"
        f"Сума: {chips(amount)}\n\n"
        f"Натисни кнопку щоб відправити Шепоти гравцю.",
        parse_mode="HTML",
        reply_markup=b.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bet_payout_"))
async def bet_payout(callback: CallbackQuery, bot: Bot):
    """Фінальна виплата шепотів переможцю."""
    bet_id = int(callback.data.split("_")[-1])
    bet    = await get_bet(bet_id)
    if not bet or bet["status"] != "hold":
        await callback.answer("Вже виплачено або помилка.", show_alert=True)
        return

    result      = bet.get("result", "")
    creator_id  = bet["creator_player_id"]
    opponent_id = bet.get("opponent_player_id")
    amount      = bet["amount"]
    coeff       = bet.get("coefficient") or 2.0
    commission  = 1 if amount >= 3 and opponent_id else 0

    if "creator" in result:
        winner_id = creator_id
        loser_id  = opponent_id
    else:
        winner_id = opponent_id or creator_id
        loser_id  = creator_id if opponent_id else None

    if loser_id:
        await change_balance(loser_id, -amount, "bet_lose",
                             f"Програш ставки #{bet_id}", callback.from_user.id)
    payout = (amount * 2 - commission) if opponent_id else (int(amount * coeff) - commission)
    if winner_id:
        await change_balance(winner_id, payout, "bet_win",
                             f"Виграш ставки #{bet_id}", callback.from_user.id)

    await update_bet_status(bet_id, "closed", result=result.replace("pending_",""))

    winner_player = await get_player_by_id(winner_id) if winner_id else None
    w_name        = winner_player["nickname"] if winner_player else "?"

    await callback.message.edit_text(
        f"✅ <b>Шепоти відправлено!</b>\n\n"
        f"Переможець: <b>{w_name}</b>\n"
        f"+{chips(payout)}\n\n"
        f"Ставку #{bet_id} закрито.",
        parse_mode="HTML"
    )
    # Повідомляємо переможця
    if winner_id:
        await _notify_player(bot, winner_id,
            f"💸 <b>Шепоти отримано!</b>\nВиграш ставки #{bet_id}: +{chips(payout)}")
    await callback.answer()


# ── Ставка у відповідь ───────────────────────────────────────

@router.callback_query(F.data == "bet_respond")
async def bet_respond_start(callback: CallbackQuery, state: FSMContext):
    """Показує всі відкриті ставки на Червоність щоб гравець міг відповісти."""
    p    = await _get_player_or_fail(callback)
    if not p:
        return
    lang         = await get_user_language(callback.from_user.id)
    redness_bets = await get_open_redness_bets()

    if not redness_bets:
        await callback.answer(
            ui("bets_respond_empty", lang),
            show_alert=True
        )
        return

    title = ui("bets_respond_title", lang)
    await state.update_data(player_id=p["id"], player_name=p["nickname"])
    await callback.message.edit_text(
        f"🔄 <b>{title}</b>\n\n"
        f"{'Обери ставку для відповіді:' if lang=='UA' else 'Выбери ставку для ответа:'}",
        parse_mode="HTML",
        reply_markup=redness_opponents_keyboard(redness_bets)
    )
    await state.set_state(BetAgainstState.choose_number)
    await callback.answer()


# ── Видати всі шепоти одночасно ──────────────────────────────

@router.callback_query(F.data == "bet_payout_all")
async def bet_payout_all(callback: CallbackQuery, bot: Bot):
    """Виплачує шепоти по всіх ставках зі статусом hold."""
    from app.database.queries import get_all_hold_bets
    hold_bets = await get_all_hold_bets()
    if not hold_bets:
        await callback.answer("Немає ставок для виплати.", show_alert=True)
        return

    paid_count = 0
    total_paid = 0
    for bet in hold_bets:
        try:
            result      = bet.get("result", "")
            creator_id  = bet["creator_player_id"]
            opponent_id = bet.get("opponent_player_id")
            amount      = bet["amount"]
            coeff       = bet.get("coefficient") or 2.0
            commission  = 1 if amount >= 3 and opponent_id else 0

            if "creator" in result:
                winner_id = creator_id
                loser_id  = opponent_id
            else:
                winner_id = opponent_id or creator_id
                loser_id  = creator_id if opponent_id else None

            if loser_id:
                await change_balance(loser_id, -amount, "bet_lose",
                                     f"Програш ставки #{bet['id']}", callback.from_user.id)
            payout = (amount * 2 - commission) if opponent_id else (int(amount * coeff) - commission)
            if winner_id:
                await change_balance(winner_id, payout, "bet_win",
                                     f"Виграш ставки #{bet['id']}", callback.from_user.id)
                await _notify_player(bot, winner_id,
                    f"💸 <b>Шепоти отримано!</b>\nВиграш ставки #{bet['id']}: +{chips(payout)}")

            await update_bet_status(bet["id"], "closed",
                                     result=result.replace("pending_",""))
            paid_count += 1
            total_paid += payout
        except Exception as e:
            logger.error(f"Помилка виплати ставки #{bet['id']}: {e}")

    await callback.message.edit_text(
        f"✅ <b>Шепоти видано!</b>\n\n"
        f"Виплачено ставок: {paid_count}\n"
        f"Загальна сума: {chips(total_paid)}",
        parse_mode="HTML"
    )
    await callback.answer()
