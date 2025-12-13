# ============================================================
# 📁 File: handlers/drop.py (Part 1 of 2)
# 📍 Location: telegram_card_bot/handlers/drop.py
# 📝 Description: Drop system with modern UI and auto-reactions
# ============================================================

import asyncio
import random
import re
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from difflib import SequenceMatcher

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from telegram.error import TelegramError
from telegram.constants import ParseMode

# Try to import reactions
try:
    from telegram import ReactionTypeEmoji
    REACTIONS_AVAILABLE = True
except ImportError:
    REACTIONS_AVAILABLE = False

from config import Config
from db import db
from utils.logger import app_logger, error_logger, log_command
from utils.rarity import (
    get_random_rarity,
    rarity_to_text,
    get_catch_reaction,
    get_coin_reward,
    get_xp_reward,
    should_celebrate,
)
from utils.constants import (
    RARITY_EMOJIS,
    RARITY_NAMES,
    PRIMARY_CATCH_REACTION,
)


# ============================================================
# ⚙️ Configuration
# ============================================================

DEFAULT_DROP_THRESHOLD = 50
MIN_DROP_THRESHOLD = 10
MAX_DROP_THRESHOLD = 500
DROP_TIMEOUT = 300  # 5 minutes


# ============================================================
# 📊 State Management
# ============================================================

active_drops: Dict[int, Dict[str, Any]] = {}
message_counters: Dict[int, int] = {}
drop_locks: Dict[int, bool] = {}


# ============================================================
# 🗄️ Database Helpers
# ============================================================

async def get_group_drop_settings(group_id: int) -> Dict[str, Any]:
    """Get group drop settings."""
    try:
        row = await db.fetchrow(
            """
            SELECT drop_threshold, drop_enabled, message_count, last_drop_at 
            FROM groups WHERE group_id = $1
            """,
            group_id
        )
        if row:
            return {
                "threshold": row.get("drop_threshold") or DEFAULT_DROP_THRESHOLD,
                "enabled": row.get("drop_enabled", True),
                "message_count": row.get("message_count") or 0,
                "last_drop_at": row.get("last_drop_at")
            }
    except Exception as e:
        error_logger.error(f"Failed to get drop settings: {e}")
    
    return {
        "threshold": DEFAULT_DROP_THRESHOLD,
        "enabled": True,
        "message_count": 0,
        "last_drop_at": None
    }


async def set_group_drop_threshold(group_id: int, threshold: int) -> bool:
    """Set group drop threshold."""
    try:
        await db.execute(
            """
            INSERT INTO groups (group_id, drop_threshold, drop_enabled, message_count)
            VALUES ($1, $2, TRUE, 0)
            ON CONFLICT (group_id) DO UPDATE SET drop_threshold = $2
            """,
            group_id, threshold
        )
        return True
    except Exception as e:
        error_logger.error(f"Failed to set threshold: {e}")
        return False


async def increment_message_count(group_id: int) -> int:
    """Increment message count for group."""
    try:
        result = await db.fetchval(
            """
            INSERT INTO groups (group_id, message_count, drop_enabled)
            VALUES ($1, 1, TRUE)
            ON CONFLICT (group_id) DO UPDATE 
            SET message_count = COALESCE(groups.message_count, 0) + 1
            RETURNING message_count
            """,
            group_id
        )
        message_counters[group_id] = result or 1
        return result or 1
    except Exception as e:
        error_logger.error(f"Failed to increment count: {e}")
        message_counters[group_id] = message_counters.get(group_id, 0) + 1
        return message_counters[group_id]


async def reset_message_count(group_id: int) -> bool:
    """Reset message count after drop."""
    try:
        await db.execute(
            "UPDATE groups SET message_count = 0, last_drop_at = NOW() WHERE group_id = $1",
            group_id
        )
        message_counters[group_id] = 0
        return True
    except Exception as e:
        error_logger.error(f"Failed to reset count: {e}")
        return False


async def ensure_group_exists(group_id: int, group_name: Optional[str] = None) -> bool:
    """Ensure group exists in database."""
    try:
        await db.execute(
            """
            INSERT INTO groups (group_id, group_name, drop_enabled, message_count)
            VALUES ($1, $2, TRUE, 0)
            ON CONFLICT (group_id) DO UPDATE 
            SET group_name = COALESCE($2, groups.group_name)
            """,
            group_id, group_name
        )
        return True
    except Exception as e:
        error_logger.error(f"Failed to ensure group: {e}")
        return False


async def get_random_card_for_drop() -> Optional[Dict[str, Any]]:
    """Get random card for drop."""
    try:
        rarity = get_random_rarity()
        card = await db.fetchrow(
            """
            SELECT card_id, character_name, anime, rarity, photo_file_id
            FROM cards WHERE rarity = $1 AND is_active = TRUE
            ORDER BY RANDOM() LIMIT 1
            """,
            rarity
        )
        if not card:
            card = await db.fetchrow(
                """
                SELECT card_id, character_name, anime, rarity, photo_file_id
                FROM cards WHERE is_active = TRUE
                ORDER BY RANDOM() LIMIT 1
                """
            )
        return dict(card) if card else None
    except Exception as e:
        error_logger.error(f"Failed to get card: {e}")
        return None


async def record_catch(
    user_id: int,
    card_id: int,
    group_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None
) -> bool:
    """Record a catch in database."""
    try:
        # Ensure user exists
        await db.execute(
            """
            INSERT INTO users (user_id, username, first_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE SET
                username = COALESCE($2, users.username),
                first_name = COALESCE($3, users.first_name)
            """,
            user_id, username, first_name
        )
        
        # Add to collection
        await db.execute(
            """
            INSERT INTO collections (user_id, card_id, caught_at, caught_in_group, quantity)
            VALUES ($1, $2, NOW(), $3, 1)
            ON CONFLICT (user_id, card_id) DO UPDATE SET
                quantity = collections.quantity + 1,
                caught_at = NOW()
            """,
            user_id, card_id, group_id
        )
        
        # Update stats
        await db.execute(
            "UPDATE users SET total_catches = COALESCE(total_catches, 0) + 1 WHERE user_id = $1",
            user_id
        )
        await db.execute(
            "UPDATE groups SET total_catches = COALESCE(total_catches, 0) + 1 WHERE group_id = $1",
            group_id
        )
        await db.execute(
            "UPDATE cards SET total_caught = COALESCE(total_caught, 0) + 1 WHERE card_id = $1",
            card_id
        )
        
        return True
    except Exception as e:
        error_logger.error(f"Failed to record catch: {e}")
        return False


# ============================================================
# 🔤 Name Matching
# ============================================================

def normalize_name(name: str) -> str:
    """Normalize name for comparison."""
    name = name.lower().strip()
    name = re.sub(r'[^\w\s]', '', name)
    name = re.sub(r'\s+', ' ', name)
    return name


def calculate_similarity(name1: str, name2: str) -> float:
    """Calculate similarity between names."""
    norm1 = normalize_name(name1)
    norm2 = normalize_name(name2)
    if norm1 == norm2:
        return 1.0
    return SequenceMatcher(None, norm1, norm2).ratio()


def check_name_match(guess: str, actual_name: str, threshold: float = 0.75) -> Tuple[bool, float]:
    """Check if guess matches actual name."""
    guess = guess.strip()
    actual = actual_name.strip()
    
    # Full name match
    full_sim = calculate_similarity(guess, actual)
    if full_sim >= threshold:
        return True, full_sim
    
    # First name match
    first_name = actual.split()[0] if actual else ""
    first_sim = calculate_similarity(guess, first_name)
    if first_sim >= 0.85:
        return True, first_sim
    
    # Partial match
    norm_guess = normalize_name(guess)
    norm_actual = normalize_name(actual)
    if len(norm_guess) >= 3 and norm_guess in norm_actual:
        return True, 0.80
    
    return False, max(full_sim, first_sim)


# ============================================================
# 🎨 Message Formatters (Clean UI)
# ============================================================

def format_drop_message(card: Dict[str, Any], group_name: Optional[str] = None) -> str:
    """Format drop announcement."""
    rarity = card.get("rarity", 1)
    rarity_name, prob, emoji = rarity_to_text(rarity)
    
    group_display = (group_name[:20] + "...") if group_name and len(group_name) > 20 else (group_name or "this group")
    
    if should_celebrate(rarity):
        return (
            f"✨ *A rare character appeared!* ✨\n\n"
            f"{emoji} {rarity_name}\n"
            f"📍 {group_display}\n\n"
            f"🎯 Type `/lulucatch <name>` to catch!"
        )
    else:
        return (
            f"🎴 *A character appeared!*\n\n"
            f"{emoji} {rarity_name}\n\n"
            f"🎯 Type `/lulucatch <name>` to catch!"
        )


def format_catch_success(
    user_name: str,
    user_id: int,
    card: Dict[str, Any],
    is_new: bool = True
) -> str:
    """Format catch success message."""
    character = card.get("character_name", "Unknown")
    anime = card.get("anime", "Unknown")
    rarity = card.get("rarity", 1)
    card_id = card.get("card_id", 0)
    
    rarity_name, prob, emoji = rarity_to_text(rarity)
    coin_reward = get_coin_reward(rarity)
    
    new_badge = " 🆕" if is_new else ""
    
    if should_celebrate(rarity):
        return (
            f"🎊 {emoji} *{rarity_name.upper()} CATCH!* {emoji} 🎊\n\n"
            f"👤 [{user_name}](tg://user?id={user_id})\n"
            f"🎴 *{character}*{new_badge}\n"
            f"📺 {anime}\n"
            f"💰 +{coin_reward:,} coins\n"
            f"🆔 `#{card_id}`"
        )
    else:
        return (
            f"🎉 *Caught!*{new_badge}\n\n"
            f"👤 [{user_name}](tg://user?id={user_id})\n"
            f"{emoji} *{character}*\n"
            f"📺 {anime}\n"
            f"🆔 `#{card_id}`"
        )


def format_caught_caption(card: Dict[str, Any], user_name: str, user_id: int) -> str:
    """Format caption for caught card image."""
    character = card.get("character_name", "Unknown")
    anime = card.get("anime", "Unknown")
    rarity = card.get("rarity", 1)
    
    emoji = RARITY_EMOJIS.get(rarity, "☘️")
    
    return (
        f"{emoji} *Caught!*\n\n"
        f"🎴 *{character}*\n"
        f"📺 {anime}\n\n"
        f"👤 [{user_name}](tg://user?id={user_id})"
    )


def format_wrong_guess(similarity: float) -> str:
    """Format wrong guess message."""
    if similarity >= 0.5:
        return "🤏 So close! Try again..."
    elif similarity >= 0.3:
        return "🤔 Not quite right..."
    return "❌ Wrong name!"


def format_already_caught(catcher_name: str, catcher_id: int, character: str) -> str:
    """Format already caught message."""
    return (
        f"⚡ *Too slow!*\n\n"
        f"[{catcher_name}](tg://user?id={catcher_id}) already caught *{character}*!"
    )