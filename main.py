import os
import uvicorn
from fastapi import FastAPI, Request

# telegram bot imports
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

# config
from config import BOT_TOKEN, WEBHOOK_URL, PORT

# db
from db import init_db, register_group

# commands
from commands.start import start
from commands.info import info_cmd
from commands.check import register_check_handlers
from commands.upload import register_handlers as register_upload_handlers
from commands.admin import register_admin_handlers

app = FastAPI()

# Initialize bot application
application = Application.builder().token(BOT_TOKEN).build()

# Register basic command handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("info", info_cmd))

# Register /check handlers
register_check_handlers(application)

# Register upload & admin handlers (they register multiple handlers)
register_upload_handlers(application)
register_admin_handlers(application)

# Group message listener (auto register groups)
async def group_message_listener(update, context):
    chat = update.effective_chat
    if chat and chat.type in ("group", "supergroup"):
        register_group(chat.id, chat.title)

application.add_handler(MessageHandler(filters.ALL & filters.ChatType.GROUPS, group_message_listener))

# ---- CallbackQuery for buttons (like Help) ----
async def help_callback(update: Update, context):
    query = update.callback_query
    if query and query.data == "help_menu":
        await query.answer()  # answer callback to remove "loading..."
        help_text = (
            "📜 **Available Commands:**\n\n"
            "/start - Show welcome message and buttons\n"
            "/info - Get your info\n"
            "/check - Check a card\n"
            "/upload - Upload a card (if allowed)\n"
            # add other commands here if needed
        )
        await query.message.reply_text(help_text, parse_mode="Markdown")

application.add_handler(CallbackQueryHandler(help_callback, pattern="help_menu"))

# ---- Webhook Receiver ----
@app.post("/webhook")
async def webhook_receiver(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}

# ---- Startup ----
@app.on_event("startup")
async def on_startup():
    print("Starting up... init db and bot")
    # create/migrate DB tables
    init_db()

    await application.initialize()

    if WEBHOOK_URL:
        await application.bot.set_webhook(f"{WEBHOOK_URL}/webhook")

    await application.start()
    print("Bot started.")

# ---- Shutdown ----
@app.on_event("shutdown")
async def on_shutdown():
    print("Shutting down bot...")
    await application.stop()
    await application.shutdown()

# ---- Run server ----
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)