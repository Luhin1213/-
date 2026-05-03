# app/utils/formatters.py
import random
from typing import Optional, List
from app.config import CHIP_EMOJI


def chips(n: int) -> str:
    """1 шепот, 2 шепоти... але за умовою — завжди 'шепот'."""
    return f"{n} {CHIP_EMOJI} шепот"


def format_profile(player: dict) -> str:
    """Профіль БЕЗ шепотів — вони у вкладці 'Мої фішки'."""
    games  = player.get("games_played", 0)
    wins   = player.get("wins", 0)
    w_pct  = f"{wins/games*100:.1f}%" if games else "—"
    city_w = player.get("city_wins",  0)
    maf_w  = player.get("mafia_wins", 0)

    if city_w > maf_w:
        city_state = "🏙️ Місто тримає контроль"
    elif city_w == maf_w:
        city_state = "⚖️ Тендітна рівновага"
    else:
        city_state = "🌑 Місто занурюється в темряву"

    # ── Рандомні фрази в кінці профілю ──────────────────────
    # Додай сюди свої фрази — бот обере одну випадково
    RANDOM_PHRASES = [
        "— додай свою фразу 1 —",
        "— додай свою фразу 2 —",
        "— додай свою фразу 3 —",
        "— додай свою фразу 4 —",
        "— додай свою фразу 5 —",
    ]
    phrase = random.choice(RANDOM_PHRASES)

    return (
        f"👤 <b>{player['nickname']}</b>\n"
        f"🆔 ID: <code>{player['player_id']}</code>\n"
        f"⭐ Статус: {player.get('status','Новачок')}\n"
        f"📍 Місце в рейтингу: #{player.get('rank_position','—')}\n"
        f"📊 Рейтинг: {player.get('rating',0):.1f}\n\n"
        f"🎮 <b>Статистика:</b>\n"
        f"  Ігор: {games}  |  Перемог: {wins} ({w_pct})\n"
        f"  Вижив: {player.get('survived',0)}\n"
        f"  Перемоги міста: {city_w}  |  Мафії: {maf_w}\n\n"
        f"🌆 {city_state}\n\n"
        f"<i>{phrase}</i>"
    )


def format_wallet_short(wallet: Optional[dict], last_ops: List[dict]) -> str:
    if not wallet:
        return "💳 Гаманець не знайдено. Зверніться до адміністратора."
    bal   = wallet["balance"]
    frz   = wallet["frozen_balance"]
    avail = bal - frz
    lines = [
        f"{CHIP_EMOJI} <b>Твої Шепоти</b>\n",
        f"  Всього:    <b>{chips(bal)}</b>",
        f"  Доступно:  <b>{chips(avail)}</b>",
        f"  Заморожено: {frz} шепот\n",
        "<b>Останні 3 операції:</b>",
    ]
    if not last_ops:
        lines.append("  Операцій ще немає.")
    for t in last_ops[:3]:
        sign = "+" if t["type"] in ("add","bonus","bet_win") else "-"
        lines.append(f"  {sign}{chips(t['amount'])} — {t.get('comment','')[:40]}")
    return "\n".join(lines)


def format_transactions_page(txs: List[dict], page: int, total: int, per_page: int = 5) -> str:
    if not txs:
        return "📋 Операцій ще немає."

    icons = {
        "add":      "➕", "subtract": "➖", "bonus":    "🎁",
        "bet_win":  "✅", "bet_lose":  "❌", "spend":    "🛒",
        "freeze":   "🔒", "unfreeze":  "🔓",
    }
    names = {
        "add":      "Нарахування", "subtract": "Списання",  "bonus": "Бонус",
        "bet_win":  "Виграш",      "bet_lose":  "Програш",  "spend": "Витрата",
        "freeze":   "Заморожено",  "unfreeze":  "Розморожено",
    }
    total_pages = (total - 1) // per_page + 1
    lines = [f"📋 <b>Операції</b>  (стор. {page+1}/{total_pages})\n"]
    for t in txs:
        icon = icons.get(t["type"], "🔄")
        name = names.get(t["type"], t["type"])
        sign = "+" if t["type"] in ("add","bonus","bet_win","unfreeze") else "-"
        comm = f" — {t['comment']}" if t.get("comment") else ""
        date = t.get("created_at","")[:16].replace("T"," ")
        lines.append(f"{icon} {name}: <b>{sign}{chips(t['amount'])}</b>{comm}\n   <i>{date}</i>")
    return "\n\n".join(lines)


def format_rating(players: List[dict], label: str = "Топ-10") -> str:
    if not players:
        return "📊 Список гравців порожній. Потрібна синхронізація."
    medals = {1:"🥇", 2:"🥈", 3:"🥉"}
    lines  = [f"🏆 <b>Рейтинг — {label}:</b>\n"]
    for i, p in enumerate(players, 1):
        m = medals.get(i, f"{i}.")
        lines.append(
            f"{m} <b>{p['nickname']}</b> — "
            f"{p.get('rating',0):.1f} ({p.get('games_played',0)} ігор)"
        )
    return "\n".join(lines)


# ── Словники ──────────────────────────────────────────────────

BET_TYPE_UA = {
    "redness":    "Ставка на Червоність",
    "against":    "Ставка Проти гравця",
    "side":       "Ставка на перемогу сторони",
    "night_death":"Смерть вночі",
}
BET_STATUS_UA = {
    "pending_admin": "очікує підтвердження",
    "open":          "відкрита",
    "duel":          "дуель",
    "closed":        "закрита",
    "cancelled":     "скасована",
}
COLOR_UA = {
    "red":   "🔴 Червоний",
    "black": "⚫ Чорний",
    "grey":  "🔘 Сірий",
}
SPEND_TYPE_UA = {
    "change_order": "🔄 Зміна ходу обговорень",
    "funeral":      "⚰️ Увімкнути похоронку",
    "know_roles":   "🔍 Дізнатися ролі гравців",
    "blind":        "🙈 Змусити осліпнути",
    "choose_seat":  "💺 Вибір місця за столом",
    "redeal":       "🔀 Пересдача карт столу",
    "bribe":        "💰 Хабар ведучому (-ФОЛ)",
    "silence":      "🤫 Змусити мовчати",
    "buy_role":     "🎭 Купити роль",
    "immunity":     "🛡️ Імунітет на ніч",
    "become_char":  "🃏 Стати персонажем карти",
    "discount_50":  "🏷️ Знижка 50%",
    "discount_100": "🆓 Знижка 100%",
}


def format_points(player: dict) -> str:
    """Показує розбивку балів гравця з таблиці Логи."""
    total = player.get("points_total", 0)
    if total == 0:
        return ""
    return (
        f"\n\n🏅 <b>Бали (з таблиці Логи):</b>\n"
        f"  Виграш: {player.get('points_win', 0)}\n"
        f"  Виживання: {player.get('points_survive', 0)}\n"
        f"  Програш: {player.get('points_lose', 0)}\n"
        f"  Від ведучого: {player.get('points_host', 0)}\n"
        f"  Кращий гравець: {player.get('points_best', 0)}\n"
        f"  Угадав ролі: {player.get('points_guess', 0)}\n"
        f"  <b>Всього: {total}</b>"
    )
