import psycopg2
from psycopg2.extras import RealDictCursor
import os

DB_HOST = os.environ.get("PGHOST")
DB_PORT = os.environ.get("PGPORT", 5432)
DB_NAME = os.environ.get("PGDATABASE")
DB_USER = os.environ.get("PGUSER")
DB_PASS = os.environ.get("PGPASSWORD")


def get_conn():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        cursor_factory=RealDictCursor
    )


def init_db():
    """
    Safe migration-style init: create tables if not exists.
    Matches the schema you specified.
    """
    with get_conn() as conn:
        cur = conn.cursor()

        # users table (use user_id as Telegram ID)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            first_name TEXT,
            role TEXT DEFAULT 'user',
            last_catch TEXT
        );
        """)

        # user_cards (inventory)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS user_cards (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(user_id),
            card_id INT NOT NULL REFERENCES cards(id) DEFERRABLE INITIALLY DEFERRED,
            quantity INT DEFAULT 1
        );
        """)  # Note: cards table may be created later, but REF handles it via deferred constraint

        # groups
        cur.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            chat_id BIGINT PRIMARY KEY,
            title TEXT
        );
        """)

        # chat_stats
        cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_stats (
            chat_id BIGINT PRIMARY KEY,
            message_count BIGINT DEFAULT 0
        );
        """)

        # cards table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            id SERIAL PRIMARY KEY,
            anime TEXT NOT NULL,
            character TEXT NOT NULL,
            rarity INT NOT NULL,
            file_id TEXT NOT NULL,
            uploader_user_id BIGINT REFERENCES users(user_id)
        );
        """)

        # active_drops
        cur.execute("""
        CREATE TABLE IF NOT EXISTS active_drops (
            chat_id BIGINT NOT NULL,
            card_id INT NOT NULL REFERENCES cards(id),
            claimed_by BIGINT REFERENCES users(user_id),
            PRIMARY KEY (chat_id, card_id)
        );
        """)

        # indexes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cards_uploader ON cards(uploader_user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_usercards_user ON user_cards(user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_active_drops_chat ON active_drops(chat_id);")

        conn.commit()


def ensure_user(user_id, first_name):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (user_id, first_name)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE
            SET first_name = EXCLUDED.first_name
        """, (user_id, first_name))
        conn.commit()


def get_user_by_id(user_id):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
        return cur.fetchone()


def register_group(chat_id, title):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO groups (chat_id, title)
            VALUES (%s, %s)
            ON CONFLICT (chat_id) DO UPDATE
            SET title = EXCLUDED.title
        """, (chat_id, title))
        conn.commit()


def add_card(anime, character, rarity, file_id, uploader_user_id=None):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO cards (anime, character, rarity, file_id, uploader_user_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (anime, character, rarity, file_id, uploader_user_id))
        row = cur.fetchone()
        conn.commit()
        return row['id']


def give_card_to_user(user_id, card_id, qty=1):
    """Add card to user's inventory (user_cards). If existing, increment quantity."""
    with get_conn() as conn:
        cur = conn.cursor()
        # check existing
        cur.execute("SELECT id, quantity FROM user_cards WHERE user_id=%s AND card_id=%s", (user_id, card_id))
        r = cur.fetchone()
        if r:
            cur.execute("UPDATE user_cards SET quantity = quantity + %s WHERE id=%s", (qty, r['id']))
        else:
            cur.execute("INSERT INTO user_cards (user_id, card_id, quantity) VALUES (%s, %s, %s)", (user_id, card_id, qty))
        conn.commit()


def get_all_groups():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT chat_id FROM groups")
        return [r['chat_id'] for r in cur.fetchall()]


def get_card_by_id(card_id):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM cards WHERE id=%s", (card_id,))
        return cur.fetchone()


def get_user_cards(user_id):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT uc.id, uc.card_id, uc.quantity, c.anime, c.character, c.rarity, c.file_id
            FROM user_cards uc
            JOIN cards c ON c.id = uc.card_id
            WHERE uc.user_id = %s
        """, (user_id,))
        return cur.fetchall()
