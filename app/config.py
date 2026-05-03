# app/config.py
import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
_raw = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: List[int] = [int(x.strip()) for x in _raw.split(",") if x.strip().isdigit()]

GOOGLE_CREDENTIALS_FILE: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_SHEET_ID: str = os.getenv("GOOGLE_SHEET_ID", "")
GOOGLE_SHEET_NAME: str = os.getenv("GOOGLE_SHEET_NAME", "Статистика")
GOOGLE_DIARY_SHEET_NAME: str = os.getenv("GOOGLE_DIARY_SHEET_NAME", "Щоденник")
GOOGLE_REG_SHEET_NAME: str = os.getenv("GOOGLE_REG_SHEET_NAME", "Реєстрація")
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "mafia_club.db")

CHIP_EMOJI = "🎰"
CHIP_NAME  = "шепот"          # схиляється: 1 шепот, 5 шепот

# Посилання на бота для отримання Telegram ID при реєстрації
USERINFOBOT_LINK = "https://t.me/userinfobot"

if not BOT_TOKEN:
    raise ValueError("❌ Токен бота не задано! Перевір файл .env")
