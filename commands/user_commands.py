"""
User commands for the Telegram Card Bot.
Includes: /catch, /harem, /check, /search, /start, /help
"""

from telegram import Update
from telegram.ext import (
    ContextTypes, 
    CommandHandler, 
    Application
)
from telegram.constants import ParseMode

from db import db
from config import config
from utils import (
    logger, 
    get_random_rarity, 
    Keyboards,
    format_catch_message,
    format_cooldown_message,
    format_harem_page,
    format_card_detail,
    format_user_profile
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command - Welcome message and registration."""
    user = update.effective_user
    chat = update.effective_chat
    
    # Ensure user is registered
    await db.ensure_user(user.id, user.first_name)
    
    # Register group if applicable
    if chat.type in ['group', 'supergroup']:
        await db.register_group(chat.id, chat.title)
    
    welcome_text = f"""
🎴 **Welcome to Card Bot!** 🎴

Hello, **{user.first_name}**! 👋

I'm a card collecting bot where you can catch anime characters and build your 