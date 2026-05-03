# app/handlers/common.py
import asyncio
import logging
import os
import sys
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from app.database.queries import (
    get_or_create_user, is_admin, get_player_by_linked_user, create_player_auto,
)
from app.keyboards.main_kb import main_menu_player, main_menu_admin
from app.services.sheets_service import register_user_to_sheets
from app.utils.states import RegState
from app.config import USERINFOBOT_LINK

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    u = message.from_user
    await get_or_create_user(u.id, u.username or "", u.full_name or "")

    admin  = await is_admin(u.id)
    player = await get_player_by_linked_user(u.id)

    if admin:
        await state.clear()
        await message.answer(
            f"🔑 Адмін-панель\nПривіт, <b>{u.full_name}</b>!",
            parse_mode="HTML",
            reply_markup=main_menu_admin()
        )
        return

    if player:
        await state.clear()
        await message.answer(
            f"🎭 З поверненням, <b>{player['nickname']}</b>!\n\nОбери дію 👇",
            parse_mode="HTML",
            reply_markup=main_menu_player()
        )
        return

    # Новий гравець — реєстрація
    await message.answer(
        "🎭 Ласкаво просимо до клубу <b>Мафія — Банкір</b>!\n\n"
        "Для реєстрації введи свій ігровий псевдонім:\n"
        "<i>(саме той нік, під яким ти граєш за столом)</i>",
        parse_mode="HTML"
    )
    await state.set_state(RegState.enter_nickname)


@router.message(RegState.enter_nickname)
async def reg_nickname(message: Message, state: FSMContext, bot: Bot):
    nickname = message.text.strip()
    if len(nickname) < 2 or len(nickname) > 32:
        await message.answer("❌ Псевдонім має бути від 2 до 32 символів. Спробуй ще:")
        return

    u = message.from_user

    # Створюємо гравця і одразу прив'язуємо
    player = await create_player_auto(nickname, u.id, u.username or "", u.full_name or "")

    # Записуємо в Google Sheets (асинхронно, не блокуємо бота)
    ok, err = await register_user_to_sheets(u.id, u.username or "", u.full_name or "", nickname)
    if not ok:
        logger.warning(f"Не вдалося записати в Sheets: {err}")

    await state.clear()
    await message.answer(
        f"✅ <b>Реєстрацію завершено!</b>\n\n"
        f"Псевдонім: <b>{nickname}</b>\n"
        f"Telegram ID: <code>{u.id}</code>\n\n"
        f"Всі функції доступні 👇",
        parse_mode="HTML",
        reply_markup=main_menu_player()
    )
    logger.info(f"Зареєстровано гравець: {nickname} (tg={u.id})")


# ── ПереСтарт ────────────────────────────────────────────────

@router.message(F.text == "♻️ ПереСтарт")
async def restart_bot(message: Message, bot: Bot):
    admin = await is_admin(message.from_user.id)
    kb    = main_menu_admin() if admin else main_menu_player()
    await message.answer(
        "♻️ Перезавантажую меню...",
        reply_markup=kb
    )
    # Для адміна — повний рестарт процесу
    if admin:
        async def do_restart():
            await asyncio.sleep(1)
            await bot.session.close()
            os.execv(sys.executable, [sys.executable, "-m", "app.main"])
        asyncio.create_task(do_restart())


# ── Допомога ─────────────────────────────────────────────────

@router.message(F.text == "❓ Допомога")
async def help_handler(message: Message):
    await message.answer(
        "❓ <b>Довідка — Мафія Банкір</b>\n\n"
        "🎰 <b>Шепоти</b> — внутрішня валюта клубу.\n\n"
        "👤 <b>Мій профіль</b> — статистика ігор\n"
        "🎰 <b>Мої фішки</b> — баланс шепот\n"
        "🏆 <b>Рейтинг</b> — топ гравців\n"
        "📋 <b>Історія операцій</b> — по 5, листати кнопками\n\n"
        "🎲 <b>Ставки:</b>\n"
        "  🔴 На Червоність — фактичне списання\n"
        "  ⚔️ Проти гравця — колір + номер ×2\n"
        "  🎯 На перемогу сторони — ×2 або ×3\n"
        "  💀 Смерть вночі — ×3, тільки для червоних\n\n"
        "🛒 <b>Витрати</b> — від 1 до 20 шепот\n"
        "  (кожна потребує підтвердження адміна)\n\n"
        "📖 <b>Щоденник Ребеки Найт</b> — архів партій\n\n"
        f"🆔 Дізнатись свій Telegram ID: {USERINFOBOT_LINK}",
        parse_mode="HTML",
        disable_web_page_preview=True
    )
