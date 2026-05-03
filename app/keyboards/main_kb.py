# app/keyboards/main_kb.py
from typing import List
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder


def main_menu_player() -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.row(KeyboardButton(text="👤 Мій профіль"),    KeyboardButton(text="🎰 Мої фішки"))
    b.row(KeyboardButton(text="🏆 Рейтинг"),         KeyboardButton(text="📋 Історія операцій"))
    b.row(KeyboardButton(text="🎲 Ставки"),           KeyboardButton(text="🛒 Витрати"))
    b.row(KeyboardButton(text="📖 Щоденник Ребеки Найт"), KeyboardButton(text="❓ Допомога"))
    b.row(KeyboardButton(text="♻️ ПереСтарт"))
    return b.as_markup(resize_keyboard=True)


def main_menu_admin() -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.row(KeyboardButton(text="➕ Видати фішки"),      KeyboardButton(text="➖ Списати фішки"))
    b.row(KeyboardButton(text="🎁 Видати бонус"),      KeyboardButton(text="📊 Активні ставки"))
    b.row(KeyboardButton(text="🎲 Ставка гравця"),     KeyboardButton(text="🔄 Оновити статистику"))
    b.row(KeyboardButton(text="🔗 Прив'язати гравця"), KeyboardButton(text="📜 Список гравців"))
    b.row(KeyboardButton(text="📖 Синх. щоденник"),    KeyboardButton(text="♻️ ПереСтарт"))
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
    b.row(InlineKeyboardButton(text="🔍 Пошук за іменем", callback_data=f"search_{action}"))
    return b.as_markup()


def search_results_keyboard(players: List[dict], action: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in players:
        b.row(InlineKeyboardButton(
            text=p["nickname"],
            callback_data=f"{action}_{p['id']}_p0"
        ))
    b.row(InlineKeyboardButton(text="◀️ До списку", callback_data=f"page_{action}_0"))
    return b.as_markup()


# ── Бонуси ───────────────────────────────────────────────────

def bonus_types_keyboard(bonuses: List[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for bn in bonuses:
        if bn["amount_min"] == bn["amount_max"]:
            b.row(InlineKeyboardButton(
                text=f"{bn['name']}  (+{bn['amount_min']} шепот)",
                callback_data=f"bon_{bn['id']}_0"
            ))
        else:
            b.row(
                InlineKeyboardButton(
                    text=f"{bn['name']}  +{bn['amount_min']}",
                    callback_data=f"bon_{bn['id']}_{bn['amount_min']}"
                ),
                InlineKeyboardButton(
                    text=f"+{bn['amount_max']} шепот",
                    callback_data=f"bon_{bn['id']}_{bn['amount_max']}"
                ),
            )
    return b.as_markup()


# ── Ставки ───────────────────────────────────────────────────

def bets_menu_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔴 На свою Червоність",         callback_data="bet_redness"))
    b.row(InlineKeyboardButton(text="⚔️ Проти гравця",                callback_data="bet_against"))
    b.row(InlineKeyboardButton(text="🎯 На перемогу сторони",         callback_data="bet_side"))
    b.row(InlineKeyboardButton(text="💀 Смерть вночі (×3, 1 шепот)", callback_data="bet_night_death"))
    return b.as_markup()


def admin_bet_type_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔴 На Червоність",       callback_data="adm_bet_redness"))
    b.row(InlineKeyboardButton(text="⚔️ Проти гравця",         callback_data="adm_bet_against"))
    b.row(InlineKeyboardButton(text="🎯 На перемогу сторони",  callback_data="adm_bet_side"))
    b.row(InlineKeyboardButton(text="💀 Смерть вночі (×3)",    callback_data="adm_bet_night"))
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
    b    = InlineKeyboardBuilder()
    btns = [
        InlineKeyboardButton(text=str(i), callback_data=f"{action}_{i}")
        for i in range(1, min(max_amount, 5) + 1)
    ]
    b.row(*btns)
    return b.as_markup()


def admin_amount_keyboard(action: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(*[InlineKeyboardButton(text=str(i), callback_data=f"{action}_{i}") for i in range(1,  6)])
    b.row(*[InlineKeyboardButton(text=str(i), callback_data=f"{action}_{i}") for i in range(6, 11)])
    return b.as_markup()


def active_bets_keyboard(bets: List[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    from app.utils.formatters import BET_TYPE_UA, BET_STATUS_UA
    for bet in bets:
        tname  = BET_TYPE_UA.get(bet["bet_type"], bet["bet_type"])
        status = BET_STATUS_UA.get(bet["status"], bet["status"])
        admin  = " [адмін]" if bet.get("created_by_admin") else ""
        label  = f"#{bet['id']} {bet['creator_nickname']}{admin} | {tname} | {bet['amount']} шепот | {status}"
        b.row(InlineKeyboardButton(text=label, callback_data=f"bet_manage_{bet['id']}"))
    return b.as_markup()


def bet_manage_keyboard(bet_id: int, status: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if status == "pending_admin":
        b.row(
            InlineKeyboardButton(text="Підтвердити", callback_data=f"bet_approve_{bet_id}"),
            InlineKeyboardButton(text="Скасувати",   callback_data=f"bet_cancel_{bet_id}"),
        )
    elif status in ("open", "duel"):
        b.row(
            InlineKeyboardButton(text="Переміг ставочник", callback_data=f"bet_win_creator_{bet_id}"),
            InlineKeyboardButton(text="Переміг опонент",   callback_data=f"bet_win_opponent_{bet_id}"),
        )
        b.row(InlineKeyboardButton(text="Скасувати", callback_data=f"bet_cancel_{bet_id}"))
    b.row(InlineKeyboardButton(text="◀ Назад", callback_data="back_active_bets"))
    return b.as_markup()


def redness_opponents_keyboard(bets: List[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for bet in bets:
        b.row(InlineKeyboardButton(
            text=f"{bet['creator_nickname']} поставив {bet['amount']} шепот — відповісти рівно",
            callback_data=f"against_redness_{bet['id']}"
        ))
    return b.as_markup()


# ── Витрати ──────────────────────────────────────────────────
# Витрати з фіксованою ціною — показуємо кнопку підтвердження
# Витрати де треба вибрати кількість — показуємо кнопки 1-5

def spending_menu_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔄 Зміна ходу обговорень — 1 шепот",   callback_data="spend_change_order"))
    b.row(InlineKeyboardButton(text="⚰️ Увімкнути похоронку — 1 шепот",     callback_data="spend_funeral"))
    b.row(InlineKeyboardButton(text="🔍 Дізнатися ролі гравців — 2 шепоти", callback_data="spend_know_roles"))
    b.row(InlineKeyboardButton(text="💺 Вибір місця за столом — 2 шепоти",  callback_data="spend_choose_seat"))
    b.row(InlineKeyboardButton(text="🔀 Пересдача карт столу — 3 шепоти",   callback_data="spend_redeal"))
    b.row(InlineKeyboardButton(text="💰 Хабар ведучому (-ФОЛ) — 3 шепоти", callback_data="spend_bribe"))
    b.row(InlineKeyboardButton(text="🙈 Змусити осліпнути — 3 шепоти",      callback_data="spend_blind"))
    b.row(InlineKeyboardButton(text="🎭 Купити роль — 4 шепоти",             callback_data="spend_buy_role"))
    b.row(InlineKeyboardButton(text="🤫 Змусити мовчати — 4 шепоти",        callback_data="spend_silence"))
    b.row(InlineKeyboardButton(text="🛡️ Імунітет на ніч — 7 шепот",         callback_data="spend_immunity"))
    b.row(InlineKeyboardButton(text="🏷️ Знижка 50% — 8 шепот",              callback_data="spend_discount_50"))
    b.row(InlineKeyboardButton(text="🆓 Знижка 100% — 14 шепот",            callback_data="spend_discount_100"))
    b.row(InlineKeyboardButton(text="🃏 Стати персонажем карти — 20 шепот", callback_data="spend_become_char"))
    return b.as_markup()


def spend_confirm_keyboard(spend_cb: str, amount: int) -> InlineKeyboardMarkup:
    """Кнопка підтвердження для фіксованих витрат."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=f"✅ Підтвердити ({amount} шепот)",
            callback_data=f"spend_confirm_{spend_cb}"
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
            text=f"#{s['id']} {s['player_nickname']} | {name}{tgt}{comm} | {s['amount']} шепот",
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
    for d in dates:
        b.row(InlineKeyboardButton(text=f"📅 {d}", callback_data=f"diary_date_{d}"))
    return b.as_markup()


def diary_games_keyboard(entries: List[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for e in entries:
        b.row(InlineKeyboardButton(
            text=f"Гра #{e['game_number']} — {e['title']}",
            callback_data=f"diary_entry_{e['id']}"
        ))
    b.row(InlineKeyboardButton(text="◀️ До дат", callback_data="diary_back"))
    return b.as_markup()


# ── Пагінація операцій ───────────────────────────────────────

def history_nav_keyboard(player_db_id: int, page: int, total: int,
                          per_page: int = 5) -> InlineKeyboardMarkup:
    b           = InlineKeyboardBuilder()
    total_pages = max(1, (total - 1) // per_page + 1)
    nav         = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            text="◀️", callback_data=f"hist_{player_db_id}_{page-1}"
        ))
    nav.append(InlineKeyboardButton(
        text=f"{page+1}/{total_pages}", callback_data="noop"
    ))
    if (page + 1) * per_page < total:
        nav.append(InlineKeyboardButton(
            text="▶️", callback_data=f"hist_{player_db_id}_{page+1}"
        ))
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
