import psycopg2
from psycopg2.extras import RealDictCursor
import os

# =========================
# Postgres connection from Railway env
# =========================
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

# =========================
# Initialize tables if not exists (safe migration)
# =========================
def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        
        # users table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id BIGINT PRIMARY KEY,
            first_name TEXT,
            role TEXT DEFAULT 'user'
        );
        """)
        
        # groups table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            chat_id BIGINT PRIMARY KEY,
            title TEXT
        );
        """)
        
        # cards table (without uploader_telegram_id first)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            anime TEXT NOT NULL,
            rarity INT NOT NULL,
            file_id TEXT NOT NULL
        );
        """)
        
        # add uploader_telegram_id column if not exists
        cur.execute("""
        ALTER TABLE cards
        ADD COLUMN IF NOT EXISTS uploader_telegram_id BIGINT REFERENCES users(telegram_id);
        """)
        
        # create index if not exists
        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_cards_uploader ON cards(uploader_telegram_id);
        """)
        
        conn.commit()

# =========================
# Ensure user exists in DB
# =========================
def ensure_user(telegram_id, first_name):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (telegram_id, first_name)
            VALUES (%s, %s)
            ON CONFLICT (telegram_id) DO NOTHING
        """, (telegram_id, first_name))
        conn.commit()

# =========================
# Get user by telegram_id
# =========================
def get_user_by_telegram(telegram_id):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE telegram_id=%s", (telegram_id,))
        return cur.fetchone()

# =========================
# Register group
# =========================
def register_group(chat_id, title):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO groups (chat_id, title)
            VALUES (%s, %s)
            ON CONFLICT (chat_id) DO NOTHING
        """, (chat_id, title))
        conn.commit()

# =========================
# Add card
# =========================
def add_card(name, anime, rarity, file_id, uploader_telegram_id=None):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO cards (name, anime, rarity, file_id, uploader_telegram_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (name, anime, rarity, file_id, uploader_telegram_id))
        card_id = cur.fetchone()['id']
        conn.commit()
        return card_id

# =========================
# Give card to user (optional inventory logic)
# =========================
def give_card_to_user(user_id, card_id):
    pass  # implement if needed

# =========================
# Get all registered groups
# =========================
def get_all_groups():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT chat_id FROM groups")
        return [r['chat_id'] for r in cur.fetchall()]

# =========================
# Get card by ID
# =========================
def get_card_by_id(card_id):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM cards WHERE id=%s", (card_id,))
        return cur.fetchone()
