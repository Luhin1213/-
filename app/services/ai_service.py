# app/services/ai_service.py
# Генерація тексту Щоденника Ребекки Найт через Groq API.
#
# Як отримати безкоштовний ключ (30 секунд):
#   1. Зайди на https://console.groq.com
#   2. Зареєструйся (email або Google)
#   3. Зліва → API Keys → Create API Key
#   4. Скопіюй ключ (починається з gsk_...)
#   5. Встав у .env: GROQ_API_KEY=gsk_...
#
# Безкоштовний ліміт: 14,400 запитів/день, 30 запитів/хвилину

import logging
from typing import Tuple
from app.config import GROQ_API_KEY

logger = logging.getLogger(__name__)

REBECCA_PROMPT = (
    "Перетвори логи мафії на художній нуарний щоденник від імені Ребекки Найт,"
    " незалежної журналістки Міста Гріхів 1958 року.\n"
    "Пиши українською, атмосферно, від імені Ребекки Найт як детективний роман:"
    " ніч, дощ, старий суд, портові околиці, страх, шантаж, мовчання, голосування і фінальний вирок.\n\n"
    "Правила:\n"
    "1. На початку: «партія #» і «перелік подій з [дата початку] по [дата кінця]».\n"
    "2. Рік завжди 1958. Кожен ігровий день = наступна календарна дата.\n"
    "3. Імена без номерів, не змінювати, писати ПРОПИСНИМИ.\n"
    "4. Вночі не писати імена тих, хто виконує дію, тільки ролі. Цілі дій можна писати іменами.\n"
    "5. Ролі підкреслювати через <u>РОЛЬ</u>.\n"
    "6. Ролі гравців не розкривати на початку і в середині. Повний список ролей тільки в кінці.\n"
    "7. Усі нічні дії писати з часом від 22:30 до 06:00.\n"
    "8. Вбивства ставити після більшості дій, крім лікування.\n"
    "9. Усі дії з логів зберігати, нічого не пропускати, якщо роль жива.\n"
    "10. Якщо роль мертва, наступної ночі один раз написати, що вона не змогла походити після смерті.\n"
    "11. Якщо лікар приходить не до жертви пострілу, він не рятує, а перевіряє стан.\n"
    "12. ДОН, ШАНТАЖИСТ і КРАДІЙКА діють художньо: тиск, конверти, шантаж, крадіжка доказів, плутання слідів.\n"
    "13. Перед голосуванням описати сцену в залі суду.\n"
    "14. Голосування компонувати так: «Проти ІМ'Я: ІМ'Я, ІМ'Я».\n"
    "15. Писати до кінця з розгорнутим фіналом.\n"
    "16. Події відбуваються на околицях Міста Гріхів, локацію придумай сам.\n"
    "17. Не змінюй смерті, голосування, результат гри і дії з логів.\n"
    "18. В кінці після фіналу: «Хто ким грав:» і список ІМ'Я — <u>РОЛЬ</u>.\n\n"
    "На основі цього логу партії напиши запис у щоденник:\n\n"
    "---\n{log_text}\n---\n\n"
    "Переможець: {winner}\n\n"
    "Напиши тільки текст щоденника, без заголовку і пояснень."
)


async def generate_diary_entry(log_text: str, winner: str,
                                game_date: str, game_number: int) -> Tuple[str, str]:
    if not GROQ_API_KEY:
        return "", (
            "❌ Groq API ключ не задано!\n\n"
            "Як отримати безкоштовно:\n"
            "1. Зайди на https://console.groq.com\n"
            "2. Зареєструйся\n"
            "3. API Keys → Create API Key\n"
            "4. Додай у .env:\n"
            "   GROQ_API_KEY=gsk_...\n"
            "5. Перезапусти бота"
        )

    if not log_text or len(log_text.strip()) < 10:
        return "", "❌ Лог партії порожній. Спочатку синхронізуй GameDetails."

    try:
        from groq import Groq

        client = Groq(api_key=GROQ_API_KEY)

        prompt = REBECCA_PROMPT.format(
            log_text=log_text[:4000],
            winner=winner or "невідомо",
        )

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0.8,
        )

        generated_text = response.choices[0].message.content.strip()
        title     = f"Партія #{game_number} — {game_date}"
        full_text = f"📖 <b>{title}</b>\n\n{generated_text}"

        logger.info(f"Groq згенерував щоденник: {game_date} партія #{game_number}")
        return full_text, ""

    except ImportError:
        return "", (
            "❌ Бібліотека groq не встановлена!\n\n"
            "Запусти в командному рядку:\n"
            "<code>pip install groq</code>"
        )
    except Exception as e:
        logger.error(f"Помилка генерації через Groq: {e}")
        err = str(e).lower()
        if "api_key" in err or "invalid" in err or "auth" in err:
            return "", "❌ Невірний API ключ. Перевір GROQ_API_KEY у .env"
        if "rate_limit" in err or "429" in err:
            return "", "❌ Перевищено ліміт Groq API. Спробуй через хвилину."
        return "", f"❌ Помилка Groq: {e}"
