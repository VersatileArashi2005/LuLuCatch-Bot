# commands/start.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from db import ensure_user, register_group

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    # Ensure user exists in database
    ensure_user(user.id, user.first_name or user.username or "User")

    # Reply keyboard
    keyboard = [
        [InlineKeyboardButton("➕ Add me to your group", url=f"https://t.me/{context.bot.username}?startgroup=true")],
        [InlineKeyboardButton("🔗 Support", url="https://t.me/lulucatch")],
        [InlineKeyboardButton("❓ Help", callback_data="help_menu")]
    ]
    await update.message.reply_text("👋 Welcome to LuLuCatch Bot!\nUse buttons below.", reply_markup=InlineKeyboardMarkup(keyboard))

    # If started in a group, register group in DB
    if chat.type in ("group", "supergroup"):
        register_group(chat.id, chat.title)
