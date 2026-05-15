# app/services/logs_service.py
#
# Робота з таблицею Логи (окрема Google таблиця):
#   - синхронізація Players → оновлення балів гравців у SQLite
#   - синхронізація GameDetails → збереження логів партій
#   - запис шепотів назад у Bankir-Bot таблицю

import os
import logging
from typing import Tuple, List, Optional

from app.config import (
    GOOGLE_CREDENTIALS_FILE,
    GOOGLE_SHEET_ID,
    LOGS_SHEET_ID,
    LOGS_PLAYERS_SHEET,
    LOGS_GAMES_SHEET,
    LOGS_TEXT_COLUMN,
)
from app.database.queries import (
    update_player_points,
    upsert_game_log,
    upsert_game_player_stat,
)

logger = logging.getLogger(__name__)


def _get_client(write: bool = False):
    import gspread
    from google.oauth2.service_account import Credentials
    creds_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), GOOGLE_CREDENTIALS_FILE
    )
    if not os.path.exists(creds_path):
        raise FileNotFoundError(f"credentials.json не знайдено: {creds_path}")
    scopes = (
        ["https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive"]
        if write else
        ["https://www.googleapis.com/auth/spreadsheets.readonly",
         "https://www.googleapis.com/auth/drive.readonly"]
    )
    from google.oauth2.service_account import Credentials
    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    return gspread.authorize(creds)


# ══════════════════════════════════════════════
# 1. Синхронізація Players → SQLite
# ══════════════════════════════════════════════

async def sync_logs_players() -> Tuple[int, str]:
    """
    Головна синхронізація: читає MAFIAGAME Players як основну таблицю.
    Структура: Ім'я | Нікнейм | Ігри | Фоли |
               Бали за програш | Бали за виживання | Бали за виграш |
               Бали від ведучого | Бали за кращо | Бали за вгадування |
               Загальні бали | TelegramID (остання колонка)

    - Якщо є TelegramID — прив'язує Telegram-акаунт до профілю
    - Якщо гравця немає в SQLite — створює автоматично
    - Оновлює всю статистику з таблиці
    """
    if not LOGS_SHEET_ID:
        return 0, "LOGS_SHEET_ID не задано у .env"
    try:
        client = _get_client()
        sheet  = client.open_by_key(LOGS_SHEET_ID).worksheet(LOGS_PLAYERS_SHEET)
        rows   = sheet.get_all_records()
        if not rows:
            return 0, f"Лист '{LOGS_PLAYERS_SHEET}' порожній."

        import aiosqlite
        from app.config import DATABASE_PATH
        from app.database.queries import (
            update_player_points, get_player_by_player_id,
            link_player_to_user, get_user_by_telegram_id,
        )

        count = 0
        for row in rows:
            r = {k.lower().strip(): v for k, v in row.items()}

            nickname = str(r.get("нікнейм", r.get("nickname", ""))).strip()
            if not nickname:
                continue

            full_name = str(r.get("ім'я", r.get("имя", nickname))).strip()

            def to_int(key_variants):
                for k in key_variants:
                    v = r.get(k, "")
                    try:
                        val = str(v).strip()
                        if val in ("", "-", "None"):
                            return 0
                        return int(float(val))
                    except (ValueError, TypeError):
                        pass
                return 0

            points_data = {
                "games":   to_int(["ігри", "ігор", "games"]),
                "fols":    to_int(["фоли", "фол", "fols"]),
                "lose":    to_int(["бали за програш", "points_lose"]),
                "survive": to_int(["бали за виживання", "points_survive"]),
                "win":     to_int(["бали за виграш", "points_win"]),
                "host":    to_int(["бали від ведучого", "points_host"]),
                "best":    to_int(["бали за кращо", "бали за кращого", "points_best"]),
                "guess":   to_int(["бали за угадав", "бали за вгадування", "points_guess"]),
                "total":   to_int(["загальні бали", "points_total"]),
            }

            # Переконуємось що гравець існує в SQLite
            async with aiosqlite.connect(DATABASE_PATH) as db:
                db.row_factory = aiosqlite.Row

                # Шукаємо по нікнейму
                cur = await db.execute(
                    "SELECT * FROM players WHERE nickname=? COLLATE NOCASE LIMIT 1",
                    (nickname,)
                )
                existing = await cur.fetchone()

                if not existing:
                    # Створюємо нового гравця з player_id = MAFIA_{nickname}
                    player_id = f"MAFIA_{nickname}"
                    await db.execute(
                        "INSERT OR IGNORE INTO players (player_id, nickname) VALUES (?,?)",
                        (player_id, nickname)
                    )
                    await db.commit()
                    cur2 = await db.execute(
                        "SELECT id FROM players WHERE player_id=?", (player_id,)
                    )
                    p_row = await cur2.fetchone()
                    if p_row:
                        await db.execute(
                            "INSERT OR IGNORE INTO wallets (player_id,balance,frozen_balance) VALUES (?,0,0)",
                            (p_row[0],)
                        )
                        await db.commit()
                    logger.info(f"Створено нового гравця: {nickname}")

            # Оновлюємо статистику
            await update_player_points(nickname, points_data)

            # Прив'язуємо TelegramID якщо є в таблиці
            tg_id_raw = str(r.get("telegramid", r.get("telegram_id", r.get("tg_id", "")))).strip()
            if tg_id_raw and tg_id_raw not in ("", "0", "None", "-"):
                try:
                    tg_id = int(float(tg_id_raw))
                    if tg_id > 0:
                        # Знаходимо user в SQLite по telegram_id
                        user = await get_user_by_telegram_id(tg_id)
                        if user:
                            # Прив'язуємо якщо ще не прив'язано
                            async with aiosqlite.connect(DATABASE_PATH) as db:
                                cur = await db.execute(
                                    "SELECT id FROM players WHERE nickname=? COLLATE NOCASE LIMIT 1",
                                    (nickname,)
                                )
                                p_row = await cur.fetchone()
                                if p_row:
                                    await db.execute(
                                        "UPDATE players SET linked_user_id=? WHERE id=? AND (linked_user_id IS NULL OR linked_user_id=0)",
                                        (user["id"], p_row[0])
                                    )
                                    await db.commit()
                except (ValueError, TypeError):
                    pass

            count += 1

        return count, ""
    except Exception as e:
        logger.error(f"Помилка синхронізації Players: {e}")
        return 0, f"Помилка: {e}"


# ══════════════════════════════════════════════
# 2. Синхронізація GameDetails → SQLite
# ══════════════════════════════════════════════

async def sync_game_details() -> Tuple[int, str]:
    """
    Читає лист GameDetails.
    Структура: Дата | № партії | Переможна фракція | Ім'я | Нікнейм |
               Роль | Фоли | [бали...] | Логи (текст)

    Групує рядки по (Дата + № партії) і зберігає як один лог.
    """
    if not LOGS_SHEET_ID:
        return 0, "LOGS_SHEET_ID не задано у .env"
    try:
        client = _get_client()
        sheet  = client.open_by_key(LOGS_SHEET_ID).worksheet(LOGS_GAMES_SHEET)

        # Читаємо сирі значення щоб знайти колонку з логом
        all_values = sheet.get_all_values()
        if not all_values or len(all_values) < 2:
            return 0, f"Лист '{LOGS_GAMES_SHEET}' порожній."

        headers = [h.lower().strip() for h in all_values[0]]

        # Знаходимо індекси потрібних колонок
        def col_idx(variants):
            for v in variants:
                if v in headers:
                    return headers.index(v)
            return None

        idx_date     = col_idx(["дата", "date"])
        idx_num      = col_idx(["№ партії", "№ партії", "# партії", "номер партії", "no"])
        idx_winner   = col_idx(["переможна фракція", "переможець", "winner"])
        idx_log      = col_idx([LOGS_TEXT_COLUMN.lower(), "логи", "log", "лог", "текст"])
        idx_nickname = col_idx(["нікнейм", "nickname"])
        idx_survive  = col_idx(["бали за виживання", "points_survive"])
        idx_win_pts  = col_idx(["бали за виграш", "points_win"])

        if idx_date is None or idx_num is None:
            return 0, (
                f"Не знайдено колонки 'Дата' або '№ партії' в листі '{LOGS_GAMES_SHEET}'.\n"
                f"Знайдені заголовки: {', '.join(all_values[0][:10])}"
            )

        def _normalize_faction(faction: str) -> str:
            f = faction.lower().strip()
            if any(x in f for x in ["місто", "misto", "city", "мирн", "червон", "red", "жовт"]):
                return "red"
            if any(x in f for x in ["маф", "mafia", "black", "чорн"]):
                return "black"
            if any(x in f for x in ["нейтрал", "neutral", "grey", "gray", "сір"]):
                return "grey"
            return faction

        def _safe_int(row, idx):
            if idx is None or idx >= len(row):
                return 0
            try:
                v = str(row[idx]).strip()
                return int(float(v)) if v and v not in ("-", "None") else 0
            except (ValueError, TypeError):
                return 0

        # Групуємо рядки по партіях + збираємо per-player статистику
        games: dict = {}  # key=(date, num) → {winner, log_lines}
        player_stats: list = []  # (date, num, nickname, survived, won, winner_faction)

        for row in all_values[1:]:
            if not row or len(row) <= max(filter(None, [idx_date, idx_num])):
                continue

            date_val   = str(row[idx_date]).strip()   if idx_date  is not None else ""
            num_val    = str(row[idx_num]).strip()    if idx_num   is not None else ""
            winner_val = str(row[idx_winner]).strip() if idx_winner is not None and idx_winner < len(row) else ""
            log_val    = str(row[idx_log]).strip()    if idx_log   is not None and idx_log    < len(row) else ""

            if not date_val and not num_val:
                continue

            key = (date_val, num_val)
            if key not in games:
                games[key] = {"winner": winner_val, "log_lines": []}
            if winner_val and not games[key]["winner"]:
                games[key]["winner"] = winner_val
            if log_val:
                games[key]["log_lines"].append(log_val)

            # Per-player статистика
            if idx_nickname is not None and idx_nickname < len(row):
                nick = str(row[idx_nickname]).strip()
                if nick and nick.lower() not in ("", "none", "нікнейм", "nickname"):
                    survive_pts = _safe_int(row, idx_survive)
                    win_pts     = _safe_int(row, idx_win_pts)
                    survived    = 1 if survive_pts > 0 else 0
                    won         = 1 if win_pts     > 0 else 0
                    winner_norm = _normalize_faction(winner_val) if winner_val else ""
                    try:
                        gnum = int(float(num_val)) if num_val else 0
                    except (ValueError, TypeError):
                        gnum = 0
                    player_stats.append((date_val, gnum, nick, survived, won, winner_norm))

        count = 0
        for (date_val, num_val), data in games.items():
            if not date_val:
                continue
            try:
                game_number = int(float(num_val)) if num_val else 0
            except (ValueError, TypeError):
                game_number = 0

            raw_log = "\n".join(data["log_lines"])
            await upsert_game_log(date_val, game_number, data["winner"], raw_log)
            count += 1

        # Зберігаємо per-player статистику
        for stat in player_stats:
            await upsert_game_player_stat(*stat)

        return count, ""
    except Exception as e:
        logger.error(f"Помилка синхронізації GameDetails: {e}")
        return 0, f"Помилка: {e}"


# ══════════════════════════════════════════════
# 3. Запис шепотів у Bankir-Bot таблицю
# ══════════════════════════════════════════════

async def write_bonus_to_bankir_sheet(nickname: str, bonus_name: str,
                                       amount: int) -> Tuple[bool, str]:
    """
    Записує нарахований бонус у лист 'Реєстрація' таблиці Bankir-Bot.
    Додає рядок: Дата | Нікнейм | Бонус | Кількість шепотів
    """
    if not GOOGLE_SHEET_ID:
        return False, "GOOGLE_SHEET_ID не задано"
    try:
        client      = _get_client(write=True)
        spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)

        # Шукаємо або створюємо лист "Бонуси"
        bonus_sheet_name = "Бонуси"
        try:
            sheet = spreadsheet.worksheet(bonus_sheet_name)
        except Exception:
            sheet = spreadsheet.add_worksheet(
                title=bonus_sheet_name, rows=1000, cols=5
            )
            sheet.update("A1:E1", [["Дата", "Нікнейм", "Бонус", "Шепоти", "Примітка"]])
            sheet.format("A1:E1", {"textFormat": {"bold": True}})

        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        sheet.append_row(
            [now, nickname, bonus_name, amount, ""],
            value_input_option="USER_ENTERED"
        )
        return True, ""
    except Exception as e:
        logger.error(f"Помилка запису бонусу в Sheets: {e}")
        return False, str(e)


# ══════════════════════════════════════════════
# MAFIAGAME Players — реєстрація нового гравця
# ══════════════════════════════════════════════

async def register_player_to_mafiagame(nickname: str, telegram_id: int,
                                        username: str, full_name: str) -> Tuple[bool, str]:
    """
    Додає нового гравця в лист Players таблиці Логи (MAFIAGAME).
    Структура: Ім'я | Нікнейм | Ігри | Фоли | Бали за програш | ... | Загальні бали
    Якщо гравець з таким нікнеймом вже є — не дублює.
    """
    if not LOGS_SHEET_ID:
        return False, "LOGS_SHEET_ID не задано"
    try:
        client = _get_client(write=True)
        sheet  = client.open_by_key(LOGS_SHEET_ID).worksheet(LOGS_PLAYERS_SHEET)

        all_rows = sheet.get_all_values()

        # Перевіряємо дублікат по нікнейму (колонка B = індекс 1)
        for i, row in enumerate(all_rows):
            if i == 0:
                continue
            if len(row) > 1 and str(row[1]).strip().lower() == nickname.strip().lower():
                # Якщо є але без TelegramID — дописуємо
                if telegram_id and (len(row) < 12 or not str(row[11]).strip() or str(row[11]).strip() in ("0", "")):
                    try:
                        col_letter = chr(ord('A') + 11)  # колонка L = TelegramID
                        sheet.update(f"{col_letter}{i+1}", [[str(telegram_id)]])
                        logger.info(f"Оновлено TelegramID для {nickname}")
                    except Exception:
                        pass
                return True, ""  # вже є

        # Додаємо новий рядок: Ім'я | Нікнейм | 0 | 0 | ... | TelegramID
        new_row = [full_name or nickname, nickname, 0, 0, 0, 0, 0, 0, 0, 0, 0, telegram_id]
        sheet.append_row(new_row, value_input_option="USER_ENTERED")
        logger.info(f"Додано в MAFIAGAME Players: {nickname} (tg={telegram_id})")
        return True, ""
    except Exception as e:
        logger.error(f"Помилка запису в MAFIAGAME Players: {e}")
        return False, str(e)


async def sync_mafiagame_players_to_bot() -> Tuple[int, str]:
    """
    Читає MAFIAGAME Players і синхронізує з ботом:
    - Якщо гравця немає в SQLite — створює з нулями
    - Оновлює бали якщо гравець вже є
    Використовує Нікнейм як ключ.
    """
    return await sync_logs_players()


async def fetch_player_stats_by_nickname(nickname: str, player_db_id: int, telegram_id: int = 0) -> bool:
    """
    Шукає гравця в MAFIAGAME Players по нікнейму і підтягує його статистику
    в SQLite для конкретного player_db_id.
    Повертає True якщо знайшов і оновив.
    """
    if not LOGS_SHEET_ID:
        return False
    try:
        client = _get_client()
        sheet  = client.open_by_key(LOGS_SHEET_ID).worksheet(LOGS_PLAYERS_SHEET)
        rows   = sheet.get_all_records()
        if not rows:
            return False

        # Шукаємо рядок де Нікнейм (колонка B) = нікнейм гравця
        matched = None
        for row in rows:
            r = {k.lower().strip(): v for k, v in row.items()}
            sheet_nick = str(r.get("нікнейм", r.get("nickname", ""))).strip()
            if sheet_nick.lower() == nickname.strip().lower():
                matched = r
                break

        if not matched:
            logger.info(f"Нікнейм '{nickname}' не знайдено в MAFIAGAME Players")
            return False

        # Записуємо TelegramID якщо знайшли гравця
        if telegram_id:
            try:
                for i, r_raw in enumerate(rows):
                    r_check = {k.lower().strip(): v for k, v in r_raw.items()}
                    sheet_nick = str(r_check.get("нікнейм", r_check.get("nickname", ""))).strip()
                    if sheet_nick.lower() == nickname.strip().lower():
                        existing_tg = str(r_check.get("telegramid", r_check.get("telegram_id", ""))).strip()
                        if not existing_tg or existing_tg in ("0", "", "None"):
                            col_letter = chr(ord("A") + 11)
                            sheet.update(f"{col_letter}{i+2}", [[str(telegram_id)]])
                        break
            except Exception as e:
                logger.warning(f"Не вдалось записати TelegramID: {e}")

        def to_int(key_variants):
            for k in key_variants:
                v = matched.get(k, "")
                try:
                    return int(float(str(v))) if str(v).strip() not in ("", "-") else 0
                except (ValueError, TypeError):
                    pass
            return 0

        points_data = {
            "lose":    to_int(["бали за програш", "points_lose"]),
            "survive": to_int(["бали за виживання", "points_survive"]),
            "win":     to_int(["бали за виграш", "points_win"]),
            "host":    to_int(["бали від ведучого", "points_host"]),
            "best":    to_int(["бали за кращо", "points_best"]),
            "guess":   to_int(["бали за угадав", "points_guess"]),
            "total":   to_int(["загальні бали", "points_total"]),
        }
        games = to_int(["ігри", "ігор", "games"])
        fols  = to_int(["фоли", "фол", "fols"])

        # Оновлюємо SQLite напряму по player_db_id
        import aiosqlite
        from app.config import DATABASE_PATH
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("""
                UPDATE players SET
                    games_played   = ?,
                    points_lose    = ?,
                    points_survive = ?,
                    points_win     = ?,
                    points_host    = ?,
                    points_best    = ?,
                    points_guess   = ?,
                    points_total   = ?,
                    updated_at     = datetime('now')
                WHERE id = ?
            """, (
                games,
                points_data["lose"], points_data["survive"],
                points_data["win"],  points_data["host"],
                points_data["best"], points_data["guess"],
                points_data["total"],
                player_db_id,
            ))
            await db.commit()

        logger.info(f"Підтягнуто статистику для '{nickname}' з MAFIAGAME Players")
        return True

    except Exception as e:
        logger.warning(f"fetch_player_stats_by_nickname помилка: {e}")
        return False


# ══════════════════════════════════════════════
# Запис операцій у лист "История Операций"
# ══════════════════════════════════════════════

async def write_operation_to_history(nickname: str, op_type: str,
                                      amount: int, comment: str = "") -> bool:
    """
    Записує операцію у лист «История Операций» таблиці Bankir-Bot.
    Структура: Дата | Время | Игрок | Тип операции | Количество фишек
    """
    try:
        from app.config import GOOGLE_SHEET_ID, HISTORY_SHEET_NAME
        if not GOOGLE_SHEET_ID:
            return False
        client      = _get_client(write=True)
        spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)

        HEADERS = ["Дата", "Время", "Игрок", "Тип операции", "Количество фишек"]
        try:
            sheet = spreadsheet.worksheet(HISTORY_SHEET_NAME)
        except Exception:
            sheet = spreadsheet.add_worksheet(
                title=HISTORY_SHEET_NAME, rows=5000, cols=5
            )
            sheet.update("A1:E1", [HEADERS])
            sheet.format("A1:E1", {"textFormat": {"bold": True}})

        from datetime import datetime
        now  = datetime.now()
        date = now.strftime("%Y-%m-%d")
        time = now.strftime("%H:%M:%S")

        op_names = {
            "add":      "Нарахування",
            "subtract": "Списання",
            "bonus":    "Бонус",
            "bet_win":  "Виграш ставки",
            "bet_lose": "Програш ставки",
            "spend":    "Витрата",
            "freeze":   "Заморожено",
            "unfreeze": "Розморожено",
        }
        op_name = op_names.get(op_type, op_type)
        if comment:
            op_name = f"{op_name}: {comment}"

        sign = "+" if op_type in ("add", "bonus", "bet_win", "unfreeze") else "-"
        amount_str = f"{sign}{amount}"

        sheet.append_row([date, time, nickname, op_name, amount_str],
                          value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        logger.warning(f"write_operation_to_history помилка: {e}")
        return False


async def find_similar_nicknames(query: str, limit: int = 5) -> list:
    """
    Шукає схожі нікнейми в MAFIAGAME Players.
    Враховує: регістр, и/і/ї, е/є, й, ё/е — щоб Кимельман знайшов Кімельман.
    """
    if not LOGS_SHEET_ID:
        return []

    def normalize(s: str) -> str:
        """Нормалізує рядок для порівняння."""
        s = s.lower().strip()
        # Українська/російська — схожі букви
        replacements = [
            ("и", "і"), ("ї", "і"), ("є", "е"), ("ё", "е"),
            ("ъ", "ь"), ("э", "е"), ("ы", "і"),
        ]
        for old, new in replacements:
            s = s.replace(old, new)
        return s

    def similarity(a: str, b: str) -> float:
        """Проста схожість двох рядків після нормалізації."""
        import difflib
        return difflib.SequenceMatcher(None, normalize(a), normalize(b)).ratio()

    try:
        client = _get_client()
        sheet  = client.open_by_key(LOGS_SHEET_ID).worksheet(LOGS_PLAYERS_SHEET)
        rows   = sheet.get_all_records()
        q_norm = normalize(query)

        scored = []
        for row in rows:
            r    = {k.lower().strip(): v for k, v in row.items()}
            nick = str(r.get("нікнейм", r.get("nickname", ""))).strip()
            if not nick:
                continue
            n_norm = normalize(nick)
            # Пропускаємо тільки якщо оригінальні рядки однакові (з урахуванням регістру)
            if nick.lower() == query.strip().lower() and normalize(nick) == q_norm:
                continue
            # Критерії схожості:
            # 1. Починається так само після нормалізації
            # 2. Один містить інший
            # 3. Схожість > 0.7 (дифлібом)
            score = similarity(query, nick)
            if (n_norm.startswith(q_norm[:3]) or
                q_norm in n_norm or n_norm in q_norm or
                score >= 0.70):
                scored.append((score, nick))

        # Сортуємо по схожості — найближчі зверху
        scored.sort(key=lambda x: x[0], reverse=True)
        return [nick for _, nick in scored[:limit]]
    except Exception as e:
        logger.warning(f"find_similar_nicknames error: {e}")
        return []
