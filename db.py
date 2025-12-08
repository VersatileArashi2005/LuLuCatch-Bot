import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime
from commands.utils import rarity_to_text

# ----------------------------
# Database Configuration
# ----------------------------
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


# ----------------------------
# Users
# ----------------------------
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


# ----------------------------
# Cards
# ----------------------------
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


def get_card_by_id(card_id):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM cards WHERE id=%s", (card_id,))
        return cur.fetchone()


def get_all_cards():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM cards")
        return cur.fetchall()


def update_card(card_id, field, value):
    """
    Safely update a card field.
    Allowed fields: anime, character, rarity, file_id
    """
    allowed_fields = ['anime', 'character', 'rarity', 'file_id']
    if field not in allowed_fields:
        raise ValueError("Invalid field")
    with get_conn() as conn:
        cur = conn.cursor()
        query = "UPDATE cards SET {}=%s WHERE id=%s".format(field)
        cur.execute(query, (value, card_id))
        conn.commit()


def delete_card(card_id):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM user_cards WHERE card_id=%s", (card_id,))
        cur.execute("DELETE FROM active_drops WHERE card_id=%s", (card_id,))
        cur.execute("DELETE FROM cards WHERE id=%s", (card_id,))
        conn.commit()


def search_cards_by_text(query):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, anime, character, rarity, file_id FROM cards WHERE LOWER(character) LIKE %s OR LOWER(anime) LIKE %s",
            (f"%{query.lower()}%", f"%{query.lower()}%")
        )
        return cur.fetchall()


def get_card_owners(card_id, limit=5):
    """
    Return list of owners with quantity for a card.
    [{'user_id':.., 'first_name':.., 'quantity':..}, ...]
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT u.user_id, u.first_name, uc.quantity
            FROM user_cards uc
            JOIN users u ON u.user_id = uc.user_id
            WHERE uc.card_id=%s
            ORDER BY uc.quantity DESC
            LIMIT %s
        """, (card_id, limit))
        return cur.fetchall()


# ----------------------------
# Catch system (daily)
# ----------------------------
def get_today_catch(user_id, update=False):
    """
    Return True if user has caught today, else False.
    If update=True and user hasn't caught today, update last_catch.
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT last_catch FROM users WHERE user_id=%s", (user_id,))
        row = cur.fetchone()
        today = datetime.utcnow().date()

        if not row or not row['last_catch']:
            if update:
                cur.execute("UPDATE users SET last_catch=%s WHERE user_id=%s",
                            (datetime.utcnow(), user_id))
                conn.commit()
            return False

        last = row['last_catch']
        if isinstance(last, str):
            last = datetime.fromisoformat(last)
        if last.date() == today:
            return True
        else:
            if update:
                cur.execute("UPDATE users SET last_catch=%s WHERE user_id=%s",
                            (datetime.utcnow(), user_id))
                conn.commit()
            return False


# ----------------------------
# User Cards / Inventory
# ----------------------------
def give_card_to_user(user_id, card_id, qty=1):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, quantity FROM user_cards WHERE user_id=%s AND card_id=%s", (user_id, card_id))
        r = cur.fetchone()
        if r:
            cur.execute("UPDATE user_cards SET quantity = quantity + %s WHERE id=%s", (qty, r['id']))
        else:
            cur.execute("INSERT INTO user_cards (user_id, card_id, quantity) VALUES (%s, %s, %s)", (user_id, card_id, qty))
        conn.commit()


def add_card_to_user(user_id, card_id):
    give_card_to_user(user_id, card_id, qty=1)
    get_today_catch(user_id, update=True)


def get_user_cards(user_id=None):
    with get_conn() as conn:
        cur = conn.cursor()
        if user_id is None:
            cur.execute("SELECT id, user_id, card_id, quantity FROM user_cards")
        else:
            cur.execute("SELECT id, card_id, quantity FROM user_cards WHERE user_id=%s", (user_id,))
        return cur.fetchall()


# ----------------------------
# Groups
# ----------------------------
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


def get_all_groups():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT chat_id FROM groups")
        return [r['chat_id'] for r in cur.fetchall()]


# ----------------------------
# Database Initialization
# ----------------------------
def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                first_name TEXT,
                role TEXT DEFAULT 'user',
                last_catch TIMESTAMP
            );
        """)
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_cards (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(user_id),
                card_id INT NOT NULL REFERENCES cards(id) DEFERRABLE INITIALLY DEFERRED,
                quantity INT DEFAULT 1
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                chat_id BIGINT PRIMARY KEY,
                title TEXT
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS active_drops (
                chat_id BIGINT NOT NULL,
                card_id INT NOT NULL REFERENCES cards(id),
                claimed_by BIGINT REFERENCES users(user_id),
                PRIMARY KEY (chat_id, card_id)
            );
        """)
        # Indexes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cards_uploader ON cards(uploader_user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_usercards_user ON user_cards(user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_active_drops_chat ON active_drops(chat_id);")
        conn.commit()