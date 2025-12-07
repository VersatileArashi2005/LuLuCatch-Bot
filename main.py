# main.py
import os
import uvicorn
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application
from config import BOT_TOKEN, WEBHOOK_URL, PORT
import db

# imports from commands
from commands.start import start
from commands.info import info_cmd
from commands.check import check_cmd
from commands.upload import register_handlers as register_upload_handlers
from commands.admin import register_admin_handlers

# helpers
from db import init_db, register_group, ensure_user

app = FastAPI()

# Initialize bot application
application = Application.builder().token(BOT_TOKEN).build()

# Register command handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("info", info_cmd))
application.add_handler(CommandHandler("check", check_cmd))

# Register upload & admin handlers (they register multiple handlers)
register_upload_handlers(application)
register_admin_handlers(application)

# simple group message listener to register groups automatically
from telegram.ext import MessageHandler, filters

async def group_message_listener(update, context):
    chat = update.effective_chat
    if chat.type in ("group", "supergroup"):
        # register group to groups table
        register_group(chat.id, chat.title)

application.add_handler(MessageHandler(filters.ALL & filters.ChatType.GROUPS, group_message_listener))

# Webhook receiver
@app.post("/webhook")
async def webhook_receiver(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}

# Startup/shutdown events
@app.on_event("startup")
async def on_startup():
    print("Starting up... init db and bot")
    init_db()
    await application.initialize()
    if WEBHOOK_URL:
        # set webhook to WEBHOOK_URL + /webhook
        await application.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    await application.start()
    print("Bot started.")

@app.on_event("shutdown")
async def on_shutdown():
    print("Shutting down bot...")
    await application.stop()
    await application.shutdown()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)
