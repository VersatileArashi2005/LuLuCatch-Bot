# main.py
import uvicorn
import traceback
from fastapi import FastAPI, Request

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, InlineQueryHandler, filters

from config import BOT_TOKEN, WEBHOOK_URL, PORT
from db import get_pool, init_db

# Commands
from commands.start import register_start_handlers
from commands.info import register_info_handlers
from commands.check import register_check_handlers
from commands.upload import register_upload_handlers
from commands.admin import register_admin_handlers
from commands.catch import register_catch_handlers
from commands.harem import register_harem_handlers
from commands.inline import register_inline_handlers

from utils.logger import app_logger, error_logger

app = FastAPI()

def log_error(e, where="Unknown"):
    error_logger.error(f"Error in {where}: {e}", exc_info=True)

# Build the PTB application
application = Application.builder().token(BOT_TOKEN).build()

# Register handlers (these functions will attach to the application)
register_start_handlers(application)
register_info_handlers(application)
register_check_handlers(application)
register_upload_handlers(application)
register_admin_handlers(application)
register_catch_handlers(application)
register_harem_handlers(application)
register_inline_handlers(application)

# Group message listener
async def group_message_listener(update: Update, context):
    try:
        chat = update.effective_chat
        if chat and chat.type in ("group", "supergroup"):
            # store pool under application.bot_data['pool'] so handlers can use it
            pool = application.bot_data.get("pool")
            if pool:
                from db import register_group
                await register_group(pool, chat.id, chat.title)
    except Exception as e:
        log_error(e, "group_message_listener")

application.add_handler(
    MessageHandler(filters.ALL & (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP), group_message_listener)
)

# Help callback
async def help_callback(update: Update, context):
    try:
        query = update.callback_query
        if query and query.data == "help_menu":
            await query.answer()
            help_text = (
                "📜 **Available Commands:**\n\n"
                "/start - Show welcome message and buttons\n"
                "/info - Get user info (reply)\n"
                "/check <id> - See card\n"
                "/upload - Upload a card (owner/dev/admin/uploader only)\n"
                "/catch - Catch daily random card\n"
                "/harem - View your collection\n"
            )
            await query.message.reply_text(help_text, parse_mode="Markdown")
    except Exception as e:
        log_error(e, "help_callback")

application.add_handler(CallbackQueryHandler(help_callback, pattern="help_menu"))

# Webhook receiver
@app.post("/webhook")
async def webhook_receiver(request: Request):
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
    except Exception as e:
        log_error(e, "Webhook Receiver")
    return {"ok": True}

# Startup / Shutdown
@app.on_event("startup")
async def on_startup():
    app_logger.info("Starting up, creating DB pool...")
    try:
        pool = await get_pool()
        application.bot_data["pool"] = pool
        await init_db(pool)
        await application.initialize()
        if WEBHOOK_URL:
            await application.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
        await application.start()
        app_logger.info("Bot started.")
    except Exception as e:
        log_error(e, "Startup")
        raise

@app.on_event("shutdown")
async def on_shutdown():
    app_logger.info("Shutting down bot...")
    try:
        await application.stop()
        await application.shutdown()
        pool = application.bot_data.get("pool")
        if pool:
            await pool.close()
    except Exception as e:
        log_error(e, "Shutdown")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)