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


# ============================================================
# 🗄️ Database Functions for Drop System
# ============================================================

async def get_group_drop_settings(group_id: int) -> Dict[str, Any]:
    """Get drop settings for a group."""
    try:
        row = await db.fetchrow(
            """
            SELECT drop_threshold, drop_enabled, message_count, last_drop_at
            FROM groups 
            WHERE group_id = $1
            """,
            group_id
        )
        
        if row:
            return {
                "threshold": row.get("drop_threshold") or DEFAULT_DROP_THRESHOLD,
                "enabled": row.get("drop_enabled", True),
                "message_count": row.get("message_count") or 0,
                "last_drop_at": row.get("last_drop_at"),
            }
        
        return {
            "threshold": DEFAULT_DROP_THRESHOLD,
            "enabled": True,
            "message_count": 0,
            "last_drop_at": None,
        }
        
    except Exception as e:
        error_logger.error(f"Failed to get group drop settings: {e}")
        return {
            "threshold": DEFAULT_DROP_THRESHOLD,
            "enabled": True,
            "message_count": 0,
            "last_drop_at": None,
        }


async def set_group_drop_threshold(group_id: int, threshold: int) -> bool:
    """Set the drop threshold for a group."""
    try:
        await db.execute(
            """
            INSERT INTO groups (group_id, drop_threshold, drop_enabled, message_count)
            VALUES ($1, $2, TRUE, 0)
            ON CONFLICT (group_id) 
            DO UPDATE SET drop_threshold = $2
            """,
            group_id, threshold
        )
        return True
    except Exception as e:
        error_logger.error(f"Failed to set drop threshold: {e}")
        return False


async def increment_message_count(group_id: int) -> int:
    """Increment message count for a group and return new count."""
    try:
        # Update in database
        result = await db.fetchval(
            """
            INSERT INTO groups (group_id, message_count, drop_enabled)
            VALUES ($1, 1, TRUE)
            ON CONFLICT (group_id) 
            DO UPDATE SET message_count = COALESCE(groups.message_count, 0) + 1
            RETURNING message_count
            """,
            group_id
        )
        
        # Also update in-memory counter
        message_counters[group_id] = result or 1
        
        return result or 1
        
    except Exception as e:
        error_logger.error(f"Failed to increment message count: {e}")
        # Fallback to in-memory counter
        message_counters[group_id] = message_counters.get(group_id, 0) + 1
        return message_counters[group_id]


async def reset_message_count(group_id: int) -> bool:
    """Reset message count after a drop."""
    try:
        await db.execute(
            """
            UPDATE groups 
            SET message_count = 0, last_drop_at = NOW()
            WHERE group_id = $1
            """,
            group_id
        )
        
        # Reset in-memory counter
        message_counters[group_id] = 0
        
        return True
    except Exception as e:
        error_logger.error(f"Failed to reset message count: {e}")
        return False


async def get_random_card_for_drop() -> Optional[Dict[str, Any]]:
    """Get a random card for dropping based on rarity weights."""
    try:
        # Roll for rarity
        rarity = roll_rarity()
        
        # Try to get a card of that rarity
        card = await db.fetchrow(
            """
            SELECT card_id, character_name, anime, rarity, image_url
            FROM cards 
            WHERE rarity = $1
            ORDER BY RANDOM() 
            LIMIT 1
            """,
            rarity
        )
        
        # If no card of that rarity, get any random card
        if not card:
            card = await db.fetchrow(
                """
                SELECT card_id, character_name, anime, rarity, image_url
                FROM cards 
                ORDER BY RANDOM() 
                LIMIT 1
                """
            )
        
        if card:
            return dict(card)
        
        return None
        
    except Exception as e:
        error_logger.error(f"Failed to get random card: {e}")
        return None


async def record_catch(
    user_id: int,
    card_id: int,
    group_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None
) -> bool:
    """Record a successful card catch."""
    try:
        # Ensure user exists
        await db.execute(
            """
            INSERT INTO users (user_id, username, first_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) 
            DO UPDATE SET 
                username = COALESCE($2, users.username),
                first_name = COALESCE($3, users.first_name)
            """,
            user_id, username, first_name
        )
        
        # Add card to collection
        await db.execute(
            """
            INSERT INTO collections (user_id, card_id, obtained_at, obtained_in_group)
            VALUES ($1, $2, NOW(), $3)
            """,
            user_id, card_id, group_id
        )
        
        # Update user stats
        await db.execute(
            """
            UPDATE users 
            SET total_catches = COALESCE(total_catches, 0) + 1
            WHERE user_id = $1
            """,
            user_id
        )
        
        # Update group stats
        await db.execute(
            """
            UPDATE groups 
            SET total_catches = COALESCE(total_catches, 0) + 1
            WHERE group_id = $1
            """,
            group_id
        )
        
        return True
        
    except Exception as e:
        error_logger.error(f"Failed to record catch: {e}")
        return False


async def ensure_group_exists(
    group_id: int,
    group_name: Optional[str] = None
) -> bool:
    """Ensure a group exists in the database."""
    try:
        await db.execute(
            """
            INSERT INTO groups (group_id, group_name, drop_enabled, message_count)
            VALUES ($1, $2, TRUE, 0)
            ON CONFLICT (group_id) 
            DO UPDATE SET group_name = COALESCE($2, groups.group_name)
            """,
            group_id, group_name
        )
        return True
    except Exception as e:
        error_logger.error(f"Failed to ensure group exists: {e}")
        return False


# ============================================================
# 🎯 Name Matching System (Fuzzy Matching)
# ============================================================

def normalize_name(name: str) -> str:
    """Normalize a name for comparison."""
    # Convert to lowercase
    name = name.lower().strip()
    
    # Remove common punctuation and extra spaces
    name = re.sub(r'[^\w\s]', '', name)
    name = re.sub(r'\s+', ' ', name)
    
    return name


def calculate_similarity(name1: str, name2: str) -> float:
    """Calculate similarity ratio between two names."""
    norm1 = normalize_name(name1)
    norm2 = normalize_name(name2)
    
    # Exact match
    if norm1 == norm2:
        return 1.0
    
    # Use SequenceMatcher for fuzzy matching
    return SequenceMatcher(None, norm1, norm2).ratio()


def check_name_match(guess: str, actual_name: str, threshold: float = 0.75) -> Tuple[bool, float]:
    """
    Check if a guessed name matches the actual name.
    
    Returns: (is_match, similarity_score)
    """
    guess = guess.strip()
    actual = actual_name.strip()
    
    # Calculate full name similarity
    full_similarity = calculate_similarity(guess, actual)
    
    if full_similarity >= threshold:
        return True, full_similarity
    
    # Check if guess matches first name only
    first_name = actual.split()[0] if actual else ""
    first_similarity = calculate_similarity(guess, first_name)
    
    if first_similarity >= 0.85:  # Higher threshold for first name only
        return True, first_similarity
    
    # Check if guess is contained in actual name
    norm_guess = normalize_name(guess)
    norm_actual = normalize_name(actual)
    
    if len(norm_guess) >= 3 and norm_guess in norm_actual:
        return True, 0.80
    
    return False, max(full_similarity, first_similarity)


# ============================================================
# 🎨 Message Formatting Helpers
# ============================================================

def get_rarity_tier(rarity: int) -> str:
    """Get the tier name for a rarity value."""
    if rarity >= 10:
        return "mythic"
    elif rarity >= 8:
        return "legendary"
    elif rarity >= 6:
        return "epic"
    elif rarity >= 4:
        return "rare"
    else:
        return "common"


def get_catch_reaction(rarity: int) -> str:
    """Get a random reaction emoji based on rarity."""
    tier = get_rarity_tier(rarity)
    reactions = CATCH_REACTIONS.get(tier, CATCH_REACTIONS["common"])
    return random.choice(reactions)


def format_group_name(name: Optional[str]) -> str:
    """Format group name for display."""
    if not name:
        return "ᴛʜɪꜱ ɢʀᴏᴜᴘ"
    
    # Truncate if too long
    if len(name) > 25:
        name = name[:22] + "..."
    
    return name


def create_drop_caption(rarity: int, group_name: str) -> str:
    """Create the beautiful drop message caption."""
    rarity_emoji = get_rarity_emoji(rarity)
    rarity_name, _, _ = rarity_to_text(rarity)
    styled_group = format_group_name(group_name)
    
    # Build the caption with iPhone-quality formatting
    caption = (
        f"{rarity_emoji} {TextStyle.sparkle()} "
        f"{TextStyle.to_small_caps('a character has appeared')} "
        f"{TextStyle.sparkle()} {rarity_emoji}\n\n"
        
        f"╭─────────────────────────╮\n"
        f"│  {TextStyle.to_small_caps('in')} *{styled_group}*\n"
        f"╰─────────────────────────╯\n\n"
        
        f"{TextStyle.heart()} {TextStyle.to_small_caps('capture them and give your')}\n"
        f"    {TextStyle.to_small_caps('harem some aura with')}\n\n"
        
        f"    `/lulucatch <name>`\n\n"
        
        f"╭───── ⋆ ✦ ⋆ ─────╮\n"
        f"│  ✨ *{rarity_name}* ✨\n"
        f"╰───── ⋆ ✦ ⋆ ─────╯"
    )
    
    return caption


def create_catch_success_message(
    user_name: str,
    user_id: int,
    character_name: str,
    anime: str,
    rarity: int,
    is_new: bool = True
) -> str:
    """Create beautiful catch success message."""
    rarity_emoji = get_rarity_emoji(rarity)
    rarity_name, _, _ = rarity_to_text(rarity)
    tier = get_rarity_tier(rarity)
    
    # Different sparkles based on rarity
    if tier in ["legendary", "mythic"]:
        border = "═" * 25
        sparkle = "💎✨🌟"
    elif tier == "epic":
        border = "─" * 25
        sparkle = "⭐✨"
    else:
        border = "─" * 25
        sparkle = "✨"
    
    new_badge = "  🆕 *ɴᴇᴡ ᴄᴀʀᴅ!*" if is_new else ""
    
    message = (
        f"{sparkle} *ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟ ᴄᴀᴛᴄʜ!* {sparkle}\n"
        f"╭{border}╮\n\n"
        
        f"   👤 [{user_name}](tg://user?id={user_id})\n"
        f"   {TextStyle.to_small_caps('has captured')}\n\n"
        
        f"   🎴 *{character_name}*\n"
        f"   📺 _{anime}_\n"
        f"   {rarity_emoji} *{rarity_name}*{new_badge}\n\n"
        
        f"╰{border}╯\n\n"
        
        f"   {TextStyle.heart()} {TextStyle.to_small_caps('added to your harem')} {TextStyle.heart()}"
    )
    
    return message


def create_already_caught_message(
    catcher_name: str,
    catcher_id: int,
    character_name: str
) -> str:
    """Create message when card was already caught."""
    return (
        f"⚡ *ᴛᴏᴏ ꜱʟᴏᴡ!*\n\n"
        f"[{catcher_name}](tg://user?id={catcher_id}) "
        f"{TextStyle.to_small_caps('already caught')} *{character_name}*!\n\n"
        f"💨 {TextStyle.to_small_caps('be faster next time')}..."
    )


def create_wrong_guess_message(similarity: float) -> str:
    """Create message for wrong guess."""
    if similarity >= 0.5:
        hint = f"🤏 {TextStyle.to_small_caps('so close! try again')}..."
    elif similarity >= 0.3:
        hint = f"🤔 {TextStyle.to_small_caps('not quite right')}..."
    else:
        hint = f"❌ {TextStyle.to_small_caps('wrong character name')}"
    
    return hint