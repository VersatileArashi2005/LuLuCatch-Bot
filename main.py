import os
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler
)
import uvicorn

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

app = FastAPI()
application = Application.builder().token(BOT_TOKEN).build()


# /start handler
async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("➕ Add me to your group", url=f"https://t.me/{context.bot.username}?startgroup=true")],
        [InlineKeyboardButton("🔗 Support", url="https://t.me/lulucatch")],
        [InlineKeyboardButton("❓ Help", callback_data="help_menu")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "👋 Welcome to **LuLuCatch Bot**!\n\n"
        "Use the buttons below to continue:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


# help button
async def help_button(update, context):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "**Commands List**\n"
        "/start - Show menu\n"
        "/help - Show help\n"
        "/ping - Check bot status",
        parse_mode="Markdown"
    )


# Normal help command
async def help_cmd(update, context):
    await update.message.reply_text(
        "**Help Menu**\n"
        "/start - Show menu\n"
        "/help - Show help",
        parse_mode="Markdown"
    )


# Webhook Receiver
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}


# Set webhook on startup
@app.on_event("startup")
async def startup():
    await application.initialize()
    await application.bot.set_webhook(WEBHOOK_URL)
    await application.start()


# Commands
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_cmd))
application.add_handler(CallbackQueryHandler(help_button, pattern="help_menu"))


# Run Uvicorn for Railway
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
