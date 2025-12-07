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
            user_id BIGINT PRIMARY KEY,
            first_name TEXT,
            role TEXT DEFAULT 'user',
            last_catch TEXT
        );
        """)
        
        # groups table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            chat_id BIGINT PRIMARY KEY,
            title TEXT
        );
        """)
        
        # cards table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            anime TEXT NOT NULL,
            rarity INT NOT NULL,
            file_id TEXT NOT NULL
        );
        """)

        # add uploader_user_id column safely
        try:
            cur.execute("""
            ALTER TABLE cards
            ADD COLUMN uploader_user_id BIGINT;
            """)
        except psycopg2.errors.DuplicateColumn:
            pass  # column already exists

        # add foreign key referencing users.user_id
        try:
            cur.execute("""
            ALTER TABLE cards
            ADD CONSTRAINT fk_uploader FOREIGN KEY (uploader_user_id) REFERENCES users(user_id);
            """)
        except psycopg2.errors.DuplicateObject:
            pass  # constraint already exists
        except psycopg2.errors.UndefinedColumn:
            pass  # users.user_id doesn't exist yet

        # create index if not exists
        try:
            cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_cards_uploader ON cards(uploader_user_id);
            """)
        except Exception:
            pass

        conn.commit()

# =========================
# Ensure user exists in DB
# =========================
def ensure_user(user_id, first_name):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (user_id, first_name)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """, (user_id, first_name))
        conn.commit()

# =========================
# Get user by user_id
# =========================
def get_user_by_id(user_id):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
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
def add_card(name, anime, rarity, file_id, uploader_user_id=None):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO cards (name, anime, rarity, file_id, uploader_user_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (name, anime, rarity, file_id, uploader_user_id))
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
