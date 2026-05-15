# app/config.py
import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
_raw = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: List[int] = [int(x.strip()) for x in _raw.split(",") if x.strip().isdigit()]

# ── Bankir-Bot таблиця (основна) ────────────────────────────
GOOGLE_CREDENTIALS_FILE: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_SHEET_ID: str = os.getenv("GOOGLE_SHEET_ID", "")
GOOGLE_SHEET_NAME: str = os.getenv("GOOGLE_SHEET_NAME", "Статистика")
GOOGLE_DIARY_SHEET_NAME: str = os.getenv("GOOGLE_DIARY_SHEET_NAME", "Щоденник")
GOOGLE_REG_SHEET_NAME: str = os.getenv("GOOGLE_REG_SHEET_NAME", "Реєстрація")

# ── Таблиця Логи (окрема) ───────────────────────────────────
LOGS_SHEET_ID: str = os.getenv(
    "LOGS_SHEET_ID",
    "1LloKJb8UwTzyECX8SpzyBxeO8BsiZmA-r5CA9CJ4J0Y"
)
LOGS_PLAYERS_SHEET: str = os.getenv("LOGS_PLAYERS_SHEET", "Players")
LOGS_GAMES_SHEET: str   = os.getenv("LOGS_GAMES_SHEET",   "GameDetails")

# Колонка з текстом логу в GameDetails
# Якщо заголовок іншій — зміни тут
LOGS_TEXT_COLUMN: str = os.getenv("LOGS_TEXT_COLUMN", "Логи")

# ── Claude API для генерації щоденника ──────────────────────
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")


DATABASE_PATH: str = os.getenv("DATABASE_PATH", "mafia_club.db")

CHIP_EMOJI = "🎰"
CHIP_NAME  = "шепот"
USERINFOBOT_LINK = "https://t.me/userinfobot"

if not BOT_TOKEN:
    raise ValueError("❌ Токен бота не задано! Перевір файл .env")

# ── Groq API ───────────────────────────────────────────────
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

# ── Telegram група ───────────────────────────────────────────
GROUP_ID: int = int(os.getenv("GROUP_ID", "-1002198467706"))
ANNOUNCEMENTS_THREAD_ID: int = int(os.getenv("ANNOUNCEMENTS_THREAD_ID", "2698"))

# Лист "История Операций" в Bankir-Bot
HISTORY_SHEET_NAME: str = os.getenv("HISTORY_SHEET_NAME", "История Операций")
