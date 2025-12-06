# main.py
import os
import psycopg2
import uvicorn
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# ---------- ENV ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# ---------- DB ----------
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
        CREATE TABLE IF NOT EXISTS cards (
            id SERIAL PRIMARY KEY,
            anime VARCHAR(255),
            character VARCHAR(255),
            rarity VARCHAR(50),
            file_id TEXT
        );
    """)
    db.commit()
    cur.close()
    print("✅ Tables ensured.")

# ---------- Rarity & Emote ----------
RARITY_EMOTES = {
    "bronze": "🥉",
    "silver": "🥈",
    "rare": "🔹",
    "epic": "💜",
    "platinum": "🏆",
    "emerald": "💚",
    "diamond": "💎",
    "mythical": "✨",
    "legendary": "🟠",
    "supernatural": "🌌"
}
RARITY_PERCENT = {
    "bronze": 100,
    "silver": 90,
    "rare": 80,
    "epic": 70,
    "platinum": 40,
    "emerald": 30,
    "diamond": 10,
    "mythical": 5,
    "legendary": 2,
    "supernatural": 1
}

# ---------- Helpers ----------
def get_card_by_id(card_id):
    if not db:
        return None
    cur = db.cursor()
    cur.execute("SELECT id, anime, character, rarity, file_id FROM cards WHERE id=%s;", (card_id,))
    r = cur.fetchone()
    cur.close()
    return r

# ---------- FastAPI + Bot ----------
app = FastAPI()
application = Application.builder().token(BOT_TOKEN).build()

# ---------- Commands ----------
async def start_cmd(update, context):
    await update.message.reply_text("👋 Welcome! Use /check <card_id> to see card info.")

async def check_cmd(update, context):
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("Usage: /check <card_id>")
        return
    try:
        card_id = int(parts[1])
    except ValueError:
        await update.message.reply_text("Card ID must be a number.")
        return

    card = get_card_by_id(card_id)
    if not card:
        await update.message.reply_text("❌ Card not found.")
        return

    cid, anime, character, rarity, file_id = card
    emote = RARITY_EMOTES.get(rarity.lower(), "🎴")
    percent = RARITY_PERCENT.get(rarity.lower(), 0)
    caption = (
        f"{emote} {character}\n"
        f"📌 ID: {cid}\n"
        f"🎬 Anime: {anime}\n"
        f"🏷 Rarity: {rarity.capitalize()} {percent}%"
    )

    await update.message.reply_photo(photo=file_id, caption=caption)

# ---------- Register Handlers ----------
application.add_handler(CommandHandler("start", start_cmd))
application.add_handler(CommandHandler("check", check_cmd))

# ---------- Webhook ----------
@app.post("/webhook")
async def webhook_receiver(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}

# ---------- Startup / Shutdown ----------
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
