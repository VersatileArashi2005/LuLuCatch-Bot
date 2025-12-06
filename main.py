import os
import random
import datetime
import uvicorn
import psycopg2
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# --------- ENV ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # no trailing slash
OWNER_ID = int(os.getenv("OWNER_ID", "0"))  # set to your telegram id e.g. 7158056614

# --------- DB ----------
db = None

def connect_db():
    global db
    DB_HOST = os.getenv("PGHOST")
    DB_NAME = os.getenv("PGDATABASE")
    DB_USER = os.getenv("PGUSER")
    DB_PASS = os.getenv("PGPASSWORD")

    if not all([DB_HOST, DB_NAME, DB_USER, DB_PASS]):
        print("❌ Missing Postgres env variables.")
        return False
    try:
        db = psycopg2.connect(
            host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS
        )
        print("✅ Connected to Postgres.")
        return True
    except Exception as e:
        print("❌ DB connect error:", e)
        db = None
        return False

def create_tables():
    if not db:
        return
    cur = db.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        first_name VARCHAR(255),
        role VARCHAR(50) DEFAULT 'user',
        last_catch TIMESTAMP
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS cards (
        id SERIAL PRIMARY KEY,
        anime VARCHAR(255),
        character VARCHAR(255),
        rarity VARCHAR(50),
        file_id TEXT
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_cards (
        id SERIAL PRIMARY KEY,
        user_id BIGINT REFERENCES users(user_id),
        card_id INTEGER REFERENCES cards(id),
        quantity INTEGER DEFAULT 1,
        UNIQUE (user_id, card_id)
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS chat_stats (
        chat_id BIGINT PRIMARY KEY,
        message_count BIGINT DEFAULT 0
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS active_drops (
        chat_id BIGINT PRIMARY KEY,
        card_id INTEGER REFERENCES cards(id),
        claimed_by BIGINT
    );
    """)
    db.commit()
    cur.close()
    print("✅ Tables ensured.")

# helpers
def add_card_to_library(anime, character, rarity, file_id):
    if not db:
        return None
    cur = db.cursor()
    cur.execute("""
        INSERT INTO cards (anime, character, rarity, file_id)
        VALUES (%s, %s, %s, %s) RETURNING id;
    """, (anime, character, rarity, file_id))
    card_id = cur.fetchone()[0]
    db.commit()
    cur.close()
    return card_id

def get_random_card():
    if not db:
        return None
    cur = db.cursor()
    cur.execute("SELECT id, anime, character, rarity, file_id FROM cards ORDER BY RANDOM() LIMIT 1;")
    row = cur.fetchone()
    cur.close()
    return row  # None if no cards

def ensure_user_in_db(user_id, first_name):
    if not db:
        return
    cur = db.cursor()
    cur.execute("""
        INSERT INTO users (user_id, first_name)
        VALUES (%s, %s)
        ON CONFLICT (user_id) DO NOTHING;
    """, (user_id, first_name))
    db.commit()
    cur.close()

def give_card_to_user(user_id, card_id):
    if not db:
        return False
    cur = db.cursor()
    cur.execute("""
        INSERT INTO user_cards (user_id, card_id, quantity)
        VALUES (%s, %s, 1)
        ON CONFLICT (user_id, card_id) DO UPDATE
        SET quantity = user_cards.quantity + 1;
    """, (user_id, card_id))
    db.commit()
    cur.close()
    return True

def increment_chat_message_count(chat_id):
    if not db:
        return 0
    cur = db.cursor()
    cur.execute("""
        INSERT INTO chat_stats (chat_id, message_count)
        VALUES (%s, 1)
        ON CONFLICT (chat_id) DO UPDATE
        SET message_count = chat_stats.message_count + 1
        RETURNING message_count;
    """, (chat_id,))
    new_count = cur.fetchone()[0]
    db.commit()
    cur.close()
    return new_count

def set_active_drop(chat_id, card_id):
    if not db:
        return
    cur = db.cursor()
    cur.execute("""
        INSERT INTO active_drops (chat_id, card_id, claimed_by)
        VALUES (%s, %s, NULL)
        ON CONFLICT (chat_id) DO UPDATE
        SET card_id = EXCLUDED.card_id, claimed_by = NULL;
    """, (chat_id, card_id))
    db.commit()
    cur.close()

def get_active_drop(chat_id):
    if not db:
        return None
    cur = db.cursor()
    cur.execute("SELECT card_id, claimed_by FROM active_drops WHERE chat_id = %s;", (chat_id,))
    row = cur.fetchone()
    cur.close()
    return row

def claim_active_drop(chat_id, user_id):
    if not db:
        return False
    cur = db.cursor()
    # Check unclaimed
    cur.execute("SELECT card_id, claimed_by FROM active_drops WHERE chat_id = %s;", (chat_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        return False
    card_id, claimed_by = row
    if claimed_by is not None:
        cur.close()
        return False
    cur.execute("UPDATE active_drops SET claimed_by = %s WHERE chat_id = %s;", (user_id, chat_id))
    db.commit()
    cur.close()
    # Add to user
    give_card_to_user(user_id, card_id)
    return True

def find_card_by_name(name):
    if not db:
        return None
    cur = db.cursor()
    cur.execute("SELECT id, anime, character, rarity, file_id FROM cards WHERE LOWER(character) = LOWER(%s) LIMIT 1;", (name,))
    r = cur.fetchone()
    cur.close()
    return r

def get_user_harem(user_id):
    if not db:
        return []
    cur = db.cursor()
    cur.execute("""
        SELECT c.id, c.anime, c.character, c.rarity, uc.quantity, c.file_id
        FROM user_cards uc
        JOIN cards c ON uc.card_id = c.id
        WHERE uc.user_id = %s;
    """, (user_id,))
    rows = cur.fetchall()
    cur.close()
    return rows

# ---------- Pending uploads in-memory (uploader_id -> (anime,character,rarity)) ----------
pending_uploads = {}

# ---------- FastAPI + Bot ----------
app = FastAPI()
application = Application.builder().token(BOT_TOKEN).build()

# Handlers
async def start_cmd(update, context):
    user = update.effective_user
    ensure_user_in_db(user.id, user.first_name)
    keyboard = [
        [InlineKeyboardButton("➕ Add me to your group", url=f"https://t.me/{context.bot.username}?startgroup=true")],
        [InlineKeyboardButton("🔗 Support", url="https://t.me/lulucatch")],
        [InlineKeyboardButton("❓ Help", callback_data="help_menu")]
    ]
    await update.message.reply_text("👋 Welcome! Use the buttons below.", reply_markup=InlineKeyboardMarkup(keyboard))

async def help_cmd(update, context):
    await update.message.reply_text(
        "/start /help /LuLuCatch <name> /harem /upload (owner/admin/dev) \nAdmin: /addadmin /gban /info"
    )

async def harem_cmd(update, context):
    user = update.effective_user
    ensure_user_in_db(user.id, user.first_name)
    rows = get_user_harem(user.id)
    if not rows:
        await update.message.reply_text("Your harem is empty.")
        return
    texts = []
    for r in rows:
        cid, anime, character, rarity, qty, file_id = r
        texts.append(f"{character} ({anime}) x{qty} [{rarity}]")
    await update.message.reply_text("\n".join(texts))

# /upload <anime>|<character>|<rarity>
async def upload_cmd(update, context):
    user = update.effective_user
    # check role: owner or db role admin/dev
    if user.id != OWNER_ID:
        # check DB role
        cur = db.cursor()
        cur.execute("SELECT role FROM users WHERE user_id=%s;", (user.id,))
        r = cur.fetchone()
        cur.close()
        role = r[0] if r else "user"
        if role not in ("admin", "dev"):
            await update.message.reply_text("🔒 Only owner/admin/dev can use /upload.")
            return
    # parse args
    text = update.message.text or ""
    parts = text.split(" ", 1)
    if len(parts) < 2:
        await update.message.reply_text("Usage: /upload AnimeName|CharacterName|Rarity\nExample: /upload OnePiece|Nami|rare")
        return
    payload = parts[1].strip()
    if "|" not in payload:
        await update.message.reply_text("Please separate fields with | (pipe).")
        return
    anime, character, rarity = [p.strip() for p in payload.split("|", 2)]
    # store pending and DM user to send photo privately
    pending_uploads[user.id] = (anime, character, rarity)
    try:
        await context.bot.send_message(chat_id=user.id,
                                       text=f"Send the image for the card:\nAnime: {anime}\nCharacter: {character}\nRarity: {rarity}\n\nPlease send the photo here (private chat).")
        # if called from group, also confirm
        if update.effective_chat.type != "private":
            await update.message.reply_text("✅ I messaged you in private. Please send the card image in DM to complete upload.")
    except Exception as e:
        await update.message.reply_text("❌ I couldn't DM you. Make sure you started the bot in private first.")
        print("DM error:", e)

# Handler for photos in private - finalize upload
async def private_photo_handler(update, context):
    user = update.effective_user
    if user.id not in pending_uploads:
        await update.message.reply_text("No pending upload. Use /upload in group first.")
        return
    if not update.message.photo:
        await update.message.reply_text("Please send a photo.")
        return
    # get highest resolution file_id
    photo = update.message.photo[-1]
    file_id = photo.file_id
    anime, character, rarity = pending_uploads.pop(user.id)
    # Save to cards table (store file_id)
    card_id = add_card_to_library(anime, character, rarity, file_id)
    await update.message.reply_text(f"✅ Uploaded card '{character}' ({anime}) as id {card_id}.\nIt will be available for drops.")
    print(f"Uploaded card id={card_id} by user {user.id}")

# Group message handler: count messages & check drops/claims
async def group_message_handler(update, context):
    message = update.message
    if not message or message.from_user.is_bot:
        return
    chat = update.effective_chat
    user = update.effective_user
    # increment count (only for groups/supergroups)
    if chat.type in ("group", "supergroup"):
        new_count = increment_chat_message_count(chat.id)
        # Every 50 messages -> create a drop
        if new_count % 50 == 0:
            card = get_random_card()
            if card:
                cid, anime, character, rarity, file_id = card
                set_active_drop(chat.id, cid)
                # send photo to chat with prompt (use file_id)
                await context.bot.send_photo(chat_id=chat.id, photo=file_id,
                                             caption=f"🎴 A new card has dropped! Try to claim it using:\n`/LuLuCatch {character}`",
                                             parse_mode="Markdown")
    # Also check if this message may be a claim for an active drop (text only)
    text = message.text or ""
    if text and text.startswith("/LuLuCatch"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            return
        claim_name = parts[1].strip()
        active = get_active_drop(chat.id)
        if not active or active[1] is not None:
            return
        card_row = find_card_by_name(claim_name)
        if card_row and card_row[0] == active[0]:
            success = claim_active_drop(chat.id, user.id)
            if success:
                await context.bot.send_message(chat_id=chat.id,
                                               text=f"🎉 {user.first_name} claimed *{card_row[2]}*!",
                                               parse_mode="Markdown")

# Admin /info
async def info_cmd(update, context):
    user = update.effective_user
    if user.id != OWNER_ID:
        await update.message.reply_text("🔒 Owner only.")
        return
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("Usage: /info <user_id>")
        return
    target = int(parts[1])
    cur = db.cursor()
    cur.execute("SELECT user_id, first_name, role, last_catch FROM users WHERE user_id = %s;", (target,))
    r = cur.fetchone()
    cur.close()
    if not r:
        await update.message.reply_text("No user found.")
    else:
        await update.message.reply_text(f"User: {r[1]} ({r[0]})\nRole: {r[2]}\nLast catch: {r[3]}")

# Register handlers
application.add_handler(CommandHandler("start", start_cmd))
application.add_handler(CommandHandler("help", help_cmd))
application.add_handler(CommandHandler("harem", harem_cmd))
application.add_handler(CommandHandler("upload", upload_cmd))
application.add_handler(CommandHandler("info", info_cmd))

# message handlers
application.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, private_photo_handler))
application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), group_message_handler))

# webhook receiver
@app.post("/webhook")
async def webhook_receiver(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}

# startup/shutdown
@app.on_event("startup")
async def on_startup():
    print("⚙️ Starting app...")
    if connect_db():
        create_tables()
    await application.initialize()
    await application.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    await application.start()
    print("✅ Bot started & webhook set.")

@app.on_event("shutdown")
async def on_shutdown():
    print("🛑 Shutting down...")
    await application.stop()
    await application.shutdown()
    global db
    if db:
        db.close()
        print("🛑 DB closed.")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)

