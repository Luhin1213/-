#!/usr/bin/env python3
# seed_data.py
# Скрипт для заполнения базы тестовыми данными.
# Запусти ОДИН РАЗ после первого запуска бота:
#   python seed_data.py

import asyncio
import sys
import os

# Добавляем корневую папку в путь
sys.path.insert(0, os.path.dirname(__file__))

from app.database.models import init_db
from app.database.queries import upsert_player, change_balance


async def seed():
    print("🌱 Заполняю базу тестовыми данными...")

    # Создаём таблицы если нет
    await init_db()

    # Тестовые игроки
    test_players = [
        {
            "player_id": "P001",
            "nickname": "Виктор Тёмный",
            "games_played": 42,
            "rating": 1850.5,
            "status": "Профессионал",
            "rank_position": 1,
            "wins": 28,
            "survived": 35,
            "city_wins": 18,
            "mafia_wins": 10,
        },
        {
            "player_id": "P002",
            "nickname": "Анна Маскарад",
            "games_played": 38,
            "rating": 1720.0,
            "status": "Мастер",
            "rank_position": 2,
            "wins": 22,
            "survived": 30,
            "city_wins": 15,
            "mafia_wins": 7,
        },
        {
            "player_id": "P003",
            "nickname": "Дмитрий Коза",
            "games_played": 25,
            "rating": 1540.0,
            "status": "Опытный",
            "rank_position": 3,
            "wins": 14,
            "survived": 20,
            "city_wins": 10,
            "mafia_wins": 4,
        },
        {
            "player_id": "P004",
            "nickname": "Мария Тень",
            "games_played": 15,
            "rating": 1200.0,
            "status": "Новичок",
            "rank_position": 4,
            "wins": 7,
            "survived": 11,
            "city_wins": 5,
            "mafia_wins": 2,
        },
        {
            "player_id": "P005",
            "nickname": "Игорь Детектив",
            "games_played": 10,
            "rating": 980.0,
            "status": "Новичок",
            "rank_position": 5,
            "wins": 4,
            "survived": 8,
            "city_wins": 3,
            "mafia_wins": 1,
        },
    ]

    for player_data in test_players:
        await upsert_player(player_data)
        print(f"  ✅ Добавлен игрок: {player_data['nickname']} ({player_data['player_id']})")

    print("\n✅ Тестовые данные добавлены!")
    print("\n📋 Что делать дальше:")
    print("1. Запусти бота: python app/main.py")
    print("2. Напиши боту /start в Telegram")
    print("3. Попроси администратора привязать тебя к игроку (кнопка '🔗 Привязать игрока')")
    print("   Твой Telegram ID узнай у @userinfobot")
    print(f"   player_id игрока из списка выше (P001, P002, ...)")


if __name__ == "__main__":
    asyncio.run(seed())
