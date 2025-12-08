# main.py (Async / FastAPI / asyncpg)
import os
import uvicorn
import traceback
from fastapi import FastAPI, Request

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, InlineQueryHandler, filters

from config import BOT_TOKEN, WEBHOOK_URL, PORT
from db import get_pool, init_db, register_group

# Commands
from commands.start import start
from commands.info import info_cmd
from commands.check import register_check_handlers
from commands.upload import register_handlers as register_upload_handlers
from commands.admin import register_admin_handlers
from commands.inline import inline_query
from commands.catch import register_catch_handlers
from commands.harem import register_harem_handlers

app = FastAPI()

# ERROR LOGGER
def log_error(e, where="Unknown"):
    print("\n" + "="*60)
    print(f"🔥 ERROR in {where}: {e}")
    print(traceback.format_exc())
    print("="*60 + "\n")

# Initialize bot
application = Application.builder().token(BOT_TOKEN).build()

# ---- Register handlers ----
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("info", info_cmd))
register_check_handlers(application)
register_upload_handlers(application)
register_admin_handlers(application)
register_catch_handlers(application)
register_harem_handlers(application)
application.add_handler(InlineQueryHandler(inline_query))

# ---- Group listener ----
@app.on_event("startup")
async def on_startup():
    print("Starting up...")
    # Initialize DB pool
    pool = await get_pool()
    app.state.pool = pool
    await init_db(pool)

    await application.initialize()
    if WEBHOOK_URL:
        await application.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    await application.start()
    print("Bot started.")

@app.on_event("shutdown")
async def on_shutdown():
    print("Shutting down bot...")
    await application.stop()
    await application.shutdown()

async def group_message_listener(update: Update, context):
    try:
        chat = update.effective_chat
        if chat and chat.type in ("group", "supergroup"):
            await register_group(app.state.pool, chat.id, chat.title)
    except Exception as e:
        log_error(e, "group_message_listener")

application.add_handler(MessageHandler(filters.ALL & (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP), group_message_listener))

# ---- Help Callback ----
async def help_callback(update: Update, context):
    query = update.callback_query
    if query and query.data == "help_menu":
        await query.answer()
        help_text = (
            "📜 **Available Commands:**\n\n"
            "/start - Show welcome message and buttons\n"
            "/info - Get your info\n"
            "/check - Check a card\n"
            "/upload - Upload a card (if allowed)\n"
            "/catch - Catch a daily random card\n"
            "/harem - View your card inventory\n"
        )
        await query.message.reply_text(help_text, parse_mode="Markdown")

application.add_handler(CallbackQueryHandler(help_callback, pattern="help_menu"))

# ---- Webhook ----
@app.post("/webhook")
async def webhook_receiver(request: Request):
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
    except Exception as e:
        log_error(e, "Webhook Receiver")
    return {"ok": True}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)