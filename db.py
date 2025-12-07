# db.py
import sqlite3

conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

# Example tables
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    telegram_id INTEGER UNIQUE,
    username TEXT,
    role TEXT DEFAULT 'USER',
    currency INTEGER DEFAULT 1000
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY,
    name TEXT,
    anime TEXT,
    character TEXT,
    rarity INTEGER
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    card_id INTEGER,
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(card_id) REFERENCES cards(id)
)''')

conn.commit()

# DB functions
def add_user(telegram_id, username):
    cursor.execute("INSERT OR IGNORE INTO users (telegram_id, username) VALUES (?, ?)", (telegram_id, username))
    conn.commit()

def get_user(telegram_id):
    cursor.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
    return cursor.fetchone()

def add_card(name, anime, character, rarity):
    cursor.execute("INSERT INTO cards (name, anime, character, rarity) VALUES (?, ?, ?, ?)", (name, anime, character, rarity))
    conn.commit()

def get_card(card_id):
    cursor.execute("SELECT * FROM cards WHERE id=?", (card_id,))
    return cursor.fetchone()

def get_inventory(user_id):
    cursor.execute("SELECT * FROM inventory WHERE user_id=?", (user_id,))
    return cursor.fetchall()

def add_inventory(user_id, card_id):
    cursor.execute("INSERT INTO inventory (user_id, card_id) VALUES (?, ?)", (user_id, card_id))
    conn.commit()
