# app/services/sheets_service.py
import os
import logging
from datetime import datetime
from typing import Tuple

from app.config import (
    GOOGLE_CREDENTIALS_FILE, GOOGLE_SHEET_ID,
    GOOGLE_SHEET_NAME, GOOGLE_DIARY_SHEET_NAME, GOOGLE_REG_SHEET_NAME,
)
from app.database.queries import upsert_player, upsert_diary_entry

logger = logging.getLogger(__name__)

REG_HEADERS = ["telegram_id", "username", "full_name", "nickname", "registered_at", "note"]


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
    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    return gspread.authorize(creds)


def _ensure_sheet(spreadsheet, name: str, cols: int):
    try:
        return spreadsheet.worksheet(name)
    except Exception:
        sheet = spreadsheet.add_worksheet(title=name, rows=1000, cols=cols)
        return sheet


# ── Запис нового гравця у лист Реєстрація ───────────────────

async def register_user_to_sheets(telegram_id: int, username: str,
                                   full_name: str, nickname: str) -> Tuple[bool, str]:
    if not GOOGLE_SHEET_ID:
        return False, "GOOGLE_SHEET_ID не задано у .env"
    try:
        client      = _get_client(write=True)
        spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)
        sheet       = _ensure_sheet(spreadsheet, GOOGLE_REG_SHEET_NAME, len(REG_HEADERS))

        # Додаємо заголовок якщо порожньо
        all_vals = sheet.get_all_values()
        if not all_vals or all_vals[0] != REG_HEADERS:
            sheet.insert_row(REG_HEADERS, 1)
            sheet.format("A1:F1", {"textFormat": {"bold": True}})
            all_vals = [REG_HEADERS]

        # Перевіряємо дублікат
        existing_row = None
        for i, row in enumerate(all_vals):
            if i == 0:
                continue
            if row and str(row[0]).strip() == str(telegram_id):
                existing_row = i + 1
                break

        now     = datetime.now().strftime("%Y-%m-%d %H:%M")
        new_row = [str(telegram_id), username or "", full_name or "", nickname, now, ""]

        if existing_row:
            sheet.update(f"A{existing_row}:E{existing_row}", [new_row[:5]])
        else:
            sheet.append_row(new_row, value_input_option="USER_ENTERED")

        # ── Також додаємо в лист Статистика ─────────────────
        # щоб гравець одразу з'являвся в боті після синхронізації
        await _add_to_stats_sheet(spreadsheet, telegram_id, nickname)

        logger.info(f"Зареєстровано: {nickname} (tg={telegram_id})")
        return True, ""
    except FileNotFoundError as e:
        return False, str(e)
    except Exception as e:
        logger.error(f"Помилка реєстрації в Sheets: {e}")
        return False, f"Помилка Google Sheets: {e}"


async def _add_to_stats_sheet(spreadsheet, telegram_id: int, nickname: str):
    """
    Додає нового гравця у лист Статистика якщо його там ще немає.
    player_id = TG_{telegram_id}
    """
    try:
        stats_sheet = _ensure_sheet(spreadsheet, GOOGLE_SHEET_NAME, 10)
        all_vals    = stats_sheet.get_all_values()

        stats_headers = [
            "player_id", "nickname", "games_played", "rating",
            "status", "rank_position", "wins", "survived", "city_wins", "mafia_wins"
        ]

        # Заголовок якщо порожньо
        if not all_vals or all_vals[0] != stats_headers:
            if not all_vals:
                stats_sheet.insert_row(stats_headers, 1)
                stats_sheet.format("A1:J1", {"textFormat": {"bold": True}})
                all_vals = [stats_headers]

        player_id = f"TG_{telegram_id}"

        # Перевіряємо чи вже є
        for i, row in enumerate(all_vals):
            if i == 0:
                continue
            if row and str(row[0]).strip() == player_id:
                return  # вже є

        # Додаємо рядок
        new_row = [player_id, nickname, "0", "0", "Новачок", "0", "0", "0", "0", "0"]
        stats_sheet.append_row(new_row, value_input_option="USER_ENTERED")
        logger.info(f"Додано {player_id} ({nickname}) у лист Статистика")
    except Exception as e:
        logger.warning(f"Не вдалося додати в Статистику: {e}")


# ── Синхронізація статистики → SQLite ───────────────────────

async def sync_players_from_sheets() -> Tuple[int, str]:
    if not GOOGLE_SHEET_ID:
        return 0, "GOOGLE_SHEET_ID не задано у .env"
    try:
        client = _get_client()
        sheet  = client.open_by_key(GOOGLE_SHEET_ID).worksheet(GOOGLE_SHEET_NAME)
        rows   = sheet.get_all_records()
        if not rows:
            return 0, "Таблиця статистики порожня."
        col_map = {
            "player_id":"player_id", "nickname":"nickname",
            "games_played":"games_played", "rating":"rating",
            "status":"status", "rank_position":"rank_position",
            "wins":"wins", "survived":"survived",
            "city_wins":"city_wins", "mafia_wins":"mafia_wins",
        }
        count = 0
        for row in rows:
            r    = {k.lower().strip(): v for k, v in row.items()}
            data = {field: r[col] for col, field in col_map.items() if r.get(col, "") != ""}
            if not data.get("player_id") or not data.get("nickname"):
                continue
            for f in ["games_played","rank_position","wins","survived","city_wins","mafia_wins"]:
                try:
                    data[f] = int(data.get(f, 0))
                except (ValueError, TypeError):
                    data[f] = 0
            try:
                data["rating"] = float(data.get("rating", 0))
            except (ValueError, TypeError):
                data["rating"] = 0.0
            await upsert_player(data)
            count += 1
        return count, ""
    except Exception as e:
        return 0, f"Помилка: {e}"


# ── Синхронізація щоденника → SQLite ────────────────────────
# Структура листа «Щоденник»:
#   game_date | game_number | title | full_text

async def sync_diary_from_sheets() -> Tuple[int, str]:
    if not GOOGLE_SHEET_ID:
        return 0, "GOOGLE_SHEET_ID не задано у .env"
    try:
        client = _get_client()
        # Відкриваємо лист (назва з .env, default = "Щоденник")
        spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)
        try:
            sheet = spreadsheet.worksheet(GOOGLE_DIARY_SHEET_NAME)
        except Exception:
            return 0, (
                f"Лист «{GOOGLE_DIARY_SHEET_NAME}» не знайдено в таблиці.\n\n"
                f"Створи лист з назвою <b>{GOOGLE_DIARY_SHEET_NAME}</b> "
                f"і заголовками:\n"
                f"<code>game_date | game_number | title | full_text</code>"
            )

        rows = sheet.get_all_records()
        if not rows:
            return 0, (
                f"Лист «{GOOGLE_DIARY_SHEET_NAME}» порожній.\n\n"
                f"Заголовки першого рядка мають бути:\n"
                f"<code>game_date | game_number | title | full_text</code>\n\n"
                f"Приклад рядка:\n"
                f"<code>2024-12-01 | 1 | Ніч підозр | Текст партії...</code>"
            )

        count = 0
        for row in rows:
            r           = {k.lower().strip(): v for k, v in row.items()}
            game_date   = str(r.get("game_date",   "")).strip()
            game_number = str(r.get("game_number", "")).strip()
            title       = str(r.get("title",       "")).strip()
            full_text   = str(r.get("full_text",   "")).strip()

            if not game_date or not game_number or not title:
                continue

            await upsert_diary_entry(game_date, game_number, title, full_text)
            count += 1

        return count, ""
    except Exception as e:
        logger.error(f"Помилка синхронізації щоденника: {e}")
        return 0, f"Помилка: {e}"
