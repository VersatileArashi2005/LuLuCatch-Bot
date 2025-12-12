# ============================================================
# 📁 File: handlers/drop.py
# 📍 Location: LuLuCatch-Bot/handlers/drop.py
# 📝 Description: Drop System - Message-based card spawning
# ============================================================

import asyncio
import random
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from difflib import SequenceMatcher

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    ReactionTypeEmoji,
)
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.error import TelegramError, BadRequest
from telegram.constants import ParseMode

from config import Config
from db import db
from utils.logger import app_logger, error_logger, log_command
from utils.rarity import (
    RARITY_TABLE,
    get_rarity_emoji,
    rarity_to_text,
    calculate_rarity_value,
    roll_rarity,
)


# ============================================================
# 🎨 Stylish Text Formatting (iPhone Quality)
# ============================================================

class TextStyle:
    """Beautiful Unicode text transformations."""
    
    # Small caps alphabet
    SMALL_CAPS = {
        'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ꜰ',
        'g': 'ɢ', 'h': 'ʜ', 'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ',
        'm': 'ᴍ', 'n': 'ɴ', 'o': 'ᴏ', 'p': 'ᴘ', 'q': 'ǫ', 'r': 'ʀ',
        's': 'ꜱ', 't': 'ᴛ', 'u': 'ᴜ', 'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x',
        'y': 'ʏ', 'z': 'ᴢ'
    }
    
    # Decorative elements
    SPARKLES = ['✦', '✧', '★', '☆', '✴', '✵', '❋', '❊']
    HEARTS = ['♡', '♥', '❤', '💕', '💖', '💗', '💝']
    DIAMONDS = ['◆', '◇', '❖', '💎', '✦']
    
    @classmethod
    def to_small_caps(cls, text: str) -> str:
        """Convert text to small caps."""
        return ''.join(cls.SMALL_CAPS.get(c.lower(), c) for c in text)
    
    @classmethod
    def sparkle(cls) -> str:
        """Get random sparkle."""
        return random.choice(cls.SPARKLES)
    
    @classmethod
    def heart(cls) -> str:
        """Get random heart."""
        return random.choice(cls.HEARTS)


# ============================================================
# 🎯 Drop System Configuration
# ============================================================

# Default drop threshold (messages)
DEFAULT_DROP_THRESHOLD = 50

# Minimum and maximum drop thresholds
MIN_DROP_THRESHOLD = 10
MAX_DROP_THRESHOLD = 500

# Catch timeout (seconds) - how long a drop stays active
DROP_TIMEOUT = 300  # 5 minutes

# Reactions for successful catches (by rarity tier)
CATCH_REACTIONS = {
    "common": ["👍", "🎉"],
    "rare": ["🔥", "⭐", "🎉"],
    "epic": ["🔥", "💯", "⭐", "🎊"],
    "legendary": ["🔥", "💯", "❤️", "🏆", "💎"],
    "mythic": ["🔥", "💯", "❤️", "🏆", "💎", "🎉"],
}

# In-memory storage for active drops (per group)
# Structure: {group_id: {"card": card_data, "message_id": msg_id, "spawned_at": datetime}}
active_drops: Dict[int, Dict[str, Any]] = {}

# Message counters per group
# Structure: {group_id: current_count}
message_counters: Dict[int, int] = {}