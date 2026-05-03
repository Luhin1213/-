# app/handlers/spendings.py
import logging
import aiosqlite
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.database.queries import (
    get_player_by_linked_user, get_wallet, freeze_chips, unfreeze_chips,
    change_balance, create_spending, get_pending_spendings,
    get_spending, resolve_spending, is_admin,
)
from app.keyboards.main_kb import (
    spending_menu_keyboard, player_number_keyboard,
    pending_spendings_keyboard, spend_resolve_keyboard,
    spend_confirm_keyboard,
)
from app.utils.states import (
    SpendChooseSeatState, SpendSilenceState, SpendBlindState, SpendBuyRoleState,
)
from app.utils.formatters import chips, SPEND_TYPE_UA
from app.config import ADMIN_IDS, DATABASE_PATH

logger = logging.getLogger(__name__)
router = Router()

# Витрати з фіксованою ціною (не потребують вибору кількості)
FIXED_SPENDS = {
    "spend_change_order": ("change_order", 1),
    "spend_funeral":      ("funeral",      1),
    "spend_know_roles":   ("know_roles",   2),
    "spend_redeal":       ("redeal",       3),
    "spend_bribe":        ("bribe",        3),
    "spend_immunity":     ("immunity",     7),
    "spend_become_char":  ("become_char", 20),
    "spend_discount_50":  ("discount_50",  8),
    "spend_discount_100": ("discount_100",14),
}


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


async def _do_spend(player: dict, spend_type: str, amount: int, bot: Bot,
                    target_number: int = None, comment: str = "",
                    callback: CallbackQuery = None, message: Message = None):
    """Заморожує фішки і створює запит на витрату."""
    wallet = await get_wallet(player["id"])
    avail  = (wallet["balance"] - wallet["frozen_balance"]) if wallet else 0
    if avail < amount:
        err = f"Недостатньо шепот!\nПотрібно: {chips(amount)}, доступно: {chips(avail)}"
        if callback:
            await callback.answer(err, show_alert=True)
        elif message:
            await message.answer(f"❌ {err}")
        return False

    await freeze_chips(player["id"], amount)
    spend_id = await create_spending(player["id"], spend_type, amount, target_number, comment)

    name = SPEND_TYPE_UA.get(spend_type, spend_type)
    tgt  = f" → гравець #{target_number}" if target_number else ""
    comm = f"\n{comment}" if comment else ""
    resp = (
        f"⏳ <b>Запит надіслано!</b>\n\n"
        f"{name}{tgt}{comm}\n"
        f"Сума: {chips(amount)}\n"
        f"Статус: очікує підтвердження адміна"
    )
    if callback:
        await callback.message.edit_text(resp, parse_mode="HTML")
        await callback.answer()
    elif message:
        await message.answer(resp, parse_mode="HTML")

    await _notify_admins(
        bot,
        f"🛒 <b>Нова витрата #{spend_id}</b>\n"
        f"Гравець: {player['nickname']}\n"
        f"{name}{tgt}{comm}\n"
        f"Сума: {chips(amount)}\n\n"
        f"Підтвердь у «📊 Активні ставки»"
    )
    return True


# ── Меню витрат ──────────────────────────────────────────────

@router.message(F.text == "🛒 Витрати")
async def spendings_menu(message: Message):
    await message.answer(
        "🛒 <b>Витрати</b>\n\n"
        "<i>Обери дію. Кожна потребує підтвердження адміна.</i>",
        parse_mode="HTML",
        reply_markup=spending_menu_keyboard()
    )


@router.callback_query(F.data == "spend_cancel_back")
async def spend_cancel_back(callback: CallbackQuery):
    await callback.message.edit_text(
        "🛒 <b>Витрати</b>\n\nОбери дію:",
        parse_mode="HTML",
        reply_markup=spending_menu_keyboard()
    )
    await callback.answer()


# ── Фіксовані витрати — спочатку показуємо підтвердження ────

@router.callback_query(F.data.in_(list(FIXED_SPENDS.keys())))
async def fixed_spend_confirm(callback: CallbackQuery):
    """Показує кнопку підтвердження перед витратою."""
    p = await _get_player_or_fail(callback)
    if not p:
        return

    spend_type, amount = FIXED_SPENDS[callback.data]
    name = SPEND_TYPE_UA.get(spend_type, spend_type)

    # Перевіряємо баланс одразу
    wallet = await get_wallet(p["id"])
    avail  = (wallet["balance"] - wallet["frozen_balance"]) if wallet else 0
    if avail < amount:
        await callback.answer(
            f"Недостатньо шепот! Потрібно {chips(amount)}, є {chips(avail)}",
            show_alert=True
        )
        return

    # Зберігаємо тип у callback через спеціальне ім'я
    short = callback.data.replace("spend_", "")  # напр: change_order
    await callback.message.edit_text(
        f"<b>{name}</b>\n\n"
        f"Вартість: {chips(amount)}\n"
        f"Доступно: {chips(avail)}\n\n"
        f"Підтвердити витрату?",
        parse_mode="HTML",
        reply_markup=spend_confirm_keyboard(short, amount)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("spend_confirm_"))
async def fixed_spend_execute(callback: CallbackQuery, bot: Bot):
    """Виконує фіксовану витрату після підтвердження."""
    short = callback.data.replace("spend_confirm_", "")
    # Відновлюємо spend_type
    spend_type = short
    amount = dict(FIXED_SPENDS).get(f"spend_{short}", (None, 0))[1]

    # Якщо не знайшли — шукаємо напряму в словнику значень
    for cb_key, (stype, amt) in FIXED_SPENDS.items():
        if stype == short or cb_key == f"spend_{short}":
            spend_type = stype
            amount = amt
            break

    p = await get_player_by_linked_user(callback.from_user.id)
    if not p:
        await callback.answer("Профіль не знайдено", show_alert=True)
        return

    await _do_spend(p, spend_type, amount, bot, callback=callback)


# ── Вибір місця — потрібен номер ────────────────────────────

@router.callback_query(F.data == "spend_choose_seat")
async def choose_seat_start(callback: CallbackQuery, state: FSMContext):
    p = await _get_player_or_fail(callback)
    if not p:
        return
    wallet = await get_wallet(p["id"])
    avail  = (wallet["balance"] - wallet["frozen_balance"]) if wallet else 0
    if avail < 2:
        await callback.answer(f"Потрібно 2 шепоти, є {avail}.", show_alert=True)
        return
    await state.update_data(player_id=p["id"])
    await callback.message.edit_text(
        "💺 <b>Вибір місця за столом — 2 шепоти</b>\n\nОбери номер місця (1–15):",
        parse_mode="HTML",
        reply_markup=player_number_keyboard("seat_num", 15)
    )
    await state.set_state(SpendChooseSeatState.enter_number)
    await callback.answer()


@router.callback_query(SpendChooseSeatState.enter_number, F.data.startswith("seat_num_"))
async def choose_seat_number(callback: CallbackQuery, state: FSMContext, bot: Bot):
    number = int(callback.data.split("_")[-1])
    await state.clear()
    p = await get_player_by_linked_user(callback.from_user.id)
    if not p:
        await callback.answer("Профіль не знайдено", show_alert=True)
        return
    await _do_spend(p, "choose_seat", 2, bot, target_number=number, callback=callback)


# ── Купити роль — гравець пише яку ──────────────────────────

@router.callback_query(F.data == "spend_buy_role")
async def buy_role_start(callback: CallbackQuery, state: FSMContext):
    p = await _get_player_or_fail(callback)
    if not p:
        return
    wallet = await get_wallet(p["id"])
    avail  = (wallet["balance"] - wallet["frozen_balance"]) if wallet else 0
    if avail < 4:
        await callback.answer(f"Потрібно 4 шепоти, є {avail}.", show_alert=True)
        return
    await state.update_data(player_id=p["id"])
    await callback.message.edit_text(
        "🎭 <b>Купити роль — 4 шепоти</b>\n\n"
        "Напиши яку роль хочеш:\n"
        "<i>(наприклад: Шериф, Лікар, Дон)</i>",
        parse_mode="HTML"
    )
    await state.set_state(SpendBuyRoleState.enter_role_text)
    await callback.answer()


@router.message(SpendBuyRoleState.enter_role_text)
async def buy_role_text(message: Message, state: FSMContext, bot: Bot):
    role_text = message.text.strip()
    if len(role_text) > 100:
        await message.answer("❌ Занадто довго. Спробуй коротше:")
        return
    await state.clear()
    p = await get_player_by_linked_user(message.from_user.id)
    if not p:
        await message.answer("Профіль не знайдено.")
        return
    await _do_spend(p, "buy_role", 4, bot,
                    comment=f"Бажана роль: {role_text}", message=message)


# ── Змусити мовчати — вибір номера ──────────────────────────

@router.callback_query(F.data == "spend_silence")
async def silence_start(callback: CallbackQuery, state: FSMContext):
    p = await _get_player_or_fail(callback)
    if not p:
        return
    wallet = await get_wallet(p["id"])
    avail  = (wallet["balance"] - wallet["frozen_balance"]) if wallet else 0
    if avail < 4:
        await callback.answer(f"Потрібно 4 шепоти, є {avail}.", show_alert=True)
        return
    await state.update_data(player_id=p["id"])
    await callback.message.edit_text(
        "🤫 <b>Змусити мовчати — 4 шепоти</b>\n\nОбери номер гравця (1–15):",
        parse_mode="HTML",
        reply_markup=player_number_keyboard("silence_num", 15)
    )
    await state.set_state(SpendSilenceState.enter_number)
    await callback.answer()


@router.callback_query(SpendSilenceState.enter_number, F.data.startswith("silence_num_"))
async def silence_number(callback: CallbackQuery, state: FSMContext, bot: Bot):
    number = int(callback.data.split("_")[-1])
    await state.clear()
    p = await get_player_by_linked_user(callback.from_user.id)
    if not p:
        await callback.answer("Профіль не знайдено", show_alert=True)
        return
    await _do_spend(p, "silence", 4, bot, target_number=number, callback=callback)


# ── Змусити осліпнути — вибір номера ────────────────────────

@router.callback_query(F.data == "spend_blind")
async def blind_start(callback: CallbackQuery, state: FSMContext):
    p = await _get_player_or_fail(callback)
    if not p:
        return
    wallet = await get_wallet(p["id"])
    avail  = (wallet["balance"] - wallet["frozen_balance"]) if wallet else 0
    if avail < 3:
        await callback.answer(f"Потрібно 3 шепоти, є {avail}.", show_alert=True)
        return
    await state.update_data(player_id=p["id"])
    await callback.message.edit_text(
        "🙈 <b>Змусити осліпнути — 3 шепоти</b>\n\nОбери номер гравця (1–15):",
        parse_mode="HTML",
        reply_markup=player_number_keyboard("blind_num", 15)
    )
    await state.set_state(SpendBlindState.enter_number)
    await callback.answer()


@router.callback_query(SpendBlindState.enter_number, F.data.startswith("blind_num_"))
async def blind_number(callback: CallbackQuery, state: FSMContext, bot: Bot):
    number = int(callback.data.split("_")[-1])
    await state.clear()
    p = await get_player_by_linked_user(callback.from_user.id)
    if not p:
        await callback.answer("Профіль не знайдено", show_alert=True)
        return
    await _do_spend(p, "blind", 3, bot, target_number=number, callback=callback)


# ══════════════════════════════════════════════
# АДМІН: підтвердження / скасування витрат
# ══════════════════════════════════════════════

@router.callback_query(F.data.startswith("spend_resolve_"))
async def spend_resolve_select(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нема прав", show_alert=True)
        return
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
        f"{name}{tgt}{comm}\n"
        f"Сума: {chips(spend['amount'])}\n\n"
        f"Дія:",
        parse_mode="HTML",
        reply_markup=spend_resolve_keyboard(spend_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("spend_ok_"))
async def spend_approve(callback: CallbackQuery, bot: Bot):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нема прав", show_alert=True)
        return
    spend_id = int(callback.data.split("_")[-1])
    spend    = await get_spending(spend_id)
    if not spend or spend["status"] != "pending":
        await callback.answer("Вже оброблено.", show_alert=True)
        return
    name = SPEND_TYPE_UA.get(spend["spend_type"], spend["spend_type"])
    await unfreeze_chips(spend["player_id"], spend["amount"])
    await change_balance(
        spend["player_id"], -spend["amount"], "spend", name, callback.from_user.id
    )
    await resolve_spending(spend_id, "approved")
    await callback.message.edit_text(
        f"✅ Витрату #{spend_id} підтверджено. -{chips(spend['amount'])}"
    )
    # Повідомити гравця
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
            try:
                await bot.send_message(
                    row[0],
                    f"✅ <b>Твою витрату підтверджено!</b>\n"
                    f"{name}{tgt}{comm}\n"
                    f"-{chips(spend['amount'])}",
                    parse_mode="HTML"
                )
            except Exception:
                pass
    await callback.answer()


@router.callback_query(F.data.startswith("spend_no_"))
async def spend_cancel_admin(callback: CallbackQuery, bot: Bot):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нема прав", show_alert=True)
        return
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
            try:
                await bot.send_message(
                    row[0],
                    f"❌ Твою витрату скасовано.\n"
                    f"Шепоти повернуто: {chips(spend['amount'])}",
                    parse_mode="HTML"
                )
            except Exception:
                pass
    await callback.answer()
