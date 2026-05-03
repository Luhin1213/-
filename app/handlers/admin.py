# app/handlers/admin.py
import logging
import aiosqlite
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Filter

from app.database.queries import (
    is_admin, get_all_players_sorted, get_player_by_id,
    change_balance, get_active_bonus_types, get_bonus_type,
    get_user_by_telegram_id, link_player_to_user,
    get_player_by_player_id, get_wallet, search_players,
    create_bet, freeze_chips,
)
from app.keyboards.main_kb import (
    main_menu_admin, players_page_keyboard, bonus_types_keyboard,
    admin_amount_keyboard, search_results_keyboard,
    admin_bet_type_keyboard, player_number_keyboard,
    color_keyboard, amount_keyboard,
)
from app.services.sheets_service import sync_players_from_sheets
from app.utils.states import (
    AddChipsState, SubtractChipsState, GiveBonusState,
    LinkPlayerState, AdminBetState, SearchPlayerState,
)
from app.utils.formatters import format_profile, chips, COLOR_UA, BET_TYPE_UA
from app.config import DATABASE_PATH

logger = logging.getLogger(__name__)
router = Router()


class AdminFilter(Filter):
    async def __call__(self, message: Message) -> bool:
        return await is_admin(message.from_user.id)

router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


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


# ── Список гравців ───────────────────────────────────────────

@router.message(F.text == "📜 Список гравців")
async def players_list_start(message: Message):
    players = await get_all_players_sorted()
    if not players:
        await message.answer("Немає гравців. Синхронізуй: 🔄 Оновити статистику")
        return
    await message.answer(
        f"📜 <b>Список гравців</b> ({len(players)} осіб):",
        parse_mode="HTML",
        reply_markup=players_page_keyboard(players, 0, "view")
    )

@router.callback_query(F.data.startswith("page_view_"))
async def players_list_page(callback: CallbackQuery):
    page = int(callback.data.split("_")[-1])
    players = await get_all_players_sorted()
    await callback.message.edit_reply_markup(
        reply_markup=players_page_keyboard(players, page, "view")
    )
    await callback.answer()

@router.callback_query(F.data == "search_view")
async def search_view_start(callback: CallbackQuery, state: FSMContext):
    await state.update_data(search_action="view")
    await callback.message.edit_text("🔍 Введи ім'я гравця:")
    await state.set_state(SearchPlayerState.enter_query)
    await callback.answer()

@router.callback_query(F.data.startswith("view_"))
async def view_player_profile(callback: CallbackQuery):
    player_id = int(callback.data.split("_")[1])
    player = await get_player_by_id(player_id)
    if not player:
        await callback.answer("Не знайдено", show_alert=True)
        return
    wallet = await get_wallet(player_id)
    bal = wallet["balance"] if wallet else 0
    frz = wallet["frozen_balance"] if wallet else 0
    text = format_profile(player) + f"\n\n🎰 Шепоти: {bal} (доступно {bal-frz})"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


# ── Пошук (загальний) ────────────────────────────────────────

@router.message(SearchPlayerState.enter_query)
async def search_player_query(message: Message, state: FSMContext):
    query = message.text.strip()
    data = await state.get_data()
    action = data.get("search_action", "view")
    results = await search_players(query)
    if not results:
        await message.answer(f"❌ Гравців з іменем «{query}» не знайдено.")
        await state.clear()
        return
    await message.answer(
        f"🔍 Знайдено {len(results)}:",
        reply_markup=search_results_keyboard(results, action)
    )
    await state.clear()


# ── Видати фішки ─────────────────────────────────────────────

@router.message(F.text == "➕ Видати фішки")
async def add_chips_start(message: Message, state: FSMContext):
    players = await get_all_players_sorted()
    if not players:
        await message.answer("Немає гравців.")
        return
    await message.answer(
        "➕ <b>Видача фішок</b>\n\nОбери гравця:",
        parse_mode="HTML",
        reply_markup=players_page_keyboard(players, 0, "select_add")
    )
    await state.set_state(AddChipsState.choose_player)

@router.callback_query(AddChipsState.choose_player, F.data.startswith("page_select_add_"))
async def add_chips_page(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[-1])
    players = await get_all_players_sorted()
    await callback.message.edit_reply_markup(
        reply_markup=players_page_keyboard(players, page, "select_add")
    )
    await callback.answer()

@router.callback_query(AddChipsState.choose_player, F.data == "search_select_add")
async def add_chips_search(callback: CallbackQuery, state: FSMContext):
    await state.update_data(search_action="select_add")
    await callback.message.edit_text("🔍 Введи ім'я гравця:")
    await state.set_state(SearchPlayerState.enter_query)
    await callback.answer()

@router.callback_query(AddChipsState.choose_player, F.data.startswith("select_add_"))
async def add_chips_player_chosen(callback: CallbackQuery, state: FSMContext):
    player_id = int(callback.data.split("_")[2])
    player = await get_player_by_id(player_id)
    if not player:
        await callback.answer("Не знайдено", show_alert=True)
        return
    await state.update_data(player_id=player_id, player_name=player["nickname"])
    await callback.message.edit_text(
        f"➕ Видача для: <b>{player['nickname']}</b>\n\nОбери кількість (1–10):",
        parse_mode="HTML",
        reply_markup=admin_amount_keyboard("add_amount")
    )
    await state.set_state(AddChipsState.enter_amount)
    await callback.answer()

@router.callback_query(AddChipsState.enter_amount, F.data.startswith("add_amount_"))
async def add_chips_amount(callback: CallbackQuery, state: FSMContext):
    amount = int(callback.data.split("_")[-1])
    await state.update_data(amount=amount)
    data = await state.get_data()
    await callback.message.edit_text(
        f"➕ {data['player_name']}: +{chips(amount)}\n\nКоментар (або —):"
    )
    await state.set_state(AddChipsState.enter_comment)
    await callback.answer()

@router.message(AddChipsState.enter_comment)
async def add_chips_comment(message: Message, state: FSMContext, bot: Bot):
    comment = message.text.strip()
    if comment == "—":
        comment = "Нарахування адміністратором"
    data = await state.get_data()
    try:
        await change_balance(data["player_id"], data["amount"], "add", comment, message.from_user.id)
        await message.answer(
            f"✅ +{chips(data['amount'])} → {data['player_name']}\n{comment}",
            reply_markup=main_menu_admin()
        )
        await _notify_player(bot, data["player_id"],
            f"🎰 <b>Тобі нараховано!</b>\n+{chips(data['amount'])}\nПричина: {comment}")
    except Exception as e:
        await message.answer(f"❌ {e}")
    await state.clear()


# ── Списати фішки ────────────────────────────────────────────

@router.message(F.text == "➖ Списати фішки")
async def sub_chips_start(message: Message, state: FSMContext):
    players = await get_all_players_sorted()
    if not players:
        await message.answer("Немає гравців.")
        return
    await message.answer(
        "➖ <b>Списання фішок</b>\n\nОбери гравця:",
        parse_mode="HTML",
        reply_markup=players_page_keyboard(players, 0, "select_sub")
    )
    await state.set_state(SubtractChipsState.choose_player)

@router.callback_query(SubtractChipsState.choose_player, F.data.startswith("page_select_sub_"))
async def sub_chips_page(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[-1])
    players = await get_all_players_sorted()
    await callback.message.edit_reply_markup(
        reply_markup=players_page_keyboard(players, page, "select_sub")
    )
    await callback.answer()

@router.callback_query(SubtractChipsState.choose_player, F.data == "search_select_sub")
async def sub_chips_search(callback: CallbackQuery, state: FSMContext):
    await state.update_data(search_action="select_sub")
    await callback.message.edit_text("🔍 Введи ім'я гравця:")
    await state.set_state(SearchPlayerState.enter_query)
    await callback.answer()

@router.callback_query(SubtractChipsState.choose_player, F.data.startswith("select_sub_"))
async def sub_chips_player_chosen(callback: CallbackQuery, state: FSMContext):
    player_id = int(callback.data.split("_")[2])
    player = await get_player_by_id(player_id)
    if not player:
        await callback.answer("Не знайдено", show_alert=True)
        return
    await state.update_data(player_id=player_id, player_name=player["nickname"])
    await callback.message.edit_text(
        f"➖ Списання у: <b>{player['nickname']}</b>\n\nОбери кількість (1–10):",
        parse_mode="HTML",
        reply_markup=admin_amount_keyboard("sub_amount")
    )
    await state.set_state(SubtractChipsState.enter_amount)
    await callback.answer()

@router.callback_query(SubtractChipsState.enter_amount, F.data.startswith("sub_amount_"))
async def sub_chips_amount(callback: CallbackQuery, state: FSMContext):
    amount = int(callback.data.split("_")[-1])
    await state.update_data(amount=amount)
    data = await state.get_data()
    await callback.message.edit_text(
        f"➖ {data['player_name']}: -{chips(amount)}\n\nКоментар (або —):"
    )
    await state.set_state(SubtractChipsState.enter_comment)
    await callback.answer()

@router.message(SubtractChipsState.enter_comment)
async def sub_chips_comment(message: Message, state: FSMContext, bot: Bot):
    comment = message.text.strip()
    if comment == "—":
        comment = "Списання адміністратором"
    data = await state.get_data()
    try:
        await change_balance(data["player_id"], -data["amount"], "subtract", comment, message.from_user.id)
        await message.answer(
            f"✅ -{chips(data['amount'])} у {data['player_name']}\n{comment}",
            reply_markup=main_menu_admin()
        )
        await _notify_player(bot, data["player_id"],
            f"➖ <b>Адмін списав шепоти</b>\n-{chips(data['amount'])}\nПричина: {comment}")
    except ValueError as e:
        await message.answer(f"❌ {e}")
    except Exception as e:
        await message.answer(f"❌ Помилка: {e}")
    await state.clear()


# ── Видати бонус ─────────────────────────────────────────────

@router.message(F.text == "🎁 Видати бонус")
async def bonus_start(message: Message, state: FSMContext):
    players = await get_all_players_sorted()
    if not players:
        await message.answer("Немає гравців.")
        return
    await message.answer(
        "🎁 <b>Видача бонусу</b>\n\nОбери гравця:",
        parse_mode="HTML",
        reply_markup=players_page_keyboard(players, 0, "select_bonus")
    )
    await state.set_state(GiveBonusState.choose_player)

@router.callback_query(GiveBonusState.choose_player, F.data.startswith("page_select_bonus_"))
async def bonus_page(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[-1])
    players = await get_all_players_sorted()
    await callback.message.edit_reply_markup(
        reply_markup=players_page_keyboard(players, page, "select_bonus")
    )
    await callback.answer()

@router.callback_query(GiveBonusState.choose_player, F.data == "search_select_bonus")
async def bonus_search(callback: CallbackQuery, state: FSMContext):
    await state.update_data(search_action="select_bonus")
    await callback.message.edit_text("🔍 Введи ім'я гравця:")
    await state.set_state(SearchPlayerState.enter_query)
    await callback.answer()

@router.callback_query(GiveBonusState.choose_player, F.data.startswith("select_bonus_"))
async def bonus_player_chosen(callback: CallbackQuery, state: FSMContext):
    player_id = int(callback.data.split("_")[2])
    player = await get_player_by_id(player_id)
    if not player:
        await callback.answer("Не знайдено", show_alert=True)
        return
    bonuses = await get_active_bonus_types()
    await state.update_data(player_id=player_id, player_name=player["nickname"])
    await callback.message.edit_text(
        f"🎁 Бонус для: <b>{player['nickname']}</b>\n\nОбери тип:",
        parse_mode="HTML",
        reply_markup=bonus_types_keyboard(bonuses)
    )
    await state.set_state(GiveBonusState.choose_bonus_type)
    await callback.answer()

@router.callback_query(GiveBonusState.choose_bonus_type, F.data.startswith("bon_"))
async def bonus_type_chosen(callback: CallbackQuery, state: FSMContext, bot: Bot):
    parts = callback.data.split("_")
    bonus_id = int(parts[1])
    amount = int(parts[2])
    bonus = await get_bonus_type(bonus_id)
    if not bonus:
        await callback.answer("Не знайдено", show_alert=True)
        return
    if amount == 0:
        amount = bonus["amount_min"]
    data = await state.get_data()
    try:
        await change_balance(data["player_id"], amount, "bonus",
                             f"Бонус: {bonus['name']}", callback.from_user.id)
        await callback.message.edit_text(
            f"✅ Бонус видано!\n{data['player_name']}: +{chips(amount)}\n{bonus['name']}"
        )
        await _notify_player(bot, data["player_id"],
            f"🎁 <b>Тобі бонус!</b>\n<b>{bonus['name']}</b>\n+{chips(amount)}")
    except Exception as e:
        await callback.message.edit_text(f"❌ {e}")
    await state.clear()
    await callback.answer()


# ── Ставка від імені гравця ──────────────────────────────────

@router.message(F.text == "🎲 Ставка гравця")
async def admin_bet_start(message: Message, state: FSMContext):
    await message.answer(
        "🎲 <b>Ставка від імені гравця</b>\n\nОбери тип ставки:",
        parse_mode="HTML",
        reply_markup=admin_bet_type_keyboard()
    )
    await state.set_state(AdminBetState.choose_type)

@router.callback_query(AdminBetState.choose_type, F.data.startswith("adm_bet_"))
async def admin_bet_type_chosen(callback: CallbackQuery, state: FSMContext):
    raw = callback.data.replace("adm_bet_", "")
    type_map = {"redness":"redness","against":"against","side":"side","night":"night_death"}
    real_type = type_map.get(raw, raw)
    await state.update_data(bet_type=real_type)
    await callback.message.edit_text(
        "Номер гравця, який РОБИТЬ ставку (1–15):",
        reply_markup=player_number_keyboard("adm_creator")
    )
    await state.set_state(AdminBetState.enter_creator_no)
    await callback.answer()

@router.callback_query(AdminBetState.enter_creator_no, F.data.startswith("adm_creator_"))
async def admin_bet_creator_chosen(callback: CallbackQuery, state: FSMContext):
    number = int(callback.data.split("_")[-1])
    await state.update_data(creator_number=number)
    data = await state.get_data()
    bet_type = data["bet_type"]
    if bet_type == "side":
        await callback.message.edit_text(
            f"Ставочник — гравець #{number}\n\nОбери колір сторони:",
            reply_markup=color_keyboard("adm_color")
        )
        # залишаємось у тому ж стані — обробляємо нижче
    elif bet_type == "against":
        await callback.message.edit_text(
            f"Ставочник — гравець #{number}\n\nНомер ЦІЛІ (1–15):",
            reply_markup=player_number_keyboard("adm_target")
        )
        await state.set_state(AdminBetState.enter_target_no)
    else:
        max_a = 1 if bet_type == "night_death" else 5
        await callback.message.edit_text(
            f"Ставочник — гравець #{number}\n\nОбери суму (1–{max_a}):",
            reply_markup=amount_keyboard("adm_amount", max_a)
        )
        await state.set_state(AdminBetState.enter_amount)
    await callback.answer()

@router.callback_query(AdminBetState.enter_creator_no, F.data.startswith("adm_color_"))
async def admin_bet_color(callback: CallbackQuery, state: FSMContext):
    color = callback.data.split("_")[-1]
    coeff = 3.0 if color == "grey" else 2.0
    await state.update_data(color=color, coefficient=coeff)
    await callback.message.edit_text(
        f"Сторона: {COLOR_UA.get(color,color)} (×{coeff})\n\nОбери суму (1–5):",
        reply_markup=amount_keyboard("adm_amount", 5)
    )
    await state.set_state(AdminBetState.enter_amount)
    await callback.answer()

@router.callback_query(AdminBetState.enter_target_no, F.data.startswith("adm_target_"))
async def admin_bet_target_chosen(callback: CallbackQuery, state: FSMContext):
    number = int(callback.data.split("_")[-1])
    await state.update_data(target_number=number)
    await callback.message.edit_text(
        f"Ціль — гравець #{number}\n\nОбери суму (1–5):",
        reply_markup=amount_keyboard("adm_amount", 5)
    )
    await state.set_state(AdminBetState.enter_amount)
    await callback.answer()

@router.callback_query(AdminBetState.enter_amount, F.data.startswith("adm_amount_"))
async def admin_bet_amount_chosen(callback: CallbackQuery, state: FSMContext):
    amount = int(callback.data.split("_")[-1])
    data = await state.get_data()
    all_players = await get_all_players_sorted()
    idx = data["creator_number"] - 1
    if idx >= len(all_players):
        await callback.answer(f"Гравця #{data['creator_number']} не знайдено.", show_alert=True)
        await state.clear()
        return
    creator = all_players[idx]
    wallet = await get_wallet(creator["id"])
    avail = (wallet["balance"] - wallet["frozen_balance"]) if wallet else 0
    if avail < amount:
        await callback.answer(
            f"У {creator['nickname']} лише {avail} шепот, потрібно {amount}.",
            show_alert=True
        )
        await state.clear()
        return
    try:
        await freeze_chips(creator["id"], amount)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        await state.clear()
        return
    bet_type = data["bet_type"]
    coeff = data.get("coefficient", 3.0 if bet_type == "night_death" else 2.0)
    bet_id = await create_bet(
        creator_id=creator["id"],
        bet_type=bet_type,
        amount=amount,
        target_number=data.get("target_number"),
        side_color=data.get("color"),
        coefficient=coeff,
        created_by_admin=1,
    )
    type_ua = BET_TYPE_UA.get(bet_type, bet_type)
    tgt_txt = f" → ціль #{data['target_number']}" if data.get("target_number") else ""
    await callback.message.edit_text(
        f"✅ <b>Ставку #{bet_id} створено!</b>\n\n"
        f"Гравець: {creator['nickname']} (#{data['creator_number']})\n"
        f"Тип: {type_ua}{tgt_txt}\n"
        f"Сума: {chips(amount)}  Коефіцієнт: ×{coeff}\n"
        f"Статус: очікує підтвердження",
        parse_mode="HTML"
    )
    await state.clear()
    await callback.answer()


# ── Синхронізація ────────────────────────────────────────────

@router.message(F.text == "🔄 Оновити статистику")
async def sync_stats(message: Message):
    await message.answer("⏳ Завантажую з Google Sheets...")
    count, err = await sync_players_from_sheets()
    if err:
        await message.answer(f"❌ {err}")
    else:
        await message.answer(f"✅ Оновлено {count} гравців.")


# ── Прив'язати гравця ────────────────────────────────────────

@router.message(F.text == "🔗 Прив'язати гравця")
async def link_start(message: Message, state: FSMContext):
    await message.answer("🔗 Введи Telegram ID користувача (дізнатись у @userinfobot):")
    await state.set_state(LinkPlayerState.enter_telegram_id)

@router.message(LinkPlayerState.enter_telegram_id)
async def link_tg_id(message: Message, state: FSMContext):
    try:
        tg_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введи числовий ID:")
        return
    user = await get_user_by_telegram_id(tg_id)
    if not user:
        await message.answer(f"❌ Користувач {tg_id} не знайдений. Він має написати /start")
        return
    await state.update_data(tg_id=tg_id, user_db_id=user["id"], user_name=user["full_name"])
    await message.answer(
        f"Знайдено: <b>{user['full_name']}</b>\n\nВведи player_id з таблиці:",
        parse_mode="HTML"
    )
    await state.set_state(LinkPlayerState.enter_player_id)

@router.message(LinkPlayerState.enter_player_id)
async def link_do(message: Message, state: FSMContext, bot: Bot):
    pid = message.text.strip()
    player = await get_player_by_player_id(pid)
    if not player:
        await message.answer(f"❌ Гравець «{pid}» не знайдений.")
        return
    data = await state.get_data()
    await link_player_to_user(player["id"], data["user_db_id"])
    await message.answer(
        f"✅ {data['user_name']} → {player['nickname']}",
        reply_markup=main_menu_admin()
    )
    try:
        await bot.send_message(data["tg_id"],
            f"✅ <b>Тебе прив'язано до профілю {player['nickname']}!</b>\nНатисни /start",
            parse_mode="HTML")
    except Exception:
        pass
    await state.clear()


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()
