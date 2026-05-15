# app/handlers/spendings.py
import logging
import aiosqlite
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.database.queries import (
    get_player_by_linked_user, get_wallet, freeze_chips, unfreeze_chips,
    change_balance, create_spending, get_pending_spendings,
    get_spending, resolve_spending, is_admin, get_user_language,
)
from app.keyboards.main_kb import (
    spending_menu_keyboard, dead_spending_keyboard, player_number_keyboard,
    pending_spendings_keyboard, spend_resolve_keyboard, spend_confirm_keyboard,
)
from app.utils.states import (
    SpendChooseSeatState, SpendSilenceState, SpendBlindState, SpendBuyRoleState,
)
from app.utils.formatters import chips, SPEND_TYPE_UA
from app.utils.i18n import ui
from app.config import ADMIN_IDS, DATABASE_PATH

logger = logging.getLogger(__name__)
router = Router()

FIXED_SPENDS = {
    "spend_change_order": ("change_order", 1),
    "spend_redeal":       ("redeal",       3),
    "spend_bribe":        ("bribe",        2),
    "spend_immunity":     ("immunity",     7),
    "spend_become_char":  ("become_char", 20),
    "spend_discount_50":  ("discount_50", 10),
    "spend_discount_100": ("discount_100",18),
    "spend_funeral":      ("funeral",      1),
    "spend_know_roles":   ("know_roles",   2),
}


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


async def _do_spend(player: dict, spend_type: str, amount: int, bot: Bot,
                    lang: str, target_number: int = None, comment: str = "",
                    callback: CallbackQuery = None, message: Message = None):
    wallet = await get_wallet(player["id"])
    avail  = (wallet["balance"] - wallet["frozen_balance"]) if wallet else 0
    if avail < amount:
        err = ui("spend_no_chips", lang, need=chips(amount), have=chips(avail))
        if callback:
            await callback.answer(err, show_alert=True)
        elif message:
            await message.answer(f"❌ {err}")
        return False

    await freeze_chips(player["id"], amount)
    spend_id = await create_spending(player["id"], spend_type, amount, target_number, comment)

    name   = SPEND_TYPE_UA.get(spend_type, spend_type)
    tgt    = f" → {'гравець' if lang=='UA' else 'игрок'} #{target_number}" if target_number else ""
    comm   = f"\n{comment}" if comment else ""
    resp   = ui("spend_sent", lang, name=name, target=tgt, comment=comm, amount=chips(amount))

    if callback:
        await callback.message.edit_text(resp, parse_mode="HTML")
        await callback.answer()
    elif message:
        await message.answer(resp, parse_mode="HTML")

    await _notify_admins(bot,
        f"🛒 <b>Нова витрата #{spend_id}</b>\n"
        f"{'Гравець' if lang=='UA' else 'Игрок'}: {player['nickname']}\n"
        f"{name}{tgt}{comm}\n{chips(amount)}\n\n"
        f"Підтвердь у «📊 Активні ставки»")
    return True


# ── Меню витрат ──────────────────────────────────────────────

@router.message(F.text.in_(["🛒 Витрати", "🛒 Траты"]))
async def spendings_menu(message: Message):
    lang = await get_user_language(message.from_user.id)
    await message.answer(
        f"🛒 <b>{ui('spend_title', lang)}</b>\n\n<i>{ui('spend_desc', lang)}</i>",
        parse_mode="HTML",
        reply_markup=spending_menu_keyboard()
    )


@router.callback_query(F.data == "spend_dead_menu")
async def dead_menu(callback: CallbackQuery):
    lang = await get_user_language(callback.from_user.id)
    await callback.message.edit_text(
        f"💀 <b>{ui('spend_dead_title', lang)}</b>",
        parse_mode="HTML",
        reply_markup=dead_spending_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "spend_back_main")
async def back_to_spend_main(callback: CallbackQuery):
    lang = await get_user_language(callback.from_user.id)
    await callback.message.edit_text(
        f"🛒 <b>{ui('spend_title', lang)}</b>\n\n<i>{ui('spend_desc', lang)}</i>",
        parse_mode="HTML",
        reply_markup=spending_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "spend_cancel_back")
async def spend_cancel_back(callback: CallbackQuery):
    lang = await get_user_language(callback.from_user.id)
    await callback.message.edit_text(
        f"🛒 <b>{ui('spend_title', lang)}</b>\n\n<i>{ui('spend_desc', lang)}</i>",
        parse_mode="HTML",
        reply_markup=spending_menu_keyboard()
    )
    await callback.answer()


# ── Фіксовані витрати ────────────────────────────────────────

@router.callback_query(F.data.in_(list(FIXED_SPENDS.keys())))
async def fixed_spend_confirm(callback: CallbackQuery):
    p = await _get_player_or_fail(callback)
    if not p:
        return
    lang = await get_user_language(callback.from_user.id)
    spend_type, amount = FIXED_SPENDS[callback.data]
    name   = SPEND_TYPE_UA.get(spend_type, spend_type)
    wallet = await get_wallet(p["id"])
    avail  = (wallet["balance"] - wallet["frozen_balance"]) if wallet else 0
    if avail < amount:
        await callback.answer(
            ui("spend_no_chips", lang, need=chips(amount), have=chips(avail)),
            show_alert=True
        )
        return
    short = callback.data.replace("spend_", "")
    confirm_txt = f"✅ {'Підтвердити' if lang=='UA' else 'Подтвердить'}"
    cancel_txt  = f"❌ {'Скасувати' if lang=='UA' else 'Отменить'}"
    await callback.message.edit_text(
        f"<b>{name}</b>\n\n"
        f"{'Вартість' if lang=='UA' else 'Стоимость'}: {chips(amount)}\n"
        f"{'Доступно' if lang=='UA' else 'Доступно'}: {chips(avail)}\n\n"
        f"{'Підтвердити витрату?' if lang=='UA' else 'Подтвердить трату?'}",
        parse_mode="HTML",
        reply_markup=spend_confirm_keyboard(short, amount)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("spend_confirm_"))
async def fixed_spend_execute(callback: CallbackQuery, bot: Bot):
    short = callback.data.replace("spend_confirm_", "")
    spend_type, amount = None, 0
    for cb_key, (stype, amt) in FIXED_SPENDS.items():
        if stype == short or cb_key == f"spend_{short}":
            spend_type = stype
            amount = amt
            break
    if not spend_type:
        await callback.answer("Помилка", show_alert=True)
        return
    p    = await get_player_by_linked_user(callback.from_user.id)
    lang = await get_user_language(callback.from_user.id)
    if not p:
        await callback.answer(ui("no_profile", lang), show_alert=True)
        return
    await _do_spend(p, spend_type, amount, bot, lang, callback=callback)


# ── Вибір місця ──────────────────────────────────────────────

@router.callback_query(F.data == "spend_choose_seat")
async def choose_seat_start(callback: CallbackQuery, state: FSMContext):
    p    = await _get_player_or_fail(callback)
    if not p:
        return
    lang   = await get_user_language(callback.from_user.id)
    wallet = await get_wallet(p["id"])
    avail  = (wallet["balance"] - wallet["frozen_balance"]) if wallet else 0
    if avail < 2:
        await callback.answer(ui("spend_no_chips", lang, need=chips(2), have=chips(avail)), show_alert=True)
        return
    await state.update_data(player_id=p["id"])
    await callback.message.edit_text(
        ui("spend_choose_seat", lang), parse_mode="HTML",
        reply_markup=player_number_keyboard("seat_num", 15)
    )
    await state.set_state(SpendChooseSeatState.enter_number)
    await callback.answer()


@router.callback_query(SpendChooseSeatState.enter_number, F.data.startswith("seat_num_"))
async def choose_seat_number(callback: CallbackQuery, state: FSMContext, bot: Bot):
    number = int(callback.data.split("_")[-1])
    await state.clear()
    p    = await get_player_by_linked_user(callback.from_user.id)
    lang = await get_user_language(callback.from_user.id)
    if not p:
        await callback.answer(ui("no_profile", lang), show_alert=True)
        return
    await _do_spend(p, "choose_seat", 2, bot, lang, target_number=number, callback=callback)


# ── Купити роль ──────────────────────────────────────────────

@router.callback_query(F.data == "spend_buy_role")
async def buy_role_start(callback: CallbackQuery, state: FSMContext):
    p    = await _get_player_or_fail(callback)
    if not p:
        return
    lang   = await get_user_language(callback.from_user.id)
    wallet = await get_wallet(p["id"])
    avail  = (wallet["balance"] - wallet["frozen_balance"]) if wallet else 0
    if avail < 4:
        await callback.answer(ui("spend_no_chips", lang, need=chips(4), have=chips(avail)), show_alert=True)
        return
    await state.update_data(player_id=p["id"])
    await callback.message.edit_text(ui("spend_buy_role_ask", lang), parse_mode="HTML")
    await state.set_state(SpendBuyRoleState.enter_role_text)
    await callback.answer()


@router.message(SpendBuyRoleState.enter_role_text)
async def buy_role_text(message: Message, state: FSMContext, bot: Bot):
    role_text = message.text.strip()
    if len(role_text) > 100:
        lang = await get_user_language(message.from_user.id)
        await message.answer("❌ Занадто довго." if lang=="UA" else "❌ Слишком длинно.")
        return
    await state.clear()
    p    = await get_player_by_linked_user(message.from_user.id)
    lang = await get_user_language(message.from_user.id)
    if not p:
        await message.answer(ui("no_profile", lang))
        return
    await _do_spend(p, "buy_role", 4, bot, lang,
                    comment=f"{'Бажана роль' if lang=='UA' else 'Желаемая роль'}: {role_text}",
                    message=message)


# ── Кляп у рот ───────────────────────────────────────────────

@router.callback_query(F.data == "spend_silence")
async def silence_start(callback: CallbackQuery, state: FSMContext):
    p    = await _get_player_or_fail(callback)
    if not p:
        return
    lang   = await get_user_language(callback.from_user.id)
    wallet = await get_wallet(p["id"])
    avail  = (wallet["balance"] - wallet["frozen_balance"]) if wallet else 0
    if avail < 4:
        await callback.answer(ui("spend_no_chips", lang, need=chips(4), have=chips(avail)), show_alert=True)
        return
    await state.update_data(player_id=p["id"])
    await callback.message.edit_text(
        ui("spend_silence_ask", lang), parse_mode="HTML",
        reply_markup=player_number_keyboard("silence_num", 15)
    )
    await state.set_state(SpendSilenceState.enter_number)
    await callback.answer()


@router.callback_query(SpendSilenceState.enter_number, F.data.startswith("silence_num_"))
async def silence_number(callback: CallbackQuery, state: FSMContext, bot: Bot):
    number = int(callback.data.split("_")[-1])
    await state.clear()
    p    = await get_player_by_linked_user(callback.from_user.id)
    lang = await get_user_language(callback.from_user.id)
    if not p:
        await callback.answer(ui("no_profile", lang), show_alert=True)
        return
    await _do_spend(p, "silence", 4, bot, lang, target_number=number, callback=callback)


# ── Осліпнути ────────────────────────────────────────────────

@router.callback_query(F.data == "spend_blind")
async def blind_start(callback: CallbackQuery, state: FSMContext):
    p    = await _get_player_or_fail(callback)
    if not p:
        return
    lang   = await get_user_language(callback.from_user.id)
    wallet = await get_wallet(p["id"])
    avail  = (wallet["balance"] - wallet["frozen_balance"]) if wallet else 0
    if avail < 3:
        await callback.answer(ui("spend_no_chips", lang, need=chips(3), have=chips(avail)), show_alert=True)
        return
    await state.update_data(player_id=p["id"])
    await callback.message.edit_text(
        ui("spend_blind_ask", lang), parse_mode="HTML",
        reply_markup=player_number_keyboard("blind_num", 15)
    )
    await state.set_state(SpendBlindState.enter_number)
    await callback.answer()


@router.callback_query(SpendBlindState.enter_number, F.data.startswith("blind_num_"))
async def blind_number(callback: CallbackQuery, state: FSMContext, bot: Bot):
    number = int(callback.data.split("_")[-1])
    await state.clear()
    p    = await get_player_by_linked_user(callback.from_user.id)
    lang = await get_user_language(callback.from_user.id)
    if not p:
        await callback.answer(ui("no_profile", lang), show_alert=True)
        return
    await _do_spend(p, "blind", 3, bot, lang, target_number=number, callback=callback)


# ── Адмін: підтвердження / скасування ───────────────────────

@router.callback_query(F.data.startswith("spend_resolve_"))
async def spend_resolve_select(callback: CallbackQuery):
    spend_id = int(callback.data.split("_")[-1])
    spend    = await get_spending(spend_id)
    if not spend:
        await callback.answer("Не знайдено", show_alert=True)
        return
    name = SPEND_TYPE_UA.get(spend["spend_type"], spend["spend_type"])
    tgt  = f" → #{spend['target_number']}" if spend.get("target_number") else ""
    comm = f"\n{spend['comment']}" if spend.get("comment") else ""
    await callback.message.answer(
        f"🛒 <b>Витрата #{spend_id}</b>\n\n"
        f"Гравець: {spend.get('player_nickname','?')}\n"
        f"{name}{tgt}{comm}\n{chips(spend['amount'])}\n\nДія:",
        parse_mode="HTML",
        reply_markup=spend_resolve_keyboard(spend_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("spend_ok_"))
async def spend_approve(callback: CallbackQuery, bot: Bot):
    spend_id = int(callback.data.split("_")[-1])
    spend    = await get_spending(spend_id)
    if not spend or spend["status"] != "pending":
        await callback.answer("Вже оброблено.", show_alert=True)
        return
    name = SPEND_TYPE_UA.get(spend["spend_type"], spend["spend_type"])
    await unfreeze_chips(spend["player_id"], spend["amount"])
    await change_balance(spend["player_id"], -spend["amount"], "spend", name, callback.from_user.id)
    await resolve_spending(spend_id, "approved")
    await callback.message.edit_text(
        f"✅ Витрату #{spend_id} підтверджено. -{chips(spend['amount'])}"
    )
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "SELECT u.telegram_id FROM users u "
            "JOIN players p ON p.linked_user_id=u.id WHERE p.id=?",
            (spend["player_id"],)
        )
        row = await cur.fetchone()
        if row:
            tgt  = f" → #{spend['target_number']}" if spend.get("target_number") else ""
            comm = f"\n{spend['comment']}" if spend.get("comment") else ""
            lang = await get_user_language(row[0])
            try:
                await bot.send_message(
                    row[0],
                    ui("spend_confirmed", lang,
                       name=name, target=tgt, comment=comm,
                       amount=chips(spend["amount"])),
                    parse_mode="HTML"
                )
            except Exception:
                pass
    await callback.answer()


@router.callback_query(F.data.startswith("spend_no_"))
async def spend_cancel_admin(callback: CallbackQuery, bot: Bot):
    spend_id = int(callback.data.split("_")[-1])
    spend    = await get_spending(spend_id)
    if not spend or spend["status"] != "pending":
        await callback.answer("Вже оброблено.", show_alert=True)
        return
    await unfreeze_chips(spend["player_id"], spend["amount"])
    await resolve_spending(spend_id, "cancelled")
    await callback.message.edit_text(
        f"❌ Витрату #{spend_id} скасовано. Шепоти повернуто."
    )
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "SELECT u.telegram_id FROM users u "
            "JOIN players p ON p.linked_user_id=u.id WHERE p.id=?",
            (spend["player_id"],)
        )
        row = await cur.fetchone()
        if row:
            lang = await get_user_language(row[0])
            try:
                await bot.send_message(
                    row[0],
                    ui("spend_cancelled", lang, amount=chips(spend["amount"])),
                    parse_mode="HTML"
                )
            except Exception:
                pass
    await callback.answer()





# ── Випивки мені! ─────────────────────────────────────────────

from aiogram.fsm.state import StatesGroup as _SG, State as _S

class SpendDrinkState(_SG):
    enter_order = _S()


@router.callback_query(F.data == "spend_drink")
async def drink_start(callback: CallbackQuery, state: FSMContext):
    p = await _get_player_or_fail(callback)
    if not p:
        return
    lang   = await get_user_language(callback.from_user.id)
    wallet = await get_wallet(p["id"])
    avail  = (wallet["balance"] - wallet["frozen_balance"]) if wallet else 0
    if avail < 8:
        await callback.answer(
            ui("spend_no_chips", lang, need=chips(8), have=chips(avail)),
            show_alert=True
        )
        return
    await state.update_data(player_id=p["id"])
    await callback.message.edit_text(
        "🍹 <b>Випивки мені! — 8 шепотів</b>\n\n"
        "Напиши що замовляєш:\n"
        "<i>(наприклад: пиво, коктейль, сік...)</i>",
        parse_mode="HTML"
    )
    await state.set_state(SpendDrinkState.enter_order)
    await callback.answer()


@router.message(SpendDrinkState.enter_order)
async def drink_order(message: Message, state: FSMContext, bot: Bot):
    order = message.text.strip()
    if len(order) > 150:
        await message.answer("❌ Занадто довго. Скоротіть замовлення:")
        return
    await state.clear()
    p    = await get_player_by_linked_user(message.from_user.id)
    lang = await get_user_language(message.from_user.id)
    if not p:
        await message.answer(ui("no_profile", lang))
        return
    await _do_spend(
        p, "drink", 8, bot, lang,
        comment=f"🍹 Замовлення: {order}",
        message=message
    )
