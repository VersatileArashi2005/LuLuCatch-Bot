# start.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, CallbackQueryHandler
from db import ensure_user, register_group

# ---------- START COMMAND ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    # Ensure user in DB
    ensure_user(user.id, user.first_name or user.username or "User")

    # Anime girl cute style greeting with username mention
    mention = f"[{user.first_name}](tg://user?id={user.id})"
    welcome_text = (
        f"✨ Hello, {mention}~!\n"
        "💖 I'm your cute LuLuCatch Bot!\n"
        "I can help you collect cards, manage your inventory, and have fun~\n\n"
        "Use the buttons below to get started!"
    )

    # Inline buttons
    keyboard = [
        [InlineKeyboardButton("➕ Add me to your group", url=f"https://t.me/{context.bot.username}?startgroup=true")],
        [InlineKeyboardButton("🔗 Support", url="https://t.me/lulucatch")],
        [InlineKeyboardButton("❓ Help", callback_data="help_menu")]
    ]

    if update.message:
        await update.message.reply_markdown(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    # Register group if started in a group chat
    if chat and chat.type in ("group", "supergroup"):
        register_group(chat.id, chat.title)


# ---------- HELP BUTTON HANDLER ----------
async def help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot commands when Help button is pressed"""
    help_text = (
        "✨ **Available Commands:**\n\n"
        "➤ /start - Show welcome menu\n"
        "➤ /upload - Upload your images\n"
        "➤ /info - Show your profile\n"
        "➤ /help - Show this help message"
    )
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(help_text, parse_mode='Markdown')


# ---------- REGISTER HANDLERS ----------
def register_handlers(application):
    from telegram.ext import CommandHandler

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(help_menu, pattern="help_menu"))