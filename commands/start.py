# commands/start.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler
from commands.utils import format_telegram_name
from db import ensure_user, register_group

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    pool = context.application.bot_data.get("pool")

    # ensure user
    if pool:
        await ensure_user(pool, user.id, user.first_name or user.username or "User")

    mention = f"[{user.first_name}](tg://user?id={user.id})"
    welcome_text = (
        f"✨ Hello, {mention}~!\n"
        "💖 Welcome to LuLuCatch — collect rare anime cards and have fun!\n\n"
        "Use the buttons below to get started!"
    )

    keyboard = [
        [InlineKeyboardButton("➕ Add me to your group", url=f"https://t.me/{context.bot.username}?startgroup=true")],
        [InlineKeyboardButton("💙 Support", url="https://t.me/lulucatch")],
        [InlineKeyboardButton("❓ Help", callback_data="help_menu")]
    ]

    if update.message:
        await update.message.reply_markdown(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    # register group if in group
    if chat and chat.type in ("group", "supergroup") and pool:
        await register_group(pool, chat.id, chat.title)

def register_start_handlers(application):
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CallbackQueryHandler(lambda u,c: None, pattern="help_menu"))  # help handled in main