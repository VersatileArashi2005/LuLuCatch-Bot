import os
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

app = FastAPI()
application = Application.builder().token(BOT_TOKEN).build()


# Handlers
async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("➕ Add me to your group", url=f"https://t.me/{context.bot.username}?startgroup=true")],
        [InlineKeyboardButton("🔗 Support", url="https://t.me/lulucatch")],
        [InlineKeyboardButton("❓ Help", callback_data="help_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Welcome!\nUse the buttons below to continue:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def help_button(update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "**Commands List**\n/start - Show menu\n/help - Show help",
        parse_mode="Markdown"
    )

async def help_cmd(update, context):
    await update.message.reply_text(
        "**Help Menu**\n/start - Show menu\n/help - Show help",
        parse_mode="Markdown"
    )

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_cmd))
application.add_handler(CallbackQueryHandler(help_button, pattern="help_menu"))


# Webhook receiver
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}


# Startup
@app.on_event("startup")
async def on_startup():
    await application.initialize()
    await application.bot.set_webhook(WEBHOOK_URL)
    await application.start()  # no polling


# Shutdown
@app.on_event("shutdown")
async def on_shutdown():
    await application.stop()
    await application.shutdown()


# Run with uvicorn
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
