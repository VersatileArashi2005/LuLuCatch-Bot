# db.py - Fully Async Version
import os
import asyncpg
from datetime import datetime
from commands.utils import rarity_to_text

DB_HOST = os.environ.get("PGHOST")
DB_PORT = int(os.environ.get("PGPORT", 5432))
DB_NAME = os.environ.get("PGDATABASE")
DB_USER = os.environ.get("PGUSER")
DB_PASS = os.environ.get("PGPASSWORD")


async def get_pool():
    """
    Create a connection pool.
    """
    return await asyncpg.create_pool(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
    )


# ----------------------------
# Users
# ----------------------------
async def ensure_user(pool, user_id: int, first_name: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, first_name)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE
            SET first_name = EXCLUDED.first_name
        """, user_id, first_name)


async def get_user_by_id(pool, user_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)
        return dict(row) if row else None


# ----------------------------
# Cards
# ----------------------------
async def add_card(pool, anime, character, rarity, file_id, uploader_user_id=None):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO cards (anime, character, rarity, file_id, uploader_user_id)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
        """, anime, character, rarity, file_id, uploader_user_id)
        return row['id']


async def get_card_by_id(pool, card_id):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM cards WHERE id=$1", card_id)
        return dict(row) if row else None


async def get_all_cards(pool):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM cards")
        return [dict(r) for r in rows]


async def update_card(pool, card_id, field, value):
    allowed_fields = ['anime', 'character', 'rarity', 'file_id']
    if field not in allowed_fields:
        raise ValueError("Invalid field")
    async with pool.acquire() as conn:
        query = f"UPDATE cards SET {field}=$1 WHERE id=$2"
        await conn.execute(query, value, card_id)


async def delete_card(pool, card_id):
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM user_cards WHERE card_id=$1", card_id)
        await conn.execute("DELETE FROM active_drops WHERE card_id=$1", card_id)
        await conn.execute("DELETE FROM cards WHERE id=$1", card_id)


async def search_cards_by_text(pool, query):
    q = f"%{query.lower()}%"
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, anime, character, rarity, file_id FROM cards WHERE LOWER(character) LIKE $1 OR LOWER(anime) LIKE $2",
            q, q
        )
        return [dict(r) for r in rows]


async def get_card_owners(pool, card_id, limit=5):
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT u.user_id, u.first_name, uc.quantity
            FROM user_cards uc
            JOIN users u ON u.user_id = uc.user_id
            WHERE uc.card_id=$1
            ORDER BY uc.quantity DESC
            LIMIT $2
        """, card_id, limit)
        return [dict(r) for r in rows]


# ----------------------------
# Catch system (daily)
# ----------------------------
async def get_today_catch(pool, user_id, update=False):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT last_catch FROM users WHERE user_id=$1", user_id)
        today = datetime.utcnow().date()

        if not row or not row['last_catch']:
            if update:
                await conn.execute("UPDATE users SET last_catch=$1 WHERE user_id=$2", datetime.utcnow(), user_id)
            return False

        last = row['last_catch']
        if isinstance(last, str):
            last = datetime.fromisoformat(last)

        if last.date() == today:
            return True
        else:
            if update:
                await conn.execute("UPDATE users SET last_catch=$1 WHERE user_id=$2", datetime.utcnow(), user_id)
            return False


# ----------------------------
# User Cards / Inventory
# ----------------------------
async def give_card_to_user(pool, user_id, card_id, qty=1):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id, quantity FROM user_cards WHERE user_id=$1 AND card_id=$2", user_id, card_id)
        if row:
            await conn.execute("UPDATE user_cards SET quantity=quantity+$1 WHERE id=$2", qty, row['id'])
        else:
            await conn.execute("INSERT INTO user_cards (user_id, card_id, quantity) VALUES ($1, $2, $3)", user_id, card_id, qty)


async def add_card_to_user(pool, user_id, card_id):
    await give_card_to_user(pool, user_id, card_id, qty=1)
    await get_today_catch(pool, user_id, update=True)


async def get_user_cards(pool, user_id):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, card_id, quantity FROM user_cards WHERE user_id=$1", user_id)
        return [{"card_id": r["card_id"], "quantity": r["quantity"]} for r in rows]


async def update_user_cards(pool, user_id, cards_list):
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM user_cards WHERE user_id=$1", user_id)
            for c in cards_list:
                await conn.execute(
                    "INSERT INTO user_cards (user_id, card_id, quantity) VALUES ($1, $2, $3)",
                    user_id, c['card_id'], c['quantity']
                )


async def update_last_catch(pool, user_id, timestamp):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET last_catch=$1 WHERE user_id=$2", timestamp, user_id)


# ----------------------------
# Groups
# ----------------------------
async def register_group(pool, chat_id, title):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO groups (chat_id, title)
            VALUES ($1, $2)
            ON CONFLICT (chat_id) DO UPDATE
            SET title = EXCLUDED.title
        """, chat_id, title)


async def get_all_groups(pool):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT chat_id FROM groups")
        return [r['chat_id'] for r in rows]


# ----------------------------
# Database Initialization
# ----------------------------
async def init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                first_name TEXT,
                role TEXT DEFAULT 'user',
                last_catch TIMESTAMP
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS cards (
                id SERIAL PRIMARY KEY,
                anime TEXT NOT NULL,
                character TEXT NOT NULL,
                rarity INT NOT NULL,
                file_id TEXT NOT NULL,
                uploader_user_id BIGINT REFERENCES users(user_id)
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_cards (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(user_id),
                card_id INT NOT NULL REFERENCES cards(id) DEFERRABLE INITIALLY DEFERRED,
                quantity INT DEFAULT 1
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                chat_id BIGINT PRIMARY KEY,
                title TEXT
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS active_drops (
                chat_id BIGINT NOT NULL,
                card_id INT NOT NULL REFERENCES cards(id),
                claimed_by BIGINT REFERENCES users(user_id),
                PRIMARY KEY (chat_id, card_id)
            );
        """)
        # Indexes
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_cards_uploader ON cards(uploader_user_id);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_usercards_user ON user_cards(user_id);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_active_drops_chat ON active_drops(chat_id);")