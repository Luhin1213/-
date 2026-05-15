# app/handlers/group_handler.py
#
# Обробник подій у Telegram-групі:
#   - Привітання нових учасників у групі
#   - Особисте повідомлення новому учаснику з інфо про бота
#   - Оновлення повідомлення про збір при записі/відписці

import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, ChatMemberUpdated
from aiogram.filters import ChatMemberUpdatedFilter, JOIN_TRANSITION

from app.config import GROUP_ID, ANNOUNCEMENTS_THREAD_ID
from app.database.queries import (
    get_user_language, get_player_by_linked_user,
)
from app.utils.i18n import t

logger = logging.getLogger(__name__)
router = Router()

# Фільтруємо тільки нашу групу
router.message.filter(F.chat.id == GROUP_ID)
router.chat_member.filter(F.chat.id == GROUP_ID)


# ══════════════════════════════════════════════
# НОВИЙ УЧАСНИК ГРУПИ
# ══════════════════════════════════════════════

@router.chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def new_member(event: ChatMemberUpdated, bot: Bot):
    """Спрацьовує коли хтось вступає в групу."""
    user = event.new_chat_member.user
    if user.is_bot:
        return

    lang = await get_user_language(user.id)

    # ── Привітання в групі ───────────────────────────────────
    if lang == "UA":
        group_welcome = (
            f"👋 Вітаємо <b>{user.full_name}</b> у клубі "
            f"<b>Lu's Bluff Business</b>!\n\n"
            f"🎭 Місто Грехів чекало саме тебе.\n\n"
            f"📌 Ознайомся з гілками групи:\n"
            f"• <b>Анонси</b> — розклад ігор та оголошення\n"
            f"• <b>Загальний чат</b> — спілкування між партіями\n"
            f"• <b>Правила</b> — обов'язково прочитай!\n"
            f"• <b>Рейтинг</b> — статистика гравців\n\n"
            f"🤖 Для гри в Банкіра напиши особисто боту: @BleffBankir_Bot"
        )
    else:
        group_welcome = (
            f"👋 Добро пожаловать <b>{user.full_name}</b> в клуб "
            f"<b>Lu's Bluff Business</b>!\n\n"
            f"🎭 Город Грехов ждал именно тебя.\n\n"
            f"📌 Ознакомься с ветками группы:\n"
            f"• <b>Анонсы</b> — расписание игр и объявления\n"
            f"• <b>Общий чат</b> — общение между партиями\n"
            f"• <b>Правила</b> — обязательно прочитай!\n"
            f"• <b>Рейтинг</b> — статистика игроков\n\n"
            f"🤖 Для игры с Банкиром напиши боту: @BleffBankir_Bot"
        )

    try:
        await bot.send_message(
            chat_id=GROUP_ID,
            text=group_welcome,
            parse_mode="HTML",
            message_thread_id=None,  # В загальний чат (не в тему)
        )
    except Exception as e:
        logger.warning(f"Не вдалось надіслати привітання в групу: {e}")

    # ── Особисте повідомлення ────────────────────────────────
    if lang == "UA":
        private_msg = (
            f"👋 Привіт, <b>{user.full_name}</b>!\n\n"
            f"Ти щойно приєднався до клубу <b>Lu's Bluff Business</b> 🎭\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 <b>Цей бот — твій Банкір у Місті Грехів</b>\n\n"
            f"Тут ти можеш:\n"
            f"🎰 Зберігати та витрачати <b>Шепоти</b> (ігрова валюта)\n"
            f"📊 Переглядати свою <b>статистику та рейтинг</b>\n"
            f"🎲 Робити <b>ставки</b> на результати партій\n"
            f"🛒 Купувати <b>ігрові переваги</b> за Шепоти\n"
            f"📖 Читати <b>Щоденник Ребеки Найт</b> — архів партій\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Гілки групи:</b>\n"
            f"• Анонси — розклад та оголошення про ігри\n"
            f"• Загальний чат — спілкуйся між партіями\n"
            f"• Правила — умови гри та клубу\n"
            f"• Рейтинг — таблиця лідерів\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 Натисни /start щоб зареєструватись і розпочати!\n\n"
            f"<i>Хто знає, хто буде Вовком, а хто — Вівцею... 😎</i>"
        )
    else:
        private_msg = (
            f"👋 Привет, <b>{user.full_name}</b>!\n\n"
            f"Ты только что присоединился к клубу <b>Lu's Bluff Business</b> 🎭\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 <b>Этот бот — твой Банкир в Городе Грехов</b>\n\n"
            f"Здесь ты можешь:\n"
            f"🎰 Хранить и тратить <b>Шёпоты</b> (игровая валюта)\n"
            f"📊 Смотреть свою <b>статистику и рейтинг</b>\n"
            f"🎲 Делать <b>ставки</b> на результаты партий\n"
            f"🛒 Покупать <b>игровые преимущества</b> за Шёпоты\n"
            f"📖 Читать <b>Дневник Ребекки Найт</b> — архив партий\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Ветки группы:</b>\n"
            f"• Анонсы — расписание и объявления об играх\n"
            f"• Общий чат — общайся между партиями\n"
            f"• Правила — условия игры и клуба\n"
            f"• Рейтинг — таблица лидеров\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 Нажми /start чтобы зарегистрироваться и начать!\n\n"
            f"<i>Кто знает, кто будет Волком, а кто — Овцой... 😎</i>"
        )

    try:
        await bot.send_message(
            chat_id=user.id,
            text=private_msg,
            parse_mode="HTML"
        )
    except Exception as e:
        # Якщо користувач не писав боту — не можемо надіслати ЛС
        logger.info(f"Не вдалось надіслати ЛС {user.id}: {e}")


# ══════════════════════════════════════════════
# ПУБЛІКАЦІЯ ЗБОРУ В ГРУПІ
# ══════════════════════════════════════════════

async def post_gathering_to_group(bot: Bot, gathering_id: int,
                                   game_date: str, game_time: str,
                                   location: str, description: str,
                                   signed_count: int = 0,
                                   max_players: int = 13,
                                   message_id: int = None) -> int:
    """
    Публікує або оновлює оголошення про збір у темі «Анонси».
    Повертає message_id опублікованого повідомлення.
    """
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    # Список гравців у вигляді прогрес-бару
    filled   = min(signed_count, max_players)
    empty    = max_players - filled
    bar      = "🟢" * filled + "⚪" * empty
    status   = "✅ Гра відбудеться!" if signed_count >= 9 else f"⏳ Набираємо ({signed_count}/9 мін.)"

    text = (
        f"🎮 <b>ОГОЛОШЕННЯ ПРО ГРУ</b>\n\n"
        f"📅 Дата: <b>{game_date}</b>\n"
        f"⏰ Час: <b>{game_time}</b>\n"
        f"📍 Місце: <b>{location}</b>\n"
        + (f"📝 {description}\n" if description else "") +
        f"\n👥 Записано: <b>{signed_count}/{max_players}</b>\n"
        f"{bar}\n\n"
        f"{status}\n\n"
        f"🤖 Щоб записатись — відкрий @BleffBankir_Bot → 🎮 Збір"
    )

    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(
        text=f"🤖 Відкрити Банкіра",
        url="https://t.me/BleffBankir_Bot"
    ))
    kb = b.as_markup()

    try:
        if message_id:
            # Оновлюємо існуюче повідомлення
            await bot.edit_message_text(
                chat_id=GROUP_ID,
                message_id=message_id,
                text=text,
                parse_mode="HTML",
                reply_markup=kb
            )
            return message_id
        else:
            # Публікуємо нове в темі «Анонси»
            msg = await bot.send_message(
                chat_id=GROUP_ID,
                text=text,
                parse_mode="HTML",
                reply_markup=kb,
                message_thread_id=ANNOUNCEMENTS_THREAD_ID
            )
            return msg.message_id
    except Exception as e:
        logger.error(f"Помилка публікації збору в групу: {e}")
        return 0


async def cancel_gathering_in_group(bot: Bot, message_id: int,
                                     game_date: str):
    """Оновлює повідомлення про збір як скасоване."""
    try:
        await bot.edit_message_text(
            chat_id=GROUP_ID,
            message_id=message_id,
            text=(
                f"❌ <b>ГРУ СКАСОВАНО</b>\n\n"
                f"📅 {game_date}\n\n"
                f"<i>Деталі уточнюйте у ведучого.</i>"
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning(f"Не вдалось оновити повідомлення скасування: {e}")
