# app/main.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio, logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import BOT_TOKEN
from app.database.models import init_db
from app.handlers import (
    common, player, admin, bets, spendings,
    diary, help_handler, gathering, group_handler,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Запускаю бот клубу Мафія...")
    await init_db()
    logger.info("База даних готова")

    bot = Bot(token=BOT_TOKEN)
    dp  = Dispatcher(storage=MemoryStorage())

    dp.include_router(common.router)
    dp.include_router(admin.router)
    dp.include_router(player.router)
    dp.include_router(bets.router)
    dp.include_router(spendings.router)
    dp.include_router(diary.router)
    dp.include_router(help_handler.router)
    dp.include_router(gathering.router)
    dp.include_router(group_handler.router)

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущений і готовий до роботи!")

    try:
        await dp.start_polling(bot)
    finally:
        logger.info("Бот зупинений")
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
