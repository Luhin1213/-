# app/services/ai_service.py
# Генерація тексту Щоденника Ребекки Найт через Google Gemini API.
# Використовує нову бібліотеку google-genai

import logging
from typing import Tuple
from app.config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

REBECCA_PROMPT = """Ти — Ребекка Найт, таємничий хронікер міста Грехів.
Твій стиль: нуар, атмосферний, від першої особи, коротко і влучно.
Ти не описуєш механіку гри — ти розповідаєш ІСТОРІЮ що відбулась цієї ночі.
Використовуй ігрові псевдоніми гравців як імена персонажів.
Довжина: 150-300 слів. Мова: українська.

На основі цього логу партії напиши запис у щоденник:

---
{log_text}
---

Переможець: {winner}

Напиши тільки текст щоденника, без заголовку і пояснень."""


async def generate_diary_entry(log_text: str, winner: str,
                                game_date: str, game_number: int) -> Tuple[str, str]:
    if not GEMINI_API_KEY:
        return "", (
            "❌ Gemini API ключ не задано!\n\n"
            "1. Зайди на https://aistudio.google.com/apikey\n"
            "2. Натисни Create API Key\n"
            "3. Додай у .env: GEMINI_API_KEY=AIzaSy...\n"
            "4. Перезапусти бота"
        )

    if not log_text or len(log_text.strip()) < 10:
        return "", "❌ Лог партії порожній. Спочатку синхронізуй GameDetails."

    try:
        from google import genai

        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = REBECCA_PROMPT.format(
            log_text=log_text[:4000],
            winner=winner or "невідомо",
        )

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )

        generated_text = response.text.strip()
        title     = f"Партія #{game_number} — {game_date}"
        full_text = f"📖 <b>{title}</b>\n\n{generated_text}"

        logger.info(f"Gemini згенерував щоденник: {game_date} партія #{game_number}")
        return full_text, ""

    except ImportError:
        return "", (
            "❌ Бібліотека не встановлена!\n\n"
            "Запусти в командному рядку:\n"
            "<code>pip install google-genai</code>"
        )
    except Exception as e:
        logger.error(f"Помилка генерації через Gemini: {e}")
        err = str(e).lower()
        if "api_key" in err or "invalid" in err or "permission" in err:
            return "", "❌ Невірний API ключ. Перевір GEMINI_API_KEY у .env"
        if "quota" in err or "limit" in err or "429" in err:
            return "", "❌ Перевищено ліміт Gemini API. Спробуй через хвилину."
        return "", f"❌ Помилка Gemini: {e}"
