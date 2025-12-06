from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)
from commands.start import start
from commands.help import help_command
from commands.upload import upload_command, upload_anime, upload_character, upload_rarity
from commands.check import check_card

# Token from environment
import os
TOKEN = os.getenv("BOT_TOKEN")

app = ApplicationBuilder().token(TOKEN).build()

# User Commands
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("upload", upload_command))
app.add_handler(CommandHandler("check", check_card))

# Upload Step Handlers
ANIME = [CallbackQueryHandler(upload_anime, pattern="^anime_")]
CHARACTER = [CallbackQueryHandler(upload_character, pattern="^character_")]
RARITY = [CallbackQueryHandler(upload_rarity, pattern="^rarity_")]

for h in ANIME + CHARACTER + RARITY:
    app.add_handler(h)

print("Bot is running...")
app.run_polling()
