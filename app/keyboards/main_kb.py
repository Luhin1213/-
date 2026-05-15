# app/keyboards/main_kb.py
from typing import List
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from app.utils.i18n import t


def main_menu_player(lang: str = "UA") -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.row(KeyboardButton(text=t("btn_profile",   lang)), KeyboardButton(text=t("btn_rating",    lang)))
    b.row(KeyboardButton(text=t("btn_bets",      lang)), KeyboardButton(text=t("btn_spendings", lang)))
    b.row(KeyboardButton(text=t("btn_diary",     lang)), KeyboardButton(text=t("btn_help",      lang)))
    b.row(KeyboardButton(text=t("btn_restart",   lang)))
    return b.as_markup(resize_keyboard=True)


def main_menu_admin(lang: str = "UA") -> ReplyKeyboardMarkup:
    whispers = "🎰 Шепоти"  if lang == "UA" else "🎰 Шёпоты"
    bets     = "🎲 Ставки"
    tables   = "📊 Таблиці" if lang == "UA" else "📊 Таблицы"
    citizens = "👥 Жителі"  if lang == "UA" else "👥 Жители"
    gather   = "🎮 Збір"    if lang == "UA" else "🎮 Сбор"

    b = ReplyKeyboardBuilder()
    b.row(KeyboardButton(text=whispers),  KeyboardButton(text=bets))
    b.row(KeyboardButton(text=tables),    KeyboardButton(text=citizens))
    b.row(KeyboardButton(text=gather),    KeyboardButton(text="📊 Активні ставки"))
    b.row(KeyboardButton(text="♻️ ПереСтарт"))
    return b.as_markup(resize_keyboard=True)


# ── Список гравців ───────────────────────────────────────────

def players_page_keyboard(players: List[dict], page: int = 0,
                           action: str = "view",
                           per_page: int = 7) -> InlineKeyboardMarkup:
    b     = InlineKeyboardBuilder()
    start = page * per_page
    chunk = players[start:start + per_page]
    for p in chunk:
        b.row(InlineKeyboardButton(
            text=p["nickname"],
            callback_data=f"{action}_{p['id']}_p{page}"
        ))
    nav         = []
    total_pages = max(1, (len(players) - 1) // per_page + 1)
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"page_{action}_{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
    if start + per_page < len(players):
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"page_{action}_{page+1}"))
    if nav:
        b.row(*nav)
    b.row(InlineKeyboardButton(text="🔍 Пошук / Поиск", callback_data=f"search_{action}"))
    return b.as_markup()


def search_results_keyboard(players: List[dict], action: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in players:
        b.row(InlineKeyboardButton(
            text=p["nickname"], callback_data=f"{action}_{p['id']}_p0"
        ))
    b.row(InlineKeyboardButton(text="◀️ Назад", callback_data=f"page_{action}_0"))
    return b.as_markup()


# ── Бонуси ───────────────────────────────────────────────────

def bonus_types_keyboard(bonuses: List[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for bn in bonuses:
        if bn["amount_min"] == bn["amount_max"]:
            b.row(InlineKeyboardButton(
                text=f"{bn['name']}  (+{bn['amount_min']} 🎰)",
                callback_data=f"bon_{bn['id']}_0"
            ))
        else:
            b.row(
                InlineKeyboardButton(
                    text=f"{bn['name']}  +{bn['amount_min']}",
                    callback_data=f"bon_{bn['id']}_{bn['amount_min']}"
                ),
                InlineKeyboardButton(
                    text=f"+{bn['amount_max']} 🎰",
                    callback_data=f"bon_{bn['id']}_{bn['amount_max']}"
                ),
            )
    return b.as_markup()


# ── Шепоти (адмін-меню) ──────────────────────────────────────

def whispers_admin_keyboard(lang: str = "UA") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="➕ Видати фішки",          callback_data="whisp_add"))
    b.row(InlineKeyboardButton(text="✏️ Ввести кількість вручну", callback_data="whisp_add_manual"))
    b.row(InlineKeyboardButton(text="➖ Списати фішки",         callback_data="whisp_sub"))
    b.row(InlineKeyboardButton(text="🎁 Видати бонус",          callback_data="whisp_bonus"))
    b.row(InlineKeyboardButton(text="💸 Видати всі шепоти",     callback_data="whisp_payout_all"))
    b.row(InlineKeyboardButton(text="📋 Історія операцій",      callback_data="whisp_history"))
    return b.as_markup()


# ── Ставки ───────────────────────────────────────────────────

def bets_menu_keyboard(lang: str = "UA") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔴 На свою Червоність",         callback_data="bet_redness"))
    respond_txt = "🔄 Ставка у відповідь" if lang == "UA" else "🔄 Ставка в ответ"
    b.row(InlineKeyboardButton(text=respond_txt,                      callback_data="bet_respond"))
    b.row(InlineKeyboardButton(text="⚔️ Ставка на Гравця",            callback_data="bet_against"))
    b.row(InlineKeyboardButton(text="🎯 На перемогу сторони",         callback_data="bet_side"))
    b.row(InlineKeyboardButton(text="💀 Смерть вночі (×3, 1 шепот)", callback_data="bet_night_death"))
    return b.as_markup()


def admin_bets_keyboard(lang: str = "UA") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📊 Активні ставки",    callback_data="admin_active_bets"))
    b.row(InlineKeyboardButton(text="🎲 Ставка від гравця", callback_data="admin_player_bet"))
    return b.as_markup()


def color_keyboard(action: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="🔴 Червоний", callback_data=f"{action}_red"),
        InlineKeyboardButton(text="⚫ Чорний",   callback_data=f"{action}_black"),
        InlineKeyboardButton(text="🔘 Сірий",    callback_data=f"{action}_grey"),
    )
    return b.as_markup()


def player_number_keyboard(action: str, max_n: int = 15) -> InlineKeyboardMarkup:
    b   = InlineKeyboardBuilder()
    row = []
    for n in range(1, max_n + 1):
        row.append(InlineKeyboardButton(text=str(n), callback_data=f"{action}_{n}"))
        if len(row) == 5:
            b.row(*row)
            row = []
    if row:
        b.row(*row)
    return b.as_markup()


def amount_keyboard(action: str, max_amount: int = 5) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(*[InlineKeyboardButton(text=str(i), callback_data=f"{action}_{i}")
            for i in range(1, min(max_amount, 5) + 1)])
    return b.as_markup()


def admin_amount_keyboard(action: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(*[InlineKeyboardButton(text=str(i), callback_data=f"{action}_{i}") for i in range(1,  6)])
    b.row(*[InlineKeyboardButton(text=str(i), callback_data=f"{action}_{i}") for i in range(6, 11)])
    return b.as_markup()


def active_bets_keyboard(bets: List[dict], has_hold: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    from app.utils.formatters import BET_TYPE_UA, BET_STATUS_UA, COLOR_UA
    for bet in bets:
        tname  = BET_TYPE_UA.get(bet["bet_type"], bet["bet_type"])
        status = BET_STATUS_UA.get(bet["status"], bet["status"])
        admin  = " [Мер]" if bet.get("created_by_admin") else ""
        target = ""
        if bet.get("target_number"):
            color  = COLOR_UA.get(bet.get("side_color",""), "")
            target = f" №{bet['target_number']} {color}"
        label = f"{status} #{bet['id']} {bet['creator_nickname']}{admin} | {tname}{target} | {bet['amount']} 🎰"
        b.row(InlineKeyboardButton(text=label, callback_data=f"bet_manage_{bet['id']}"))
    if has_hold:
        b.row(InlineKeyboardButton(
            text="💸 Видати всі шепоти гравцям",
            callback_data="bet_payout_all"
        ))
    return b.as_markup()


def bet_manage_keyboard(bet_id: int, status: str, bet_type: str = "") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if status == "pending_admin":
        b.row(
            InlineKeyboardButton(text="✅ Підтвердити", callback_data=f"bet_approve_{bet_id}"),
            InlineKeyboardButton(text="❌ Скасувати",   callback_data=f"bet_cancel_{bet_id}"),
        )
        # Для ставки на Червоність — можна одразу призначити опонента
        if bet_type == "redness":
            b.row(InlineKeyboardButton(
                text="👤 Призначити Опонента",
                callback_data=f"bet_set_opponent_{bet_id}"
            ))
    elif status in ("open", "duel"):
        b.row(
            InlineKeyboardButton(text="🏆 Переміг ставочник",  callback_data=f"bet_win_creator_{bet_id}"),
            InlineKeyboardButton(text="🏆 Переміг опонент",    callback_data=f"bet_win_opponent_{bet_id}"),
        )
        b.row(InlineKeyboardButton(text="❌ Скасувати", callback_data=f"bet_cancel_{bet_id}"))
        if bet_type == "redness" and status == "open":
            b.row(InlineKeyboardButton(
                text="👤 Призначити Опонента",
                callback_data=f"bet_set_opponent_{bet_id}"
            ))
    b.row(InlineKeyboardButton(text="◀ Назад", callback_data="back_active_bets"))
    return b.as_markup()


def redness_opponents_keyboard(bets: List[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for bet in bets:
        b.row(InlineKeyboardButton(
            text=f"{bet['creator_nickname']} поставив {bet['amount']} 🎰 — відповісти рівно",
            callback_data=f"against_redness_{bet['id']}"
        ))
    return b.as_markup()


# ── Витрати ──────────────────────────────────────────────────

def spending_menu_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    # Відсортовано за кількістю шепотів
    b.row(InlineKeyboardButton(text="🔄 Зміна ходу — 1 🎰",              callback_data="spend_change_order"))
    b.row(InlineKeyboardButton(text="💺 Вибір місця за столом — 2 🎰",    callback_data="spend_choose_seat"))
    b.row(InlineKeyboardButton(text="💰 Хабар ведучому — 2 🎰",           callback_data="spend_bribe"))
    b.row(InlineKeyboardButton(text="🔀 Пересдача карт — 3 🎰",           callback_data="spend_redeal"))
    b.row(InlineKeyboardButton(text="🎭 Купити роль — 4 🎰",              callback_data="spend_buy_role"))
    b.row(InlineKeyboardButton(text="🛡️ Хочу Імунітет — 7 🎰",            callback_data="spend_immunity"))
    b.row(InlineKeyboardButton(text="🍹 Випивки мені! — 8 🎰",            callback_data="spend_drink"))
    b.row(InlineKeyboardButton(text="🏷️ Знижка 50% — 10 🎰",              callback_data="spend_discount_50"))
    b.row(InlineKeyboardButton(text="🆓 Знижка 100% — 18 🎰",             callback_data="spend_discount_100"))
    b.row(InlineKeyboardButton(text="🃏 Стати Персонажем Карти — 20 🎰",  callback_data="spend_become_char"))
    b.row(InlineKeyboardButton(text="💀 Мертві →",                         callback_data="spend_dead_menu"))
    return b.as_markup()


def dead_spending_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="⚰️ Похоронка наступному мертвому — 1 🎰",  callback_data="spend_funeral"))
    b.row(InlineKeyboardButton(text="🔍 Дізнатися Ролі Гравців — 2 🎰",        callback_data="spend_know_roles"))
    b.row(InlineKeyboardButton(text="🙈 Осліпити Гравця (1 коло) — 3 🎰",      callback_data="spend_blind"))
    b.row(InlineKeyboardButton(text="🤫 Стулити Пельку (1 коло) — 4 🎰",         callback_data="spend_silence"))
    b.row(InlineKeyboardButton(text="◀️ Назад",                                 callback_data="spend_back_main"))
    return b.as_markup()


def spend_confirm_keyboard(spend_type: str, amount: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=f"✅ Підтвердити ({amount} 🎰)",
            callback_data=f"spend_confirm_{spend_type}"
        ),
        InlineKeyboardButton(text="❌ Скасувати", callback_data="spend_cancel_back"),
    )
    return b.as_markup()


def pending_spendings_keyboard(spendings: List[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    from app.utils.formatters import SPEND_TYPE_UA
    for s in spendings:
        name = SPEND_TYPE_UA.get(s["spend_type"], s["spend_type"])
        tgt  = f" №{s['target_number']}" if s.get("target_number") else ""
        comm = f" [{s['comment'][:15]}]" if s.get("comment") else ""
        b.row(InlineKeyboardButton(
            text=f"#{s['id']} {s['player_nickname']} | {name}{tgt}{comm} | {s['amount']} 🎰",
            callback_data=f"spend_resolve_{s['id']}"
        ))
    return b.as_markup()


def spend_resolve_keyboard(spending_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="Підтвердити", callback_data=f"spend_ok_{spending_id}"),
        InlineKeyboardButton(text="Скасувати",   callback_data=f"spend_no_{spending_id}"),
    )
    return b.as_markup()


# ── Щоденник ─────────────────────────────────────────────────

def diary_dates_keyboard(dates: List[str]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for i, d in enumerate(dates):
        b.row(InlineKeyboardButton(text=f"📅 {d}", callback_data=f"ddate_{i}"))
    return b.as_markup()


def diary_games_keyboard(entries: List[dict], lang: str = "UA") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    game_word = "Гра" if lang == "UA" else "Партия"
    for e in entries:
        b.row(InlineKeyboardButton(
            text=f"{game_word} #{e['game_number']} — {e['title']}",
            callback_data=f"dentry_{e['id']}"
        ))
    back_txt = "◀️ До дат" if lang == "UA" else "◀️ К датам"
    b.row(InlineKeyboardButton(text=back_txt, callback_data="dback"))
    return b.as_markup()


# ── Пагінація операцій ───────────────────────────────────────

def history_nav_keyboard(player_db_id: int, page: int, total: int,
                          per_page: int = 5) -> InlineKeyboardMarkup:
    b           = InlineKeyboardBuilder()
    total_pages = max(1, (total - 1) // per_page + 1)
    nav         = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"hist_{player_db_id}_{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
    if (page + 1) * per_page < total:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"hist_{player_db_id}_{page+1}"))
    b.row(*nav)
    return b.as_markup()


# ── Рейтинг ──────────────────────────────────────────────────

def rating_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="📍 Моє місце",   callback_data="rat_my"),
        InlineKeyboardButton(text="🏆 Топ-10",       callback_data="rat_top10"),
        InlineKeyboardButton(text="📊 Весь рейтинг", callback_data="rat_all"),
    )
    return b.as_markup()


# ── Збори ────────────────────────────────────────────────────

def gathering_signup_keyboard(gathering_id: int, lang: str = "UA") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ Записатись",  callback_data=f"gather_join_{gathering_id}"),
        InlineKeyboardButton(text="❌ Відписатись", callback_data=f"gather_leave_{gathering_id}"),
    )
    return b.as_markup()


def active_gatherings_keyboard(gatherings: List[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for g in gatherings:
        label = f"📅 {g['game_date']} {g.get('game_time','')} | 👥 {g['signed_count']}/{g['max_players']}"
        b.row(InlineKeyboardButton(text=label, callback_data=f"gather_view_{g['id']}"))
    return b.as_markup()


def admin_gathering_keyboard(gathering_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="👥 Список записаних",  callback_data=f"gather_list_{gathering_id}"))
    b.row(InlineKeyboardButton(text="❌ Скасувати збір",    callback_data=f"gather_cancel_{gathering_id}"))
    b.row(InlineKeyboardButton(text="◀️ Назад",             callback_data="gather_back"))
    return b.as_markup()


def admin_bet_type_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔴 На Червоність",      callback_data="adm_bet_redness"))
    b.row(InlineKeyboardButton(text="⚔️ Проти гравця",        callback_data="adm_bet_against"))
    b.row(InlineKeyboardButton(text="🎯 На перемогу сторони", callback_data="adm_bet_side"))
    b.row(InlineKeyboardButton(text="💀 Смерть вночі (×3)",   callback_data="adm_bet_night"))
    return b.as_markup()
