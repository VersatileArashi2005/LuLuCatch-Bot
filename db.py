import psycopg2
import os

# Postgres connection function
def get_conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        database=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD")
    )

# ----------------------------
# User-related functions
# ----------------------------
def get_user(user_id):
    """
    Get user info by Telegram ID
    Returns dict: id, username, role, currency
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, username, role, currency FROM users WHERE id=%s", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        return {
            "id": row[0],
            "username": row[1],
            "role": row[2],
            "currency": row[3]
        }
    return None

def add_user(user_id, username):
    """
    Add a new user with default values
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (id, username, role, currency) VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
        (user_id, username, "USER", 1000)
    )
    conn.commit()
    cur.close()
    conn.close()

# ----------------------------
# Card-related functions
# ----------------------------
def get_card(card_id):
    """
    Get a card by its ID
    Returns a dict with keys: id, character, anime, rarity, file_id
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, character, anime, rarity, file_id FROM cards WHERE id=%s", (card_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        return {
            "id": row[0],
            "character": row[1],
            "anime": row[2],
            "rarity": row[3],
            "file_id": row[4]
        }
    return None

def add_card(character, anime, rarity, file_id):
    """
    Add a new card to the database
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO cards (character, anime, rarity, file_id) VALUES (%s, %s, %s, %s) RETURNING id",
        (character, anime, rarity, file_id)
    )
    card_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return card_id

# ----------------------------
# Additional functions
# ----------------------------
def get_user_inventory(user_id):
    """
    Returns list of card dicts the user owns
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT c.id, c.character, c.anime, c.rarity, c.file_id FROM cards c "
        "JOIN user_cards uc ON uc.card_id=c.id WHERE uc.user_id=%s",
        (user_id,)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {"id": r[0], "character": r[1], "anime": r[2], "rarity": r[3], "file_id": r[4]}
        for r in rows
    ]

def give_card_to_user(user_id, card_id):
    """
    Assign card to user
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO user_cards (user_id, card_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (user_id, card_id)
    )
    conn.commit()
    cur.close()
    conn.close()
