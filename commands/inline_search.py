# ============================================================
# 📁 File: commands/inline_search.py
# 📍 Location: telegram_card_bot/commands/inline_search.py
# 📝 Description: Inline search - shows characters, then their cards (images only)
# ============================================================

from uuid import uuid4
from typing import List, Dict, Any, Optional

from telegram import (
    Update,
    InlineQueryResultCachedPhoto,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from telegram.ext import (
    Application,
    InlineQueryHandler,
    ContextTypes,
)

from db import db, get_unique_characters, get_cards_by_character
from utils.logger import app_logger, error_logger
from utils.rarity import rarity_to_text, get_rarity_emoji


# ============================================================
# 📊 Constants
# ============================================================

MAX_RESULTS = 50
MIN_QUERY_LENGTH = 1