# app/database/models.py
import aiosqlite
from app.config import DATABASE_PATH


async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:

        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username    TEXT,
                full_name   TEXT,
                phone       TEXT,
                language    TEXT DEFAULT 'UA',
                is_admin    INTEGER DEFAULT 0,
                created_at       TEXT DEFAULT (datetime('now')),
                group_message_id INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS players (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id       TEXT UNIQUE NOT NULL,
                nickname        TEXT NOT NULL,
                linked_user_id  INTEGER,
                games_played    INTEGER DEFAULT 0,
                rating          REAL DEFAULT 0,
                status          TEXT DEFAULT 'Перехожий',
                rank_position   INTEGER DEFAULT 0,
                wins            INTEGER DEFAULT 0,
                survived        INTEGER DEFAULT 0,
                city_wins       INTEGER DEFAULT 0,
                mafia_wins      INTEGER DEFAULT 0,
                points_lose     INTEGER DEFAULT 0,
                points_survive  INTEGER DEFAULT 0,
                points_win      INTEGER DEFAULT 0,
                points_host     INTEGER DEFAULT 0,
                points_best     INTEGER DEFAULT 0,
                points_guess    INTEGER DEFAULT 0,
                points_total    INTEGER DEFAULT 0,
                fols            INTEGER DEFAULT 0,
                updated_at      TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (linked_user_id) REFERENCES users(id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS wallets (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id       INTEGER UNIQUE NOT NULL,
                balance         INTEGER DEFAULT 0,
                frozen_balance  INTEGER DEFAULT 0,
                updated_at      TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (player_id) REFERENCES players(id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id           INTEGER NOT NULL,
                type                TEXT NOT NULL,
                amount              INTEGER NOT NULL,
                comment             TEXT,
                created_by_user_id  INTEGER,
                created_at          TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (player_id) REFERENCES players(id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS bonus_types (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT NOT NULL,
                amount_min      INTEGER NOT NULL,
                amount_max      INTEGER NOT NULL,
                is_active       INTEGER DEFAULT 1
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS bets (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                creator_player_id   INTEGER NOT NULL,
                bet_type            TEXT NOT NULL,
                target_player_id    INTEGER,
                target_number       INTEGER,
                side_color          TEXT,
                amount              INTEGER NOT NULL,
                status              TEXT DEFAULT 'pending_admin',
                result              TEXT,
                opponent_player_id  INTEGER,
                coefficient         REAL DEFAULT 2.0,
                created_by_admin    INTEGER DEFAULT 0,
                created_at          TEXT DEFAULT (datetime('now')),
                resolved_at         TEXT,
                FOREIGN KEY (creator_player_id)  REFERENCES players(id),
                FOREIGN KEY (target_player_id)   REFERENCES players(id),
                FOREIGN KEY (opponent_player_id) REFERENCES players(id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS spendings (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id       INTEGER NOT NULL,
                spend_type      TEXT NOT NULL,
                amount          INTEGER NOT NULL,
                target_number   INTEGER,
                comment         TEXT,
                status          TEXT DEFAULT 'pending',
                created_at      TEXT DEFAULT (datetime('now')),
                resolved_at     TEXT,
                FOREIGN KEY (player_id) REFERENCES players(id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS game_logs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                game_date       TEXT NOT NULL,
                game_number     INTEGER NOT NULL,
                winner_faction  TEXT,
                raw_log         TEXT,
                diary_generated INTEGER DEFAULT 0,
                diary_text      TEXT,
                synced_at       TEXT DEFAULT (datetime('now')),
                UNIQUE(game_date, game_number)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS game_player_stats (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                game_date      TEXT NOT NULL,
                game_number    INTEGER NOT NULL,
                nickname       TEXT NOT NULL,
                survived       INTEGER DEFAULT 0,
                won            INTEGER DEFAULT 0,
                winner_faction TEXT,
                UNIQUE(game_date, game_number, nickname)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS diary_entries (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                game_date   TEXT NOT NULL,
                game_number TEXT NOT NULL,
                title       TEXT NOT NULL,
                full_text   TEXT,
                created_at       TEXT DEFAULT (datetime('now')),
                group_message_id INTEGER DEFAULT 0
            )
        """)

        # Збори (оголошення ігор)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS gatherings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                game_date   TEXT NOT NULL,
                game_time   TEXT,
                location    TEXT,
                description TEXT,
                max_players INTEGER DEFAULT 13,
                status      TEXT DEFAULT 'active',
                created_by  INTEGER,
                created_at       TEXT DEFAULT (datetime('now')),
                group_message_id INTEGER DEFAULT 0
            )
        """)

        # Записи гравців на збори
        await db.execute("""
            CREATE TABLE IF NOT EXISTS gathering_signups (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                gathering_id INTEGER NOT NULL,
                player_id    INTEGER NOT NULL,
                signed_up_at TEXT DEFAULT (datetime('now')),
                UNIQUE(gathering_id, player_id),
                FOREIGN KEY (gathering_id) REFERENCES gatherings(id),
                FOREIGN KEY (player_id)    REFERENCES players(id)
            )
        """)

        await db.commit()

        await db.execute("""
            CREATE TABLE IF NOT EXISTS pending_payouts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id   INTEGER NOT NULL,
                amount      INTEGER NOT NULL,
                comment     TEXT,
                created_by  INTEGER,
                created_at  TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (player_id) REFERENCES players(id)
            )
        """)

        # ── Автоматичні міграції ─────────────────────────────
        # Додаємо нові колонки якщо їх ще немає (без видалення бази)
        migrations = [
            ("players", "fols",            "INTEGER DEFAULT 0"),
            ("players", "points_lose",     "INTEGER DEFAULT 0"),
            ("players", "points_survive",  "INTEGER DEFAULT 0"),
            ("players", "points_win",      "INTEGER DEFAULT 0"),
            ("players", "points_host",     "INTEGER DEFAULT 0"),
            ("players", "points_best",     "INTEGER DEFAULT 0"),
            ("players", "points_guess",    "INTEGER DEFAULT 0"),
            ("players", "points_total",    "INTEGER DEFAULT 0"),
            ("users",   "language",        "TEXT DEFAULT 'UA'"),
            ("gatherings", "group_message_id", "INTEGER DEFAULT 0"),
            ("game_player_stats", "winner_faction", "TEXT"),
        ]
        for table, col, col_def in migrations:
            try:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
                await db.commit()
            except Exception:
                pass  # Колонка вже існує — ігноруємо

        cur = await db.execute("SELECT COUNT(*) FROM bonus_types")
        if (await cur.fetchone())[0] == 0:
            bonuses = [
                ("Краща прощальна промова",  1, 1),
                ("Акторська гра",            1, 1),
                ("Від ГМ'а",                 1, 1),
                ("Кращий гравець",           1, 1),
                ("Вгадав 2 ролі при смерті", 1, 1),
                ("Вгадав 3 ролі при смерті", 2, 2),
                ("Привів друга",             2, 2),
                ("Сторіс з рекламою Клубу",  2, 2),
                ("Пост з рекламою Клубу",    3, 3),
                ("Новачок",                  3, 3),
                ("День Народження",          3, 3),
            ]
            await db.executemany(
                "INSERT INTO bonus_types (name,amount_min,amount_max) VALUES (?,?,?)",
                bonuses
            )
            await db.commit()
