# db.py
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from config import PGHOST, PGDATABASE, PGUSER, PGPASSWORD

@contextmanager
def get_conn():
    conn = psycopg2.connect(host=PGHOST, database=PGDATABASE, user=PGUSER, password=PGPASSWORD)
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE,
            first_name TEXT,
            role TEXT DEFAULT 'user',
            last_catch TIMESTAMP
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            id SERIAL PRIMARY KEY,
            name TEXT,
            anime TEXT,
            rarity INTEGER,
            file_id TEXT,
            uploader_id BIGINT,
            created_at TIMESTAMP DEFAULT now()
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS user_cards (
            id SERIAL PRIMARY KEY,
            user_telegram_id BIGINT,
            card_id INTEGER REFERENCES cards(id),
            quantity INTEGER DEFAULT 1
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            chat_id BIGINT PRIMARY KEY,
            title TEXT
        );
        """)
        conn.commit()

# user helpers
def ensure_user(telegram_id, first_name):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (telegram_id, first_name) VALUES (%s, %s) ON CONFLICT (telegram_id) DO UPDATE SET first_name=EXCLUDED.first_name",
            (telegram_id, first_name)
        )
        conn.commit()

def get_user_by_telegram(telegram_id):
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM users WHERE telegram_id=%s", (telegram_id,))
        return cur.fetchone()

# card helpers
def add_card(name, anime, rarity, file_id, uploader_id):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO cards (name, anime, rarity, file_id, uploader_id) VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (name, anime, rarity, file_id, uploader_id)
        )
        card_id = cur.fetchone()[0]
        conn.commit()
        return card_id

def get_card_by_id(card_id):
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM cards WHERE id=%s", (card_id,))
        return cur.fetchone()

def give_card_to_user(user_telegram_id, card_id):
    with get_conn() as conn:
        cur = conn.cursor()
        # if already exists, increment quantity
        cur.execute("SELECT id, quantity FROM user_cards WHERE user_telegram_id=%s AND card_id=%s", (user_telegram_id, card_id))
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE user_cards SET quantity = quantity + 1 WHERE id=%s", (row[0],))
        else:
            cur.execute("INSERT INTO user_cards (user_telegram_id, card_id, quantity) VALUES (%s,%s,1)", (user_telegram_id, card_id))
        conn.commit()

def get_user_harem(user_telegram_id):
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT c.id AS card_id, c.name, c.anime, c.rarity, uc.quantity, c.file_id
            FROM user_cards uc
            JOIN cards c ON uc.card_id = c.id
            WHERE uc.user_telegram_id = %s
        """, (user_telegram_id,))
        return cur.fetchall()

# groups
def register_group(chat_id, title=None):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO groups (chat_id, title) VALUES (%s,%s) ON CONFLICT (chat_id) DO UPDATE SET title=EXCLUDED.title", (chat_id, title))
        conn.commit()

def get_all_groups():
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT chat_id, title FROM groups")
        return [r['chat_id'] for r in cur.fetchall()]
