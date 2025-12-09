# commands/start.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from db import ensure_user, register_group

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    await ensure_user(context.application.bot_data["pool"], user.id, user.first_name or user.username or "User")

    mention = f"[{user.first_name}](tg://user?id={user.id})"
    welcome_text = (
        f"✨ Hello, {mention}~!\n"
        "💖 I'm LuLuCatch — collect anime cards and have fun!\n\n"
        "Use the buttons below to get started!"
    )

    keyboard = [
        [InlineKeyboardButton("➕ Add me to your group", url=f"https://t.me/{context.bot.username}?startgroup=true")],
        [InlineKeyboardButton("💙 Support", url="https://t.me/lulucatch")],
        [InlineKeyboardButton("❓ Help", callback_data="help_menu")],
    ]

    if update.message:
        await update.message.reply_markdown(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    if chat and chat.type in ("group","supergroup"):
        await register_group(context.application.bot_data["pool"], chat.id, chat.title)

async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query and query.data == "help_menu":
        await query.answer()
        help_text = (
            "📜 **Available Commands:**\n\n"
            "/lulucatch - Catch a random card (24h)\n"
            "/inventory - View your collection\n"
            "/cardinfo <id> - Show card details\n"
            "/upload - Upload card (uploader/admin only)\n"
            "/addcard - Admin add card\n"
            "/info - Reply to someone with /info\n"
        )
        await query.edit_message_text(help_text, parse_mode="Markdown")

def register_start_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(help_callback, pattern="help_menu"))