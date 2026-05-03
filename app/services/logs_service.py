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
    Читає лист Players з таблиці Логи.
    Структура: Ім'я | Нікнейм | Ігри | Фоли |
               Бали за програш | Бали за виживання | Бали за виграш |
               Бали від ведучого | Бали за кращо | Бали за угадав | Загальні бали
    """
    if not LOGS_SHEET_ID:
        return 0, "LOGS_SHEET_ID не задано у .env"
    try:
        client = _get_client()
        sheet  = client.open_by_key(LOGS_SHEET_ID).worksheet(LOGS_PLAYERS_SHEET)
        rows   = sheet.get_all_records()
        if not rows:
            return 0, f"Лист '{LOGS_PLAYERS_SHEET}' порожній."

        count = 0
        for row in rows:
            r = {k.lower().strip(): v for k, v in row.items()}

            # Нікнейм — спільний ключ між таблицями
            nickname = str(r.get("нікнейм", r.get("nickname", ""))).strip()
            if not nickname:
                continue

            def to_int(key_variants):
                for k in key_variants:
                    v = r.get(k, "")
                    try:
                        return int(float(str(v))) if v != "" else 0
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

            await update_player_points(nickname, points_data)
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

        idx_date    = col_idx(["дата", "date"])
        idx_num     = col_idx(["№ партії", "№ партії", "# партії", "номер партії", "no"])
        idx_winner  = col_idx(["переможна фракція", "переможець", "winner"])
        idx_log     = col_idx([LOGS_TEXT_COLUMN.lower(), "логи", "log", "лог", "текст"])

        if idx_date is None or idx_num is None:
            return 0, (
                f"Не знайдено колонки 'Дата' або '№ партії' в листі '{LOGS_GAMES_SHEET}'.\n"
                f"Знайдені заголовки: {', '.join(all_values[0][:10])}"
            )

        # Групуємо рядки по партіях
        games: dict = {}  # key=(date, num) → {winner, log_lines}
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
