# commands/start.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from db import ensure_user, register_group

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    # SAVE user in database using correct column "user_id"
    ensure_user(
        user.id, 
        user.first_name or user.username or "User"
    )

    # MAIN MENU BUTTONS
    keyboard = [
        [InlineKeyboardButton("➕ Add me to your group", url=f"https://t.me/{context.bot.username}?startgroup=true")],
        [InlineKeyboardButton("🔗 Support", url="https://t.me/lulucatch")],
        [InlineKeyboardButton("❓ Help", callback_data="help_menu")]
    ]

    if update.message:
        await update.message.reply_text(
            "👋 Welcome to LuLuCatch Bot!\nUse the buttons below.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # REGISTER GROUP
    if chat.type in ("group", "supergroup"):
        register_group(chat.id, chat.title or "Group")
