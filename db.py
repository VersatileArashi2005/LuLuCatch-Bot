import psycopg2
from config import DATABASE_URL

def get_conn():
    return psycopg2.connect(DATABASE_URL)

def get_user(telegram_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE telegram_id=%s", (telegram_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

def add_card(anime, character, rarity, file_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO cards (anime, character, rarity, file_id) VALUES (%s,%s,%s,%s) RETURNING id",
        (anime, character, rarity, file_id)
    )
    card_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return card_id
