# app/database/queries.py
import aiosqlite
from typing import Optional, List
from app.config import DATABASE_PATH, ADMIN_IDS


# ══════════════════════════════════════════════
# КОРИСТУВАЧІ
# ══════════════════════════════════════════════

async def get_or_create_user(telegram_id: int, username: str, full_name: str) -> dict:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
        row = await cur.fetchone()
        if row:
            return dict(row)
        await db.execute(
            "INSERT INTO users (telegram_id,username,full_name) VALUES (?,?,?)",
            (telegram_id, username, full_name)
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
        return dict(await cur.fetchone())


async def get_user_by_telegram_id(telegram_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def is_admin(telegram_id: int) -> bool:
    if telegram_id in ADMIN_IDS:
        return True
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "SELECT is_admin FROM users WHERE telegram_id=?", (telegram_id,)
        )
        row = await cur.fetchone()
        return bool(row and row[0])


async def save_user_phone(telegram_id: int, phone: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE users SET phone=? WHERE telegram_id=?", (phone, telegram_id)
        )
        await db.commit()


# ══════════════════════════════════════════════
# ГРАВЦІ
# ══════════════════════════════════════════════

async def get_player_by_linked_user(telegram_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT p.* FROM players p
            JOIN users u ON p.linked_user_id=u.id
            WHERE u.telegram_id=?
        """, (telegram_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_player_by_id(player_db_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM players WHERE id=?", (player_db_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_player_by_player_id(player_id: str) -> Optional[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM players WHERE player_id=?", (player_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_player_by_nickname(nickname: str) -> Optional[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM players WHERE nickname LIKE ? LIMIT 1",
            (f"%{nickname}%",)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def search_players(query: str) -> List[dict]:
    """Пошук гравців за частиною нікнейму — повертає всі збіги."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Шукаємо по кожному слову в запиті окремо
        words = query.strip().split()
        if not words:
            return []
        # Основний пошук — contains
        cur = await db.execute(
            "SELECT * FROM players WHERE nickname LIKE ? ORDER BY nickname COLLATE NOCASE LIMIT 30",
            (f"%{query}%",)
        )
        rows = await cur.fetchall()
        results = [dict(r) for r in rows]
        # Якщо нічого не знайшло — пробуємо по першому слову
        if not results and words:
            cur2 = await db.execute(
                "SELECT * FROM players WHERE nickname LIKE ? ORDER BY nickname COLLATE NOCASE LIMIT 30",
                (f"%{words[0]}%",)
            )
            rows2 = await cur2.fetchall()
            results = [dict(r) for r in rows2]
        return results


async def get_all_players_sorted() -> List[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM players ORDER BY nickname COLLATE NOCASE ASC"
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_top_players(limit: int = 10) -> List[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM players ORDER BY rating DESC LIMIT ?", (limit,)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def link_player_to_user(player_db_id: int, user_db_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE players SET linked_user_id=? WHERE id=?", (user_db_id, player_db_id)
        )
        await db.commit()


async def create_player_auto(nickname: str, telegram_id: int,
                              username: str, full_name: str) -> dict:
    """
    Автоматична реєстрація гравця.
    Логіка:
    1. Шукаємо в players по нікнейму (з таблиці MAFIAGAME Players)
       — якщо знайдено, прив'язуємо до цього Telegram і повертаємо
    2. Якщо не знайдено — створюємо нового з player_id = TG_{telegram_id}
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Отримуємо user_db_id
        cur = await db.execute(
            "SELECT id FROM users WHERE telegram_id=?", (telegram_id,)
        )
        user_row   = await cur.fetchone()
        user_db_id = user_row[0] if user_row else None

        # 1. Шукаємо гравця по нікнейму (COLLATE NOCASE — без урахування регістру)
        cur = await db.execute(
            "SELECT * FROM players WHERE nickname = ? COLLATE NOCASE LIMIT 1",
            (nickname,)
        )
        existing_by_nick = await cur.fetchone()

        if existing_by_nick:
            p = dict(existing_by_nick)
            # Прив'язуємо до Telegram якщо ще не прив'язаний
            if not p.get("linked_user_id") and user_db_id:
                await db.execute(
                    "UPDATE players SET linked_user_id=? WHERE id=?",
                    (user_db_id, p["id"])
                )
                await db.commit()
                # Оновлюємо гаманець якщо немає
                await db.execute(
                    "INSERT OR IGNORE INTO wallets (player_id,balance,frozen_balance) VALUES (?,0,0)",
                    (p["id"],)
                )
                await db.commit()
            return p

        # 2. Перевіряємо по player_id = TG_{telegram_id}
        player_id = f"TG_{telegram_id}"
        cur = await db.execute(
            "SELECT * FROM players WHERE player_id=?", (player_id,)
        )
        existing = await cur.fetchone()
        if existing:
            return dict(existing)

        # 3. Створюємо нового гравця
        await db.execute("""
            INSERT INTO players (player_id, nickname, linked_user_id)
            VALUES (?,?,?)
        """, (player_id, nickname, user_db_id))

        cur2  = await db.execute(
            "SELECT id FROM players WHERE player_id=?", (player_id,)
        )
        p_row = await cur2.fetchone()
        p_id  = p_row[0]

        await db.execute(
            "INSERT OR IGNORE INTO wallets (player_id,balance,frozen_balance) VALUES (?,0,0)",
            (p_id,)
        )
        await db.commit()

        cur3 = await db.execute("SELECT * FROM players WHERE id=?", (p_id,))
        return dict(await cur3.fetchone())


async def upsert_player(data: dict):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO players
                (player_id,nickname,games_played,rating,status,
                 rank_position,wins,survived,city_wins,mafia_wins,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))
            ON CONFLICT(player_id) DO UPDATE SET
                nickname=excluded.nickname,
                games_played=excluded.games_played,
                rating=excluded.rating,
                status=excluded.status,
                rank_position=excluded.rank_position,
                wins=excluded.wins,
                survived=excluded.survived,
                city_wins=excluded.city_wins,
                mafia_wins=excluded.mafia_wins,
                updated_at=datetime('now')
        """, (
            data["player_id"], data["nickname"],
            data.get("games_played",0), data.get("rating",0),
            data.get("status","Новачок"), data.get("rank_position",0),
            data.get("wins",0), data.get("survived",0),
            data.get("city_wins",0), data.get("mafia_wins",0),
        ))
        cur = await db.execute(
            "SELECT id FROM players WHERE player_id=?", (data["player_id"],)
        )
        row = await cur.fetchone()
        if row:
            await db.execute(
                "INSERT OR IGNORE INTO wallets (player_id,balance,frozen_balance) VALUES (?,0,0)",
                (row[0],)
            )
        await db.commit()


# ══════════════════════════════════════════════
# ГАМАНЦІ
# ══════════════════════════════════════════════

async def get_wallet(player_db_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM wallets WHERE player_id=?", (player_db_id,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def change_balance(player_db_id: int, amount: int,
                         op_type: str, comment: str, done_by: int = 0):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "SELECT balance FROM wallets WHERE player_id=?", (player_db_id,)
        )
        row = await cur.fetchone()
        if not row:
            await db.execute(
                "INSERT INTO wallets (player_id,balance) VALUES (?,?)",
                (player_db_id, max(0, amount))
            )
        else:
            new_bal = row[0] + amount
            if new_bal < 0:
                raise ValueError(f"Недостатньо шепот на балансі")
            await db.execute(
                "UPDATE wallets SET balance=?,updated_at=datetime('now') WHERE player_id=?",
                (new_bal, player_db_id)
            )
        await db.execute(
            "INSERT INTO transactions (player_id,type,amount,comment,created_by_user_id) "
            "VALUES (?,?,?,?,?)",
            (player_db_id, op_type, abs(amount), comment, done_by)
        )
        await db.commit()
    # Фоновий запис в Google Sheets "История Операций"
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db2:
            nc = await db2.execute("SELECT nickname FROM players WHERE id=?", (player_db_id,))
            nrow = await nc.fetchone()
            nickname = nrow[0] if nrow else str(player_db_id)
        import asyncio
        from app.services.logs_service import write_operation_to_history
        asyncio.ensure_future(
            write_operation_to_history(nickname, op_type, abs(amount), comment)
        )
    except Exception:
        pass


async def freeze_chips(player_db_id: int, amount: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "SELECT balance,frozen_balance FROM wallets WHERE player_id=?", (player_db_id,)
        )
        row = await cur.fetchone()
        if not row:
            raise ValueError("Гаманець не знайдено")
        bal, frozen = row
        if (bal - frozen) < amount:
            raise ValueError(f"Недостатньо доступних шепот")
        await db.execute(
            "UPDATE wallets SET frozen_balance=frozen_balance+? WHERE player_id=?",
            (amount, player_db_id)
        )
        await db.commit()


async def unfreeze_chips(player_db_id: int, amount: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE wallets SET frozen_balance=MAX(0,frozen_balance-?) WHERE player_id=?",
            (amount, player_db_id)
        )
        await db.commit()


# ══════════════════════════════════════════════
# ТРАНЗАКЦІЇ
# ══════════════════════════════════════════════

async def get_transactions(player_db_id: int,
                           limit: int = 5,
                           offset: int = 0) -> List[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT * FROM transactions
            WHERE player_id=?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (player_db_id, limit, offset))
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def count_transactions(player_db_id: int) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM transactions WHERE player_id=?", (player_db_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else 0


# ══════════════════════════════════════════════
# БОНУСИ
# ══════════════════════════════════════════════

async def get_active_bonus_types() -> List[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM bonus_types WHERE is_active=1 ORDER BY amount_min ASC"
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_bonus_type(bonus_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM bonus_types WHERE id=?", (bonus_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


# ══════════════════════════════════════════════
# СТАВКИ
# ══════════════════════════════════════════════

async def create_bet(creator_id: int, bet_type: str, amount: int,
                     target_player_id: Optional[int] = None,
                     target_number: Optional[int] = None,
                     side_color: Optional[str] = None,
                     coefficient: float = 2.0,
                     created_by_admin: int = 0) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("""
            INSERT INTO bets
                (creator_player_id,bet_type,amount,target_player_id,
                 target_number,side_color,coefficient,status,created_by_admin)
            VALUES (?,?,?,?,?,?,?,'pending_admin',?)
        """, (creator_id, bet_type, amount, target_player_id,
              target_number, side_color, coefficient, created_by_admin))
        await db.commit()
        return cur.lastrowid


async def get_active_bets() -> List[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT b.*, p1.nickname AS creator_nickname
            FROM bets b
            JOIN players p1 ON b.creator_player_id=p1.id
            WHERE b.status IN ('pending_admin','open','duel')
            ORDER BY b.created_at DESC
        """)
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_open_redness_bets() -> List[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT b.*, p.nickname AS creator_nickname
            FROM bets b JOIN players p ON b.creator_player_id=p.id
            WHERE b.bet_type='redness' AND b.status='open'
            ORDER BY b.created_at DESC
        """)
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_bet(bet_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM bets WHERE id=?", (bet_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def update_bet_status(bet_id: int, status: str,
                             result: Optional[str] = None,
                             opponent_id: Optional[int] = None):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if result:
            await db.execute(
                "UPDATE bets SET status=?,result=?,resolved_at=datetime('now') WHERE id=?",
                (status, result, bet_id)
            )
        elif opponent_id:
            await db.execute(
                "UPDATE bets SET status=?,opponent_player_id=? WHERE id=?",
                (status, opponent_id, bet_id)
            )
        else:
            await db.execute("UPDATE bets SET status=? WHERE id=?", (status, bet_id))
        await db.commit()


async def get_player_bets(player_db_id: int) -> List[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT * FROM bets WHERE creator_player_id=?
            ORDER BY created_at DESC LIMIT 20
        """, (player_db_id,))
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


# ══════════════════════════════════════════════
# ВИТРАТИ
# ══════════════════════════════════════════════

async def create_spending(player_id: int, spend_type: str, amount: int,
                          target_number: Optional[int] = None,
                          comment: str = "") -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("""
            INSERT INTO spendings
                (player_id,spend_type,amount,target_number,comment,status)
            VALUES (?,?,?,?,?,'pending')
        """, (player_id, spend_type, amount, target_number, comment))
        await db.commit()
        return cur.lastrowid


async def get_pending_spendings() -> List[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT s.*, p.nickname AS player_nickname
            FROM spendings s JOIN players p ON s.player_id=p.id
            WHERE s.status='pending'
            ORDER BY s.created_at ASC
        """)
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_spending(spending_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM spendings WHERE id=?", (spending_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def resolve_spending(spending_id: int, status: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE spendings SET status=?,resolved_at=datetime('now') WHERE id=?",
            (status, spending_id)
        )
        await db.commit()


# ══════════════════════════════════════════════
# ЩОДЕННИК
# ══════════════════════════════════════════════

async def get_diary_dates() -> List[str]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "SELECT DISTINCT game_date FROM diary_entries ORDER BY game_date DESC"
        )
        rows = await cur.fetchall()
        return [r[0] for r in rows]


async def get_diary_entries_by_date(game_date: str) -> List[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM diary_entries WHERE game_date=? ORDER BY game_number ASC",
            (game_date,)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_diary_entry(entry_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM diary_entries WHERE id=?", (entry_id,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def upsert_diary_entry(game_date: str, game_number: str,
                              title: str, full_text: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Перевіряємо чи вже є такий запис
        cur = await db.execute(
            "SELECT id FROM diary_entries WHERE game_date=? AND game_number=?",
            (game_date, game_number)
        )
        row = await cur.fetchone()
        if row:
            await db.execute(
                "UPDATE diary_entries SET title=?,full_text=? WHERE id=?",
                (title, full_text, row[0])
            )
        else:
            await db.execute(
                "INSERT INTO diary_entries (game_date,game_number,title,full_text) VALUES (?,?,?,?)",
                (game_date, game_number, title, full_text)
            )
        await db.commit()


# ══════════════════════════════════════════════
# ЛОГИ ПАРТІЙ
# ══════════════════════════════════════════════

async def upsert_game_log(game_date: str, game_number: int,
                           winner_faction: str, raw_log: str):
    """Зберігає або оновлює лог партії."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO game_logs (game_date, game_number, winner_faction, raw_log, synced_at)
            VALUES (?,?,?,?,datetime('now'))
            ON CONFLICT(game_date, game_number) DO UPDATE SET
                winner_faction = excluded.winner_faction,
                raw_log        = excluded.raw_log,
                synced_at      = datetime('now')
        """, (game_date, game_number, winner_faction, raw_log))
        await db.commit()


async def get_game_logs_without_diary(limit: int = 20) -> List[dict]:
    """Партії для яких ще не згенеровано щоденник."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT * FROM game_logs
            WHERE diary_generated = 0
            ORDER BY game_date DESC, game_number DESC
            LIMIT ?
        """, (limit,))
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_all_game_logs(limit: int = 50) -> List[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT * FROM game_logs
            ORDER BY game_date DESC, game_number DESC
            LIMIT ?
        """, (limit,))
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_game_log(log_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM game_logs WHERE id=?", (log_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def mark_diary_generated(log_id: int, diary_text: str):
    """Позначає лог як оброблений і зберігає згенерований текст."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            UPDATE game_logs SET diary_generated=1, diary_text=?
            WHERE id=?
        """, (diary_text, log_id))
        await db.commit()


async def update_player_points(nickname: str, points_data: dict):
    """Оновлює бали і статистику гравця з таблиці MAFIAGAME."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            UPDATE players SET
                games_played   = ?,
                points_lose    = ?,
                points_survive = ?,
                points_win     = ?,
                points_host    = ?,
                points_best    = ?,
                points_guess   = ?,
                points_total   = ?,
                fols           = ?,
                updated_at     = datetime('now')
            WHERE nickname = ? COLLATE NOCASE
        """, (
            points_data.get("games", 0),
            points_data.get("lose", 0),
            points_data.get("survive", 0),
            points_data.get("win", 0),
            points_data.get("host", 0),
            points_data.get("best", 0),
            points_data.get("guess", 0),
            points_data.get("total", 0),
            points_data.get("fols", 0),
            nickname,
        ))
        await db.commit()


# ══════════════════════════════════════════════
# МОВА КОРИСТУВАЧА
# ══════════════════════════════════════════════

async def get_user_language(telegram_id: int) -> str:
    """Повертає мову користувача: 'UA' або 'RU'. Default = 'UA'."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "SELECT language FROM users WHERE telegram_id=?", (telegram_id,)
        )
        row = await cur.fetchone()
        if row and row[0]:
            return row[0]
        return "UA"


async def set_user_language(telegram_id: int, lang: str):
    """Зберігає мову користувача ('UA' або 'RU')."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE users SET language=? WHERE telegram_id=?", (lang, telegram_id)
        )
        await db.commit()


# ══════════════════════════════════════════════
# ЗБОРИ ГРИ
# ══════════════════════════════════════════════

# ══════════════════════════════════════════════
# ЗБОРИ
# ══════════════════════════════════════════════

async def create_gathering(game_date: str, game_time: str,
                            location: str, description: str,
                            created_by: int) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("""
            INSERT INTO gatherings (game_date,game_time,location,description,created_by)
            VALUES (?,?,?,?,?)
        """, (game_date, game_time, location, description, created_by))
        await db.commit()
        return cur.lastrowid


async def get_active_gatherings() -> List[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT g.*,
                   (SELECT COUNT(*) FROM gathering_signups s WHERE s.gathering_id=g.id) AS signed_count
            FROM gatherings g
            WHERE g.status='active'
            ORDER BY g.game_date ASC
        """)
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_gathering(gathering_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT g.*,
                   (SELECT COUNT(*) FROM gathering_signups s WHERE s.gathering_id=g.id) AS signed_count
            FROM gatherings g WHERE g.id=?
        """, (gathering_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def cancel_gathering(gathering_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE gatherings SET status='cancelled' WHERE id=?", (gathering_id,)
        )
        await db.commit()


async def signup_gathering(gathering_id: int, player_id: int) -> bool:
    """Записує гравця на гру. Повертає True якщо успішно, False якщо вже записаний."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO gathering_signups (gathering_id,player_id) VALUES (?,?)",
                (gathering_id, player_id)
            )
            await db.commit()
            return True
        except Exception:
            return False


async def cancel_signup(gathering_id: int, player_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "DELETE FROM gathering_signups WHERE gathering_id=? AND player_id=?",
            (gathering_id, player_id)
        )
        await db.commit()


async def get_gathering_signups(gathering_id: int) -> List[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT p.nickname, s.signed_up_at
            FROM gathering_signups s
            JOIN players p ON s.player_id=p.id
            WHERE s.gathering_id=?
            ORDER BY s.signed_up_at ASC
        """, (gathering_id,))
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_all_linked_telegram_ids() -> List[int]:
    """Всі telegram_id гравців що прив'язані (для масових розсилок)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("""
            SELECT u.telegram_id FROM users u
            JOIN players p ON p.linked_user_id=u.id
        """)
        rows = await cur.fetchall()
        return [r[0] for r in rows]


async def save_gathering_message_id(gathering_id: int, message_id: int):
    """Зберігає ID повідомлення збору в групі."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE gatherings SET group_message_id=? WHERE id=?",
            (message_id, gathering_id)
        )
        await db.commit()


async def get_hold_bets_exist() -> bool:
    """Перевіряє чи є ставки зі статусом hold (очікують виплати)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM bets WHERE status='hold'"
        )
        row = await cur.fetchone()
        return row[0] > 0


async def get_all_hold_bets() -> List[dict]:
    """Повертає всі ставки зі статусом hold."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM bets WHERE status='hold' ORDER BY created_at ASC"
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


# ══════════════════════════════════════════════
# ВІДКЛАДЕНІ ВИПЛАТИ (pending_payouts)
# ══════════════════════════════════════════════

async def add_pending_payout(player_id: int, amount: int,
                              comment: str, created_by: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO pending_payouts (player_id,amount,comment,created_by) VALUES (?,?,?,?)",
            (player_id, amount, comment, created_by)
        )
        await db.commit()


async def get_all_pending_payouts() -> List[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT pp.*, p.nickname FROM pending_payouts pp
            JOIN players p ON p.id=pp.player_id
            ORDER BY pp.created_at ASC
        """)
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def clear_pending_payouts():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM pending_payouts")
        await db.commit()


async def has_pending_payouts() -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM pending_payouts")
        row = await cur.fetchone()
        return row[0] > 0


# ══════════════════════════════════════════════
# СТАТИСТИКА ГРАВЦІВ З ЛОГІВ (game_player_stats)
# ══════════════════════════════════════════════

async def upsert_game_player_stat(game_date: str, game_number: int, nickname: str,
                                   survived: int, won: int, winner_faction: str):
    """Зберігає або оновлює статистику гравця за окрему партію."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO game_player_stats
                (game_date, game_number, nickname, survived, won, winner_faction)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(game_date, game_number, nickname) DO UPDATE SET
                survived       = excluded.survived,
                won            = excluded.won,
                winner_faction = excluded.winner_faction
        """, (game_date, game_number, nickname, survived, won, winner_faction))
        await db.commit()


async def get_player_game_stats(nickname: str) -> dict:
    """Повертає агреговану статистику гравця з логів (4 сезон)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("""
            SELECT
                COUNT(*)                                                        AS games,
                SUM(survived)                                                   AS survived,
                SUM(CASE WHEN won=1 AND winner_faction='red'   THEN 1 ELSE 0 END) AS red_wins,
                SUM(CASE WHEN won=1 AND winner_faction='black' THEN 1 ELSE 0 END) AS black_wins,
                SUM(CASE WHEN won=1 AND winner_faction='grey'  THEN 1 ELSE 0 END) AS grey_wins,
                SUM(won)                                                        AS total_wins
            FROM game_player_stats
            WHERE nickname = ? COLLATE NOCASE
        """, (nickname,))
        row = await cur.fetchone()
        if row and row[0]:
            return {
                "games":      row[0] or 0,
                "survived":   row[1] or 0,
                "red_wins":   row[2] or 0,
                "black_wins": row[3] or 0,
                "grey_wins":  row[4] or 0,
                "total_wins": row[5] or 0,
            }
        return {"games": 0, "survived": 0, "red_wins": 0, "black_wins": 0,
                "grey_wins": 0, "total_wins": 0}
