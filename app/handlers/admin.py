# app/handlers/admin.py
import logging
import aiosqlite
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.filters import Filter
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from app.database.queries import (
    is_admin, get_all_players_sorted, get_player_by_id,
    change_balance, get_active_bonus_types, get_bonus_type,
    get_user_by_telegram_id, link_player_to_user,
    get_player_by_player_id, get_wallet, search_players,
    create_bet, freeze_chips, get_user_language,
)
from app.keyboards.main_kb import (
    main_menu_admin, players_page_keyboard, bonus_types_keyboard,
    admin_amount_keyboard, search_results_keyboard,
    admin_bet_type_keyboard, player_number_keyboard,
    color_keyboard, amount_keyboard, whispers_admin_keyboard,
    admin_bets_keyboard,
)
from app.services.sheets_service import sync_players_from_sheets
from app.services.logs_service import sync_logs_players, sync_game_details
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


# ── 🎰 ШЕПОТИ (об'єднано: видати/списати/бонус) ─────────────

@router.message(F.text.in_(["🎰 Шепоти", "🎰 Шёпоты"]))
async def whispers_menu(message: Message):
    lang = await get_user_language(message.from_user.id)
    title = "Управління Шепотами" if lang == "UA" else "Управление Шёпотами"
    await message.answer(
        f"🎰 <b>{title}</b>",
        parse_mode="HTML",
        reply_markup=whispers_admin_keyboard(lang)
    )


@router.callback_query(F.data == "whisp_add")
async def whisp_add_start(callback: CallbackQuery, state: FSMContext):
    players = await get_all_players_sorted()
    if not players:
        await callback.answer("Немає гравців", show_alert=True)
        return
    await callback.message.edit_text(
        "➕ <b>Видача фішок</b>\n\nОбери гравця:",
        parse_mode="HTML",
        reply_markup=players_page_keyboard(players, 0, "select_add")
    )
    await state.set_state(AddChipsState.choose_player)
    await callback.answer()


@router.callback_query(F.data == "whisp_sub")
async def whisp_sub_start(callback: CallbackQuery, state: FSMContext):
    players = await get_all_players_sorted()
    if not players:
        await callback.answer("Немає гравців", show_alert=True)
        return
    await callback.message.edit_text(
        "➖ <b>Списання фішок</b>\n\nОбери гравця:",
        parse_mode="HTML",
        reply_markup=players_page_keyboard(players, 0, "select_sub")
    )
    await state.set_state(SubtractChipsState.choose_player)
    await callback.answer()


@router.callback_query(F.data == "whisp_bonus")
async def whisp_bonus_start(callback: CallbackQuery, state: FSMContext):
    players = await get_all_players_sorted()
    if not players:
        await callback.answer("Немає гравців", show_alert=True)
        return
    await callback.message.edit_text(
        "🎁 <b>Видача бонусу</b>\n\nОбери гравця:",
        parse_mode="HTML",
        reply_markup=players_page_keyboard(players, 0, "select_bonus")
    )
    await state.set_state(GiveBonusState.choose_player)
    await callback.answer()


# ── Видати фішки ─────────────────────────────────────────────

@router.callback_query(AddChipsState.choose_player, F.data.startswith("page_select_add_"))
async def add_chips_page(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[-1])
    players = await get_all_players_sorted()
    await callback.message.edit_reply_markup(reply_markup=players_page_keyboard(players, page, "select_add"))
    await callback.answer()

@router.callback_query(AddChipsState.choose_player, F.data == "search_select_add")
async def add_chips_search(callback: CallbackQuery, state: FSMContext):
    await state.update_data(search_action="select_add")
    await callback.message.edit_text("🔍 Введи ім'я гравця:")
    await state.set_state(SearchPlayerState.enter_query)
    await callback.answer()

@router.callback_query(AddChipsState.choose_player, F.data.startswith("select_add_"))
async def add_chips_player(callback: CallbackQuery, state: FSMContext):
    pid = int(callback.data.split("_")[2])
    p   = await get_player_by_id(pid)
    if not p:
        await callback.answer("Не знайдено", show_alert=True)
        return
    await state.update_data(player_id=pid, player_name=p["nickname"])
    await callback.message.edit_text(
        f"➕ Видача для: <b>{p['nickname']}</b>\n\nОбери кількість (1–10):",
        parse_mode="HTML", reply_markup=admin_amount_keyboard("add_amount")
    )
    await state.set_state(AddChipsState.enter_amount)
    await callback.answer()

@router.callback_query(AddChipsState.enter_amount, F.data.startswith("add_amount_"))
async def add_chips_amount(callback: CallbackQuery, state: FSMContext):
    amount = int(callback.data.split("_")[-1])
    await state.update_data(amount=amount)
    data = await state.get_data()
    await callback.message.edit_text(f"➕ {data['player_name']}: +{chips(amount)}\n\nКоментар (або —):")
    await state.set_state(AddChipsState.enter_comment)
    await callback.answer()

@router.message(AddChipsState.enter_comment)
async def add_chips_comment(message: Message, state: FSMContext, bot: Bot):
    comment = message.text.strip()
    if comment == "—":
        comment = "Нарахування Банкіром Міста Грехів"
    data = await state.get_data()
    try:
        await change_balance(data["player_id"], data["amount"], "add", comment, message.from_user.id)
        await message.answer(f"✅ +{chips(data['amount'])} → {data['player_name']}")
        await _notify_player(bot, data["player_id"],
            f"🎰 <b>Тобі нараховано!</b>\n+{chips(data['amount'])}\nПричина: {comment}")
    except Exception as e:
        await message.answer(f"❌ {e}")
    await state.clear()


# ── Списати фішки ────────────────────────────────────────────

@router.callback_query(SubtractChipsState.choose_player, F.data.startswith("page_select_sub_"))
async def sub_chips_page(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[-1])
    players = await get_all_players_sorted()
    await callback.message.edit_reply_markup(reply_markup=players_page_keyboard(players, page, "select_sub"))
    await callback.answer()

@router.callback_query(SubtractChipsState.choose_player, F.data == "search_select_sub")
async def sub_chips_search(callback: CallbackQuery, state: FSMContext):
    await state.update_data(search_action="select_sub")
    await callback.message.edit_text("🔍 Введи ім'я гравця:")
    await state.set_state(SearchPlayerState.enter_query)
    await callback.answer()

@router.callback_query(SubtractChipsState.choose_player, F.data.startswith("select_sub_"))
async def sub_chips_player(callback: CallbackQuery, state: FSMContext):
    pid = int(callback.data.split("_")[2])
    p   = await get_player_by_id(pid)
    if not p:
        await callback.answer("Не знайдено", show_alert=True)
        return
    await state.update_data(player_id=pid, player_name=p["nickname"])
    await callback.message.edit_text(
        f"➖ Списання у: <b>{p['nickname']}</b>\n\nОбери кількість (1–10):",
        parse_mode="HTML", reply_markup=admin_amount_keyboard("sub_amount")
    )
    await state.set_state(SubtractChipsState.enter_amount)
    await callback.answer()

@router.callback_query(SubtractChipsState.enter_amount, F.data.startswith("sub_amount_"))
async def sub_chips_amount(callback: CallbackQuery, state: FSMContext):
    amount = int(callback.data.split("_")[-1])
    await state.update_data(amount=amount)
    data = await state.get_data()
    await callback.message.edit_text(f"➖ {data['player_name']}: -{chips(amount)}\n\nКоментар (або —):")
    await state.set_state(SubtractChipsState.enter_comment)
    await callback.answer()

@router.message(SubtractChipsState.enter_comment)
async def sub_chips_comment(message: Message, state: FSMContext, bot: Bot):
    comment = message.text.strip()
    if comment == "—":
        comment = "Списання Банкіром Міста Грехів"
    data = await state.get_data()
    try:
        await change_balance(data["player_id"], -data["amount"], "subtract", comment, message.from_user.id)
        await message.answer(f"✅ -{chips(data['amount'])} у {data['player_name']}")
        await _notify_player(bot, data["player_id"],
            f"➖ <b>Адмін списав шепоти</b>\n-{chips(data['amount'])}\nПричина: {comment}")
    except ValueError as e:
        await message.answer(f"❌ {e}")
    await state.clear()


# ── Бонус ────────────────────────────────────────────────────

@router.callback_query(GiveBonusState.choose_player, F.data.startswith("page_select_bonus_"))
async def bonus_page(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[-1])
    players = await get_all_players_sorted()
    await callback.message.edit_reply_markup(reply_markup=players_page_keyboard(players, page, "select_bonus"))
    await callback.answer()

@router.callback_query(GiveBonusState.choose_player, F.data == "search_select_bonus")
async def bonus_search(callback: CallbackQuery, state: FSMContext):
    await state.update_data(search_action="select_bonus")
    await callback.message.edit_text("🔍 Введи ім'я гравця:")
    await state.set_state(SearchPlayerState.enter_query)
    await callback.answer()

@router.callback_query(GiveBonusState.choose_player, F.data.startswith("select_bonus_"))
async def bonus_player(callback: CallbackQuery, state: FSMContext):
    pid     = int(callback.data.split("_")[2])
    p       = await get_player_by_id(pid)
    bonuses = await get_active_bonus_types()
    if not p:
        await callback.answer("Не знайдено", show_alert=True)
        return
    await state.update_data(player_id=pid, player_name=p["nickname"])
    await callback.message.edit_text(
        f"🎁 Бонус для: <b>{p['nickname']}</b>\n\nОбери тип:",
        parse_mode="HTML", reply_markup=bonus_types_keyboard(bonuses)
    )
    await state.set_state(GiveBonusState.choose_bonus_type)
    await callback.answer()

@router.callback_query(GiveBonusState.choose_bonus_type, F.data.startswith("bon_"))
async def bonus_type(callback: CallbackQuery, state: FSMContext, bot: Bot):
    parts    = callback.data.split("_")
    bonus_id = int(parts[1])
    amount   = int(parts[2])
    bonus    = await get_bonus_type(bonus_id)
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


# ── Пошук (загальний) ────────────────────────────────────────

@router.message(SearchPlayerState.enter_query)
async def search_player(message: Message, state: FSMContext):
    query   = message.text.strip()
    data    = await state.get_data()
    action  = data.get("search_action", "view")
    results = await search_players(query)
    if not results:
        await message.answer(f"❌ «{query}» не знайдено.")
        # НЕ очищаємо стан — повертаємо до попереднього стану
        return
    # НЕ очищаємо стан після пошуку — щоб вибір гравця з результатів спрацював
    # Повертаємо стан до choose_player відповідного флоу
    state_map = {
        "select_add":   AddChipsState.choose_player,
        "select_sub":   SubtractChipsState.choose_player,
        "select_bonus": GiveBonusState.choose_player,
    }
    if action in state_map:
        await state.set_state(state_map[action])
    await message.answer(
        f"🔍 Знайдено {len(results)}:",
        reply_markup=search_results_keyboard(results, action)
    )


# ── 🎲 СТАВКИ (об'єднано) ────────────────────────────────────

@router.message(F.text == "🎲 Ставки")
async def admin_bets_menu(message: Message):
    lang = await get_user_language(message.from_user.id)
    await message.answer(
        "🎲 <b>Ставки</b>",
        parse_mode="HTML",
        reply_markup=admin_bets_keyboard(lang)
    )

@router.callback_query(F.data == "admin_active_bets")
async def admin_active_bets(callback: CallbackQuery):
    from app.database.queries import get_active_bets, get_pending_spendings
    from app.keyboards.main_kb import active_bets_keyboard, pending_spendings_keyboard
    bets     = await get_active_bets()
    spendings = await get_pending_spendings()
    if not bets and not spendings:
        await callback.message.edit_text("📊 Немає активних ставок і запитів.")
        await callback.answer()
        return
    if spendings:
        await callback.message.answer(
            f"🛒 <b>Очікуючі витрати ({len(spendings)}):</b>",
            parse_mode="HTML",
            reply_markup=pending_spendings_keyboard(spendings)
        )
    if bets:
        await callback.message.answer(
            f"🎲 <b>Активні ставки ({len(bets)}):</b>",
            parse_mode="HTML",
            reply_markup=active_bets_keyboard(bets)
        )
    await callback.answer()

@router.callback_query(F.data == "admin_player_bet")
async def admin_player_bet_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🎲 <b>Ставка від імені гравця</b>\n\nОбери тип:",
        parse_mode="HTML",
        reply_markup=admin_bet_type_keyboard()
    )
    await state.set_state(AdminBetState.choose_type)
    await callback.answer()

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
async def admin_bet_creator(callback: CallbackQuery, state: FSMContext):
    number   = int(callback.data.split("_")[-1])
    await state.update_data(creator_number=number)
    data     = await state.get_data()
    bet_type = data["bet_type"]
    if bet_type == "side":
        await callback.message.edit_text(
            f"Ставочник #{number}\n\nОбери колір сторони:",
            reply_markup=color_keyboard("adm_color")
        )
    elif bet_type == "against":
        await callback.message.edit_text(
            f"Ставочник #{number}\n\nНомер ЦІЛІ (1–15):",
            reply_markup=player_number_keyboard("adm_target")
        )
        await state.set_state(AdminBetState.enter_target_no)
    else:
        max_a = 1 if bet_type == "night_death" else 5
        await callback.message.edit_text(
            f"Ставочник #{number}\n\nОбери суму (1–{max_a}):",
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
        f"{COLOR_UA.get(color,color)} (×{coeff})\n\nОбери суму (1–5):",
        reply_markup=amount_keyboard("adm_amount", 5)
    )
    await state.set_state(AdminBetState.enter_amount)
    await callback.answer()

@router.callback_query(AdminBetState.enter_target_no, F.data.startswith("adm_target_"))
async def admin_bet_target(callback: CallbackQuery, state: FSMContext):
    number = int(callback.data.split("_")[-1])
    await state.update_data(target_number=number)
    await callback.message.edit_text(
        f"Ціль #{number}\n\nОбери суму (1–5):",
        reply_markup=amount_keyboard("adm_amount", 5)
    )
    await state.set_state(AdminBetState.enter_amount)
    await callback.answer()

@router.callback_query(AdminBetState.enter_amount, F.data.startswith("adm_amount_"))
async def admin_bet_amount(callback: CallbackQuery, state: FSMContext):
    amount      = int(callback.data.split("_")[-1])
    data        = await state.get_data()
    all_players = await get_all_players_sorted()
    idx         = data["creator_number"] - 1
    if idx >= len(all_players):
        await callback.answer(f"Гравця #{data['creator_number']} не знайдено.", show_alert=True)
        await state.clear()
        return
    creator = all_players[idx]
    wallet  = await get_wallet(creator["id"])
    avail   = (wallet["balance"] - wallet["frozen_balance"]) if wallet else 0
    if avail < amount:
        await callback.answer(
            f"У {creator['nickname']} лише {avail} шепот.", show_alert=True
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
    coeff    = data.get("coefficient", 3.0 if bet_type == "night_death" else 2.0)
    bet_id   = await create_bet(
        creator_id=creator["id"], bet_type=bet_type, amount=amount,
        target_number=data.get("target_number"), side_color=data.get("color"),
        coefficient=coeff, created_by_admin=1,
    )
    type_ua = BET_TYPE_UA.get(bet_type, bet_type)
    tgt_txt = f" → #{data['target_number']}" if data.get("target_number") else ""
    await callback.message.edit_text(
        f"✅ Ставку #{bet_id} створено!\n{creator['nickname']} #{data['creator_number']}\n"
        f"{type_ua}{tgt_txt}\n{chips(amount)} ×{coeff}",
        parse_mode="HTML"
    )
    await state.clear()
    await callback.answer()


# ── 📊 ТАБЛИЦІ (об'єднано) ───────────────────────────────────

@router.message(F.text.in_(["📊 Таблиці", "📊 Таблицы"]))
async def tables_menu(message: Message):
    lang = await get_user_language(message.from_user.id)
    b    = InlineKeyboardBuilder()
    if lang == "UA":
        b.row(InlineKeyboardButton(text="🔄 Синхр. партії (GameDetails)", callback_data="tbl_sync_games"))
        b.row(InlineKeyboardButton(text="📖 Синхр. ручний щоденник", callback_data="tbl_sync_diary"))
        b.row(InlineKeyboardButton(text="✨ Генерувати щоденник ШІ", callback_data="ai_generate_menu"))
    else:
        b.row(InlineKeyboardButton(text="🔄 Синхр. партии (GameDetails)", callback_data="tbl_sync_games"))
        b.row(InlineKeyboardButton(text="📖 Синхр. ручной дневник",   callback_data="tbl_sync_diary"))
        b.row(InlineKeyboardButton(text="✨ Сгенерировать дневник ИИ",callback_data="ai_generate_menu"))
    title = "Таблиці та Щоденник" if lang == "UA" else "Таблицы и Дневник"
    await message.answer(f"📊 <b>{title}</b>", parse_mode="HTML", reply_markup=b.as_markup())

@router.callback_query(F.data == "tbl_sync_stats")
async def tbl_sync_stats(callback: CallbackQuery):
    await callback.message.edit_text("⏳ Завантажую статистику...")
    count, err = await sync_players_from_sheets()
    await callback.message.edit_text(f"❌ {err}" if err else f"✅ Оновлено {count} гравців.")
    await callback.answer()

@router.callback_query(F.data == "tbl_sync_players")
async def tbl_sync_players(callback: CallbackQuery):
    await callback.message.edit_text("⏳ Синхронізую бали гравців...")
    count, err = await sync_logs_players()
    await callback.message.edit_text(f"❌ {err}" if err else f"✅ Оновлено {count} гравців.")
    await callback.answer()

@router.callback_query(F.data == "tbl_sync_games")
async def tbl_sync_games(callback: CallbackQuery):
    await callback.message.edit_text("⏳ Зчитую логи партій...")
    count, err = await sync_game_details()
    await callback.message.edit_text(f"❌ {err}" if err else f"✅ Партій збережено: {count}.")
    await callback.answer()

@router.callback_query(F.data == "tbl_sync_diary")
async def tbl_sync_diary(callback: CallbackQuery):
    from app.services.sheets_service import sync_diary_from_sheets
    await callback.message.edit_text("⏳ Завантажую щоденник...")
    count, err = await sync_diary_from_sheets()
    await callback.message.edit_text(f"❌ {err}" if err else f"✅ Записів щоденника: {count}.")
    await callback.answer()


# ── 👥 ЖИТЕЛІ (об'єднано) ────────────────────────────────────

@router.message(F.text.in_(["👥 Жителі", "👥 Жители"]))
async def citizens_menu(message: Message):
    lang = await get_user_language(message.from_user.id)
    b    = InlineKeyboardBuilder()
    if lang == "UA":
        b.row(InlineKeyboardButton(text="📜 Список гравців",           callback_data="cit_list"))
        b.row(InlineKeyboardButton(text="🔗 Прив'язати гравця",        callback_data="cit_link"))
        b.row(InlineKeyboardButton(text="🔄 Оновити статистику",       callback_data="tbl_sync_stats"))
        b.row(InlineKeyboardButton(text="🔄 Синхр. логи гравців",      callback_data="tbl_sync_players"))
    else:
        b.row(InlineKeyboardButton(text="📜 Список игроков",           callback_data="cit_list"))
        b.row(InlineKeyboardButton(text="🔗 Привязать игрока",         callback_data="cit_link"))
        b.row(InlineKeyboardButton(text="🔄 Обновить статистику",      callback_data="tbl_sync_stats"))
        b.row(InlineKeyboardButton(text="🔄 Синхр. логи игроков",      callback_data="tbl_sync_players"))
    title = "Жителі Міста" if lang == "UA" else "Жители Города"
    await message.answer(f"👥 <b>{title}</b>", parse_mode="HTML", reply_markup=b.as_markup())

@router.callback_query(F.data == "cit_list")
async def cit_list(callback: CallbackQuery):
    players = await get_all_players_sorted()
    if not players:
        await callback.answer("Немає гравців.", show_alert=True)
        return
    await callback.message.edit_text(
        f"📜 <b>Список ({len(players)}):</b>",
        parse_mode="HTML",
        reply_markup=players_page_keyboard(players, 0, "view")
    )
    await callback.answer()

@router.callback_query(F.data.startswith("page_view_"))
async def cit_list_page(callback: CallbackQuery):
    page = int(callback.data.split("_")[-1])
    players = await get_all_players_sorted()
    await callback.message.edit_reply_markup(
        reply_markup=players_page_keyboard(players, page, "view")
    )
    await callback.answer()

@router.callback_query(F.data == "search_view")
async def cit_search(callback: CallbackQuery, state: FSMContext):
    await state.update_data(search_action="view")
    await callback.message.edit_text("🔍 Введи ім'я гравця:")
    await state.set_state(SearchPlayerState.enter_query)
    await callback.answer()

@router.callback_query(F.data.startswith("view_"))
async def cit_view_player(callback: CallbackQuery):
    pid    = int(callback.data.split("_")[1])
    player = await get_player_by_id(pid)
    if not player:
        await callback.answer("Не знайдено", show_alert=True)
        return
    wallet = await get_wallet(pid)
    lang   = await get_user_language(callback.from_user.id)
    from app.utils.formatters import format_profile
    text = format_profile(player, wallet, None, lang)
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "cit_link")
async def cit_link_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🔗 Введи Telegram ID користувача\n(дізнатись у @userinfobot):"
    )
    await state.set_state(LinkPlayerState.enter_telegram_id)
    await callback.answer()

@router.message(LinkPlayerState.enter_telegram_id)
async def link_tg_id(message: Message, state: FSMContext):
    try:
        tg_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введи числовий ID:")
        return
    user = await get_user_by_telegram_id(tg_id)
    if not user:
        await message.answer(f"❌ {tg_id} не знайдений. Він має написати /start")
        return
    await state.update_data(tg_id=tg_id, user_db_id=user["id"], user_name=user["full_name"])
    await message.answer(
        f"Знайдено: <b>{user['full_name']}</b>\n\nВведи player_id з таблиці:",
        parse_mode="HTML"
    )
    await state.set_state(LinkPlayerState.enter_player_id)

@router.message(LinkPlayerState.enter_player_id)
async def link_do(message: Message, state: FSMContext, bot: Bot):
    pid    = message.text.strip()
    player = await get_player_by_player_id(pid)
    if not player:
        await message.answer(f"❌ Гравець «{pid}» не знайдений.")
        return
    data = await state.get_data()
    await link_player_to_user(player["id"], data["user_db_id"])
    await message.answer(f"✅ {data['user_name']} → {player['nickname']}")
    try:
        await bot.send_message(data["tg_id"],
            f"✅ <b>Тебе прив'язано до профілю {player['nickname']}!</b>\nНатисни /start",
            parse_mode="HTML")
    except Exception:
        pass
    await state.clear()


# ── Активні ставки (пряма кнопка в меню) ─────────────────────

@router.message(F.text == "📊 Активні ставки")
async def active_bets_direct(message: Message):
    from app.database.queries import get_active_bets, get_pending_spendings
    from app.keyboards.main_kb import active_bets_keyboard, pending_spendings_keyboard
    bets     = await get_active_bets()
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
            parse_mode="HTML", reply_markup=active_bets_keyboard(bets)
        )


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()


# ── Перегляд / запис операцій з Google Sheets ───────────────

@router.callback_query(F.data == "whisp_history")
async def whisp_history(callback: CallbackQuery):
    """Показує останні 20 операцій з SQLite."""
    from app.database.queries import get_all_players_sorted, get_transactions, count_transactions
    lang = await get_user_language(callback.from_user.id)
    title = "📋 Останні операції" if lang == "UA" else "📋 Последние операции"

    # Беремо останні 15 транзакцій по всіх гравцях
    import aiosqlite as _aio
    from app.config import DATABASE_PATH as _DB
    async with _aio.connect(_DB) as db:
        db.row_factory = _aio.Row
        cur = await db.execute("""
            SELECT t.*, p.nickname FROM transactions t
            JOIN players p ON p.id = t.player_id
            ORDER BY t.created_at DESC LIMIT 15
        """)
        rows = [dict(r) for r in await cur.fetchall()]

    if not rows:
        await callback.answer("Операцій ще немає.", show_alert=True)
        return

    icons = {"add":"➕","subtract":"➖","bonus":"🎁","bet_win":"✅","bet_lose":"❌","spend":"🛒","drink":"🍹"}
    lines = [f"<b>{title}:</b>\n"]
    for r in rows:
        icon = icons.get(r["type"], "🔄")
        sign = "+" if r["type"] in ("add","bonus","bet_win") else "-"
        date = r.get("created_at","")[:16]
        comm = f" — {r.get('comment','')[:30]}" if r.get("comment") else ""
        lines.append(f"{icon} {r['nickname']} {sign}{r['amount']} 🎰{comm} <i>{date}</i>")

    from aiogram.utils.keyboard import InlineKeyboardBuilder as _IKB
    from aiogram.types import InlineKeyboardButton as _IKBtn
    b = _IKB()
    b.row(_IKBtn(text="◀️ Назад", callback_data="whisp_back"))
    await callback.message.edit_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=b.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data == "whisp_back")
async def whisp_back(callback: CallbackQuery):
    from app.keyboards.main_kb import whispers_admin_keyboard
    lang = await get_user_language(callback.from_user.id)
    title = "Управління Шепотами" if lang == "UA" else "Управление Шёпотами"
    await callback.message.edit_text(
        f"🎰 <b>{title}</b>",
        parse_mode="HTML",
        reply_markup=whispers_admin_keyboard(lang)
    )
    await callback.answer()


# ── Ручне введення кількості шепотів ────────────────────────

from aiogram.fsm.state import StatesGroup as _SG2, State as _S2

class ManualAmountState(_SG2):
    choose_player = _S2()
    enter_amount  = _S2()
    enter_comment = _S2()


@router.callback_query(F.data == "whisp_add_manual")
async def whisp_add_manual_start(callback: CallbackQuery, state: FSMContext):
    players = await get_all_players_sorted()
    if not players:
        await callback.answer("Немає гравців", show_alert=True)
        return
    await callback.message.edit_text(
        "✏️ <b>Ввести кількість вручну</b>\n\nОбери гравця:",
        parse_mode="HTML",
        reply_markup=players_page_keyboard(players, 0, "manual_p")
    )
    await state.set_state(ManualAmountState.choose_player)
    await callback.answer()


@router.callback_query(ManualAmountState.choose_player, F.data.startswith("manual_p_"))
async def manual_player_chosen(callback: CallbackQuery, state: FSMContext):
    pid = int(callback.data.split("_")[2])
    p   = await get_player_by_id(pid)
    if not p:
        await callback.answer("Не знайдено", show_alert=True)
        return
    await state.update_data(player_id=pid, player_name=p["nickname"])
    await callback.message.edit_text(
        f"✏️ Гравець: <b>{p['nickname']}</b>\n\nВведи кількість шепотів (число):",
        parse_mode="HTML"
    )
    await state.set_state(ManualAmountState.enter_amount)
    await callback.answer()


@router.message(ManualAmountState.enter_amount)
async def manual_amount_entered(message: Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
        if amount <= 0 or amount > 999:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи ціле число від 1 до 999:")
        return
    await state.update_data(amount=amount)
    data = await state.get_data()
    await message.answer(
        f"✏️ {data['player_name']}: +{chips(amount)}\n\nКоментар (або —):"
    )
    await state.set_state(ManualAmountState.enter_comment)


@router.message(ManualAmountState.enter_comment)
async def manual_comment_entered(message: Message, state: FSMContext, bot: Bot):
    comment = message.text.strip()
    if comment == "—":
        comment = "Ручне нарахування від Банкіра"
    data = await state.get_data()
    from app.database.queries import add_pending_payout
    await add_pending_payout(data["player_id"], data["amount"], comment, message.from_user.id)
    from aiogram.utils.keyboard import InlineKeyboardBuilder as IKB
    from aiogram.types import InlineKeyboardButton as IKBtn
    b = IKB()
    b.row(IKBtn(text="💸 Видати всі шепоти гравцям", callback_data="whisp_payout_all"))
    await message.answer(
        f"✅ +{chips(data['amount'])} → <b>{data['player_name']}</b> в черзі виплат\n<i>{comment}</i>",
        parse_mode="HTML", reply_markup=b.as_markup()
    )
    await state.clear()


# ── Видати всі шепоти з черги ────────────────────────────────

@router.callback_query(F.data == "whisp_payout_all")
async def whisp_payout_all(callback: CallbackQuery, bot: Bot):
    from app.database.queries import get_all_pending_payouts, clear_pending_payouts
    payouts = await get_all_pending_payouts()
    if not payouts:
        await callback.answer("Черга виплат порожня.", show_alert=True)
        return

    sent_count = 0
    total_sent = 0
    for p in payouts:
        try:
            await change_balance(p["player_id"], p["amount"], "add",
                                  p.get("comment","Виплата"), callback.from_user.id)
            await _notify_player(bot, p["player_id"],
                f"🎰 <b>Шепоти нараховано!</b>\n+{chips(p['amount'])}\n{p.get('comment','')}")
            sent_count += 1
            total_sent += p["amount"]
        except Exception as e:
            logger.error(f"Помилка виплати {p['nickname']}: {e}")

    await clear_pending_payouts()
    await callback.message.edit_text(
        f"✅ <b>Шепоти видано!</b>\n\n"
        f"Гравців: {sent_count}\n"
        f"Всього: {chips(total_sent)}",
        parse_mode="HTML"
    )
    await callback.answer()
