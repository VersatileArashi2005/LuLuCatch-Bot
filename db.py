import psycopg2
from psycopg2.extras import RealDictCursor
import os
from commands.utils import rarity_to_text  # import utils helper

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
    with get_conn() as conn:
        cur = conn.cursor()
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


def get_all_cards():
    """Return all cards in DB."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM cards ORDER BY id ASC")
        return cur.fetchall()


def update_card(card_id, field, value):
    """Update a single field of a card."""
    if field not in ['anime', 'character', 'rarity', 'file_id']:
        raise ValueError("Invalid field")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE cards SET {field}=%s WHERE id=%s", (value, card_id))
        conn.commit()


def delete_card(card_id):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM user_cards WHERE card_id=%s", (card_id,))
        cur.execute("DELETE FROM active_drops WHERE card_id=%s", (card_id,))
        cur.execute("DELETE FROM cards WHERE id=%s", (card_id,))
        conn.commit()


def search_cards_by_name(query):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, anime, character, rarity, file_id FROM cards WHERE LOWER(character) LIKE %s OR LOWER(anime) LIKE %s",
            (f"%{query.lower()}%", f"%{query.lower()}%")
        )
        cards = []
        for r in cur.fetchall():
            rid = r['rarity']
            name, _, emoji = rarity_to_text(rid)
            cards.append({
                "id": r['id'],
                "anime": r['anime'],
                "character": r['character'],
                "rarity_name": name,
                "rarity_emote": emoji,
                "file_id": r['file_id'],
            })
        return cards