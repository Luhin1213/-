# app/utils/formatters.py
import random
from typing import Optional, List
from app.config import CHIP_EMOJI
from app.utils.i18n import get_status_by_games

# Сезон 4 — загальна статистика
SEASON_4_GAMES = 21
SEASON_4_RED   = 8
SEASON_4_BLACK = 10
SEASON_4_GREY  = 3

# Перемоги гравців з Excel (Перемоги за сторони)
PLAYER_WINS = {
    "Лилит":      {"red": 5, "black": 3, "grey": 0, "total": 8,  "games": 17},
    "Коллинз":    {"red": 2, "black": 1, "grey": 0, "total": 3,  "games": 6},
    "Кэрол":      {"red": 3, "black": 2, "grey": 0, "total": 5,  "games": 17},
    "Sambuca":    {"red": 2, "black": 3, "grey": 0, "total": 5,  "games": 14},
    "Донна":      {"red": 5, "black": 3, "grey": 0, "total": 8,  "games": 17},
    "Микс":       {"red": 6, "black": 2, "grey": 0, "total": 8,  "games": 17},
    "Cherry Pie": {"red": 3, "black": 0, "grey": 0, "total": 3,  "games": 3},
    "Одис":       {"red": 2, "black": 0, "grey": 0, "total": 2,  "games": 4},
    "Иноземец":   {"red": 3, "black": 0, "grey": 0, "total": 3,  "games": 6},
    "Subaru":     {"red": 3, "black": 1, "grey": 0, "total": 4,  "games": 6},
    "Senorita":   {"red": 2, "black": 1, "grey": 0, "total": 3,  "games": 8},
    "ШадЭ":       {"red": 2, "black": 0, "grey": 0, "total": 2,  "games": 3},
    "Луна":       {"red": 3, "black": 2, "grey": 1, "total": 6,  "games": 14},
    "Фокс":       {"red": 0, "black": 1, "grey": 0, "total": 1,  "games": 3},
    "Айро":       {"red": 1, "black": 0, "grey": 0, "total": 1,  "games": 4},
    "Кимельман":  {"red": 2, "black": 4, "grey": 0, "total": 6,  "games": 14},
}

def chips(n: int) -> str:
    return f"{n} {CHIP_EMOJI} шепот"


def _city_capture_phrase(red_wins: int, black_wins: int, lang: str) -> str:
    diff = red_wins - black_wins
    if lang == "UA":
        if abs(diff) <= 2:
            return "⚖️ Хистка рівновага"
        elif diff >= 6:
            return "⚖️ Закон повертає собі Місто Грехів"
        elif diff >= 3:
            return "🏙️ Місто Грехів починає дихати вільніше"
        elif diff <= -6:
            return "🌑 Мафія встановлює новий порядок..."
        else:
            return "🌑 Тіні беруть вулиці Міста Грехів під контроль"
    else:
        if abs(diff) <= 2:
            return "⚖️ Хрупкое равновесие"
        elif diff >= 6:
            return "⚖️ Закон возвращает себе Город Грехов"
        elif diff >= 3:
            return "🏙️ Город Грехов начинает дышать свободнее"
        elif diff <= -6:
            return "🌑 Мафия устанавливает новый порядок..."
        else:
            return "🌑 Тени берут улицы Города Грехов под контроль"


def format_profile(player: dict, wallet: Optional[dict],
                   txs: Optional[List[dict]], lang: str = "UA",
                   rank_pos: int = 0, game_stats: Optional[dict] = None) -> str:
    games  = player.get("games_played", 0)
    nick   = player.get("nickname", "")
    fols   = player.get("fols", 0)
    p_lose  = player.get("points_lose",    0)
    p_surv  = player.get("points_survive", 0)
    p_win   = player.get("points_win",     0)
    p_host  = player.get("points_host",    0)
    p_best  = player.get("points_best",    0)
    p_guess = player.get("points_guess",   0)
    p_total = player.get("points_total",   0)

    status = get_status_by_games(games, lang)

    # Місце в рейтингу — динамічно або з БД
    rank_display = f"#{rank_pos}" if rank_pos else f"#{player.get('rank_position', '—')}"

    # Виживаємість і перемоги — з логів (4 сезон) якщо є, інакше fallback
    if game_stats and game_stats.get("games", 0) > 0:
        gs        = game_stats
        games_log = gs["games"]
        surv_log  = gs["survived"]
        red_w     = gs["red_wins"]
        black_w   = gs["black_wins"]
        grey_w    = gs["grey_wins"]
        total_w   = gs["total_wins"]
        surv_pct  = f"{surv_log / games_log * 100:.0f}%"
        surv_detail = f"{surv_log} з {games_log}"
    else:
        # Fallback: Excel словник → потім дані з БД
        pw      = PLAYER_WINS.get(nick, {})
        red_w   = pw.get("red",   player.get("city_wins",  0))
        black_w = pw.get("black", player.get("mafia_wins", 0))
        grey_w  = pw.get("grey",  0)
        total_w = pw.get("total", player.get("wins", 0))
        surv_pct    = f"{p_surv / games * 100:.0f}%" if games > 0 else "—"
        surv_detail = f"{p_surv} з {games}"

    # Захоплення міста
    city_phrase = _city_capture_phrase(SEASON_4_RED, SEASON_4_BLACK, lang)

    # Шепоти
    whisper_block = ""
    if wallet:
        bal   = wallet["balance"]
        frz   = wallet["frozen_balance"]
        avail = bal - frz
        if lang == "UA":
            whisper_block = (
                f"\n\n{CHIP_EMOJI} <b>Шепоти:</b>\n"
                f"  Всього: <b>{bal}</b>  |  Доступно: <b>{avail}</b>  |  Заморожено: {frz}"
            )
        else:
            whisper_block = (
                f"\n\n{CHIP_EMOJI} <b>Шепоты:</b>\n"
                f"  Всего: <b>{bal}</b>  |  Доступно: <b>{avail}</b>  |  Заморожено: {frz}"
            )

    # Останні 3 операції
    ops_block = ""
    if txs:
        label = "Останні операції:" if lang == "UA" else "Последние операции:"
        lines = [f"\n\n📋 <b>{label}</b>"]
        for tx in txs[:3]:
            comm   = tx.get("comment", "")
            amount = tx.get("amount", 0)
            tp     = tx.get("type", "")
            if tp in ("add", "bonus"):
                sign = "+"
                icon = "🎁" if tp == "bonus" else "➕"
            elif tp == "bet_win":
                sign = "+"
                icon = "✅"
            else:
                sign = "-"
                icon = "❌" if tp == "bet_lose" else "🛒" if tp == "spend" else "➖"
            lines.append(f"  {icon} {sign}{chips(amount)} — {comm[:45]}")
        ops_block = "\n".join(lines)

    phrase = random.choice(RANDOM_PHRASES)

    return (
        f"👤 <b>{nick}</b>\n"
        f"⭐ Статус: <b>{status}</b>\n"
        f"📍 Місце в рейтингу: {rank_display}\n\n"
        f"🎮 <b>Статистика — 4 Сезон:</b>\n"
        f"  Ігри: <b>{games}</b>  |  Фоли: <b>{fols}</b>\n"
        f"  Виживаємість: <b>{surv_pct}</b> ({surv_detail})\n\n"
        f"📊 <b>Бали:</b>\n"
        f"  За програш: {p_lose}  |  За виживання: {p_surv}\n"
        f"  За виграш: {p_win}  |  Від ведучого: {p_host}\n"
        f"  Кращий гравець: <b>{p_best}</b>  |  За вгадування: {p_guess}\n"
        f"  <b>Загальні бали: {p_total}</b>\n\n"
        f"🏆 <b>Перемоги гравця:</b>\n"
        f"  🔴 Червоні: {red_w}  ⚫ Чорні: {black_w}  🔘 Сірі: {grey_w}\n"
        f"  Разом: <b>{total_w}</b>\n\n"
        f"🌆 <b>Захоплення Міста Гріхів:</b>\n"
        f"  🔴 {SEASON_4_RED}  ⚫ {SEASON_4_BLACK}  🔘 {SEASON_4_GREY}\n"
        f"  {city_phrase}"
        f"{whisper_block}"
        f"{ops_block}\n\n"
        f"<b>Нотатник:</b>\n<i>{phrase}</i>"
    )


def format_points(player: dict) -> str:
    # Блок балів прибрано за запитом
    return ""


def format_transactions_page(txs: List[dict], page: int, total: int,
                               per_page: int = 5) -> str:
    if not txs:
        return "📋 Операцій ще немає."
    icons = {
        "add":"➕","subtract":"➖","bonus":"🎁",
        "bet_win":"✅","bet_lose":"❌","spend":"🛒",
        "freeze":"🔒","unfreeze":"🔓",
    }
    names = {
        "add":"Нарахування","subtract":"Списання","bonus":"Бонус",
        "bet_win":"Виграш","bet_lose":"Програш","spend":"Витрата",
        "freeze":"Заморожено","unfreeze":"Розморожено",
    }
    total_pages = max(1, (total - 1) // per_page + 1)
    lines = [f"📋 <b>Операції</b>  (стор. {page+1}/{total_pages})\n"]
    for tx in txs:
        icon = icons.get(tx["type"], "🔄")
        name = names.get(tx["type"], tx["type"])
        sign = "+" if tx["type"] in ("add","bonus","bet_win","unfreeze") else "-"
        comm = f" — {tx['comment']}" if tx.get("comment") else ""
        date = tx.get("created_at","")[:16].replace("T"," ")
        lines.append(f"{icon} {name}: <b>{sign}{chips(tx['amount'])}</b>{comm}\n   <i>{date}</i>")
    return "\n\n".join(lines)


def format_rating(players: List[dict], label: str = "Топ-10") -> str:
    if not players:
        return "📊 Список гравців порожній."
    medals = {1:"🥇", 2:"🥈", 3:"🥉"}
    lines  = [f"🏆 <b>Рейтинг — {label}:</b>\n"]
    for i, p in enumerate(players, 1):
        m      = medals.get(i, f"{i}.")
        pts    = p.get("points_total", 0)
        games  = p.get("games_played", 0)
        lines.append(f"{m} <b>{p['nickname']}</b> — {pts} балів ({games} ігор)")
    return "\n".join(lines)


BET_TYPE_UA = {
    "redness":    "🔴 Ставка на Червоність",
    "against":    "🎰 Ставка на гравця",
    "side":       "🎯 На перемогу сторони",
    "night_death":"💀 Смерть вночі",
}
BET_STATUS_UA = {
    "pending_admin": "🟡 нова",
    "open":          "🟢 активна",
    "duel":          "🟢 дуель",
    "closed":        "🔴 закрита",
    "cancelled":     "⚫ скасована",
}
COLOR_UA = {"red":"🔴 Червоний","black":"⚫ Чорний","grey":"🔘 Сірий"}
SPEND_TYPE_UA = {
    "change_order": "🔄 Зміна ходу",
    "funeral":      "⚰️ Похоронка",
    "know_roles":   "🔍 Ролі гравців",
    "blind":        "🙈 Осліпнути (1 круг)",
    "choose_seat":  "💺 Вибір місця за столом",
    "redeal":       "🔀 Пересдача карт",
    "bribe":        "💰 Хабар ведучому",
    "silence":      "🤫 Стулити Пельку (1 коло)",
    "buy_role":     "🎭 Купити роль",
    "immunity":     "🛡️ Хочу Імунітет",
    "become_char":  "🃏 Стати Персонажем Карти",
    "discount_50":  "🏷️ Знижка 50%",
    "discount_100": "🆓 Знижка 100%",
    "drink":        "🍹 Випивки мені!",
}

# Фрази з файлу фразы.txt + старі фрази Міста
RANDOM_PHRASES = [
    "Интересно,действительно! Послушаю остальных...",
    "Так сложно говорить первым😂",
    "Играю с Миксом)",
    "Стоять... а как же меня лечить в игре?",
    "«Не, если хотите, можете меня слить, но тогда мирные проиграют»",
    "Пусть меня проверит детектив",
    "Я важный и нужный  игрок для города © Молли",
    "Главное не убивате меня! © Самурай",
    "Чтобы я не говорил, Микс всегда подозрительный © Микс",
    "Если Пан Ведущий ничего не напутал… © Микс",
    "Как тяжело говорить 13-м © Мольфар",
    "«Убейти (выгоните) меня...» © Триггер",
    "Этот город прогнил… © Триггер",
    "Спаси…. Господи меня © Микс",
    "«Я играю с Миксом» «Я не играю против Луны» © Мольфар",
    "Давай, рискни... © Триггер",
    "Бородатый мальчик) © Кимельман",
    "«Я жду ваши голоса». © Самурай",
    "«Щас будит мясоооо!!» © Пан Ведущий",
    "«Спасибо! Пошли нахуй» © Sambuca",
    "Такая горячая, что перестрахуюсь объяснением © Мольфар",
    "Самбука - Легенда © Триггер",
    "Живи долго, хотя-бы 3-4 ночи! © Señorita",
    "Я думал, ты показываешь, что ты замужем! © Микс",
    "Текилька ©",
    "Заходит слепой в HORIZON и говорит: «Всем привет кого не видел». © Кимельман",
    "Выживаю как могу © Микс",
    "С тебя льется чернота © GC",
    "Горизонт має 12 синонімів в українській мові: обрій, небозвід, небосхил... © Донна",
    "«Микс, воскреснешь?» © Пан Ведущий",
    "Это вообще- рванина © Психея",
    "Молли будет 100% © Молли",
    "Приятно когда в тебя верят 😁",
    "«Уважаю поле» © Луночка and Микс",
    "«Давай я перезаряжу» © Луна 🌓",
    "У картишек, нет братишек © Луна 🌒",
    "Мы с Сантой вась-вась. У трамвая рога и у оленей рога. © Молли",
    "Я - Олег Ляжко © Trigger",
    "Раз два три надо говорить © Кимельман",
    "Здесь могла быть Ваша Реклама, а тут фразочки",
    "Это моя женщина! Тигрица 🐅!! © Субару",
    "Миндальная и фисташковая связь)) © Кимельман",
    "Деревья – это вредители © Донна",
    "У меня папа Генерал © Дернис",
    "«Та не завербован я» © Все, 04.05.2025",
    "«Серега, ты голова, ты решай))» © Субару",
    "Запретное слово: «Оля». P.s. чтобы не получить фол.",
    "Может покормим ведущего? (спустя 3 часа) Ведущего мы так и не покормили © Кимельман",
    "А че ты не сказал что ты мирный ? © Субару",
    "Корова - пошла нахуй! © Самбука",
    "Слава Богу, что можно материться! © Нимфа",
    "Просыпаются сектанты, ведущий лезет под стол! © Пан Ведущий",
    "Ведущий: «Не буду фоллить за маты.» - Алькатрас: «Бл*ть»",
    "*Донна уходить після другої партії* Ведучий: Помянем",
    "Ну, а если не победим, то проиграем © Senorita",
    "- Луна, предсмертные 30 секунд - Да идите в жопу!! Спасибо!! © Луна",
    "Желаю вам, чтоб вас ГИРОСКУТЕР СБИЛ © Сеньорита",
    # Старі фрази Міста
    "Місто не спить. Але хтось із вас цієї ночі не прокинеться...",
    "Довіряй своїй інтуїції. Або не довіряй — все одно помреш.",
    "Мафія ніколи не спить. А ти?",
    "Кожна партія — нова брехня. Кожна брехня — новий шанс.",
    "Хтось за цим столом знає більше ніж говорить.",
    "Найнебезпечніший гравець той, кого ніхто не підозрює.",
    "В цьому місті кожна усмішка — маска. Кожне слово — зброя.",
    "Ніч опускається на місто. Хто не прокинеться вранці?",
    "Слова вбивають швидше за кулі. Обирай їх мудро.",
    "Страх видає більше ніж сто слів.",
]
