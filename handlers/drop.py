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


# ============================================================
# 🎮 Command: /setdrop - Set Drop Threshold (Owner Only)
# ============================================================

async def setdrop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /setdrop command - Set message threshold for drops."""
    user = update.effective_user
    chat = update.effective_chat
    
    log_command(user.id, "setdrop", chat.id)
    
    # Only bot owner can use this command
    if not Config.is_admin(user.id):
        await update.message.reply_text(
            f"❌ {TextStyle.to_small_caps('only bot owner can use this command')}",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Check if in group
    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text(
            f"❌ {TextStyle.to_small_caps('this command only works in groups')}",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Get threshold from arguments
    if not context.args:
        # Show current settings
        settings = await get_group_drop_settings(chat.id)
        
        await update.message.reply_text(
            f"⚙️ *ᴅʀᴏᴘ ꜱᴇᴛᴛɪɴɢꜱ*\n\n"
            f"╭─────────────────────────╮\n"
            f"│  📊 *ᴄᴜʀʀᴇɴᴛ ᴛʜʀᴇꜱʜᴏʟᴅ:* `{settings['threshold']}`\n"
            f"│  💬 *ᴍᴇꜱꜱᴀɢᴇ ᴄᴏᴜɴᴛ:* `{settings['message_count']}`\n"
            f"│  ✅ *ᴇɴᴀʙʟᴇᴅ:* `{settings['enabled']}`\n"
            f"╰─────────────────────────╯\n\n"
            f"📝 *ᴜꜱᴀɢᴇ:* `/setdrop <amount>`\n"
            f"📌 *ᴇxᴀᴍᴘʟᴇ:* `/setdrop 50`\n\n"
            f"_{TextStyle.to_small_caps('range')}: {MIN_DROP_THRESHOLD} - {MAX_DROP_THRESHOLD}_",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Parse threshold
    try:
        threshold = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            f"❌ {TextStyle.to_small_caps('please provide a valid number')}",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Validate range
    if threshold < MIN_DROP_THRESHOLD or threshold > MAX_DROP_THRESHOLD:
        await update.message.reply_text(
            f"❌ {TextStyle.to_small_caps('threshold must be between')} "
            f"`{MIN_DROP_THRESHOLD}` {TextStyle.to_small_caps('and')} `{MAX_DROP_THRESHOLD}`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Ensure group exists
    await ensure_group_exists(chat.id, chat.title)
    
    # Set threshold
    success = await set_group_drop_threshold(chat.id, threshold)
    
    if success:
        await update.message.reply_text(
            f"✅ *ᴅʀᴏᴘ ᴛʜʀᴇꜱʜᴏʟᴅ ᴜᴘᴅᴀᴛᴇᴅ!*\n\n"
            f"╭─────────────────────────╮\n"
            f"│  🎯 *ɴᴇᴡ ᴛʜʀᴇꜱʜᴏʟᴅ:* `{threshold}` ᴍꜱɢꜱ\n"
            f"╰─────────────────────────╯\n\n"
            f"✨ {TextStyle.to_small_caps('a card will drop every')} `{threshold}` "
            f"{TextStyle.to_small_caps('messages')}!",
            parse_mode=ParseMode.MARKDOWN
        )
        
        app_logger.info(f"⚙️ Drop threshold set to {threshold} in group {chat.id} by {user.id}")
    else:
        await update.message.reply_text(
            f"❌ {TextStyle.to_small_caps('failed to update settings. please try again.')}",
            parse_mode=ParseMode.MARKDOWN
        )


# ============================================================
# ⏱️ Command: /droptime - Check Remaining Messages
# ============================================================

async def droptime_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /droptime command - Check messages until next drop."""
    user = update.effective_user
    chat = update.effective_chat
    
    log_command(user.id, "droptime", chat.id)
    
    # Check if in group
    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text(
            f"❌ {TextStyle.to_small_caps('this command only works in groups')}",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Get settings
    settings = await get_group_drop_settings(chat.id)
    
    threshold = settings["threshold"]
    current = settings["message_count"]
    remaining = max(0, threshold - current)
    
    # Calculate progress percentage
    progress = min(100, int((current / threshold) * 100)) if threshold > 0 else 0
    
    # Create progress bar
    filled = int(progress / 10)
    empty = 10 - filled
    progress_bar = "▓" * filled + "░" * empty
    
    # Check if there's an active drop
    active_drop = active_drops.get(chat.id)
    active_status = ""
    
    if active_drop:
        active_status = (
            f"\n\n🚨 *ᴀᴄᴛɪᴠᴇ ᴅʀᴏᴘ!*\n"
            f"   {TextStyle.to_small_caps('a character is waiting to be caught')}!\n"
            f"   {TextStyle.to_small_caps('use')} `/lulucatch <name>`"
        )
    
    await update.message.reply_text(
        f"⏱️ *ᴅʀᴏᴘ ꜱᴛᴀᴛᴜꜱ*\n\n"
        f"╭─────────────────────────╮\n"
        f"│  📊 *ᴘʀᴏɢʀᴇꜱꜱ:* {progress}%\n"
        f"│  [{progress_bar}]\n"
        f"│\n"
        f"│  💬 *ᴍᴇꜱꜱᴀɢᴇꜱ:* `{current}` / `{threshold}`\n"
        f"│  ⏳ *ʀᴇᴍᴀɪɴɪɴɢ:* `{remaining}` ᴍꜱɢꜱ\n"
        f"╰─────────────────────────╯"
        f"{active_status}\n\n"
        f"💡 _{TextStyle.to_small_caps('keep chatting to trigger a drop')}!_",
        parse_mode=ParseMode.MARKDOWN
    )


# ============================================================
# 🎴 Spawn Card Drop
# ============================================================

async def spawn_card_drop(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    chat_title: Optional[str] = None
) -> bool:
    """Spawn a random card in the group."""
    try:
        # Check if there's already an active drop
        if chat_id in active_drops:
            # Check if it's expired
            spawned_at = active_drops[chat_id].get("spawned_at")
            if spawned_at and (datetime.now() - spawned_at).seconds < DROP_TIMEOUT:
                return False  # Still active, don't spawn new one
            else:
                # Expired, remove it
                del active_drops[chat_id]
        
        # Get random card
        card = await get_random_card_for_drop()
        
        if not card:
            error_logger.warning(f"No cards available for drop in group {chat_id}")
            return False
        
        # Create caption
        rarity = card["rarity"]
        caption = create_drop_caption(rarity, chat_title)
        
        # Send the card with spoiler
        image_url = card.get("image_url")
        
        if not image_url:
            error_logger.warning(f"Card {card['card_id']} has no image URL")
            return False
        
        # Send photo with spoiler effect
        message = await context.bot.send_photo(
            chat_id=chat_id,
            photo=image_url,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
            has_spoiler=True  # This creates the spoiler effect!
        )
        
        # Store active drop
        active_drops[chat_id] = {
            "card": card,
            "message_id": message.message_id,
            "spawned_at": datetime.now(),
            "caught_by": None,
        }
        
        # Reset message count
        await reset_message_count(chat_id)
        
        app_logger.info(
            f"🎴 Card dropped in group {chat_id}: "
            f"{card['character_name']} ({card['card_id']}) - Rarity: {rarity}"
        )
        
        return True
        
    except TelegramError as e:
        error_logger.error(f"Failed to spawn card drop: {e}")
        return False
    except Exception as e:
        error_logger.error(f"Unexpected error in spawn_card_drop: {e}", exc_info=True)
        return False


# ============================================================
# 🎯 Command: /lulucatch - Catch the Character
# ============================================================

async def lulucatch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /lulucatch command - Attempt to catch a dropped character."""
    user = update.effective_user
    chat = update.effective_chat
    message = update.message
    
    log_command(user.id, "lulucatch", chat.id)
    
    # Check if in group
    if chat.type not in ["group", "supergroup"]:
        await message.reply_text(
            f"❌ {TextStyle.to_small_caps('this command only works in groups')}",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Check if there's an active drop
    drop = active_drops.get(chat.id)
    
    if not drop:
        await message.reply_text(
            f"❌ {TextStyle.to_small_caps('no active drop right now')}!\n\n"
            f"💡 {TextStyle.to_small_caps('wait for a character to appear')}...",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Check if already caught
    if drop.get("caught_by"):
        catcher_id = drop["caught_by"]["user_id"]
        catcher_name = drop["caught_by"]["first_name"]
        character_name = drop["card"]["character_name"]
        
        await message.reply_text(
            create_already_caught_message(catcher_name, catcher_id, character_name),
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Check if drop expired
    spawned_at = drop.get("spawned_at")
    if spawned_at and (datetime.now() - spawned_at).seconds >= DROP_TIMEOUT:
        # Remove expired drop
        del active_drops[chat.id]
        
        await message.reply_text(
            f"⏰ {TextStyle.to_small_caps('this drop has expired')}!\n\n"
            f"💨 {TextStyle.to_small_caps('the character ran away')}...",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Get the guessed name
    if not context.args:
        await message.reply_text(
            f"❌ {TextStyle.to_small_caps('please provide the character name')}!\n\n"
            f"📝 *ᴜꜱᴀɢᴇ:* `/lulucatch <character name>`\n"
            f"📌 *ᴇxᴀᴍᴘʟᴇ:* `/lulucatch Yumeko`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    guess = " ".join(context.args).strip()
    actual_name = drop["card"]["character_name"]
    
    # Check name match
    is_match, similarity = check_name_match(guess, actual_name)
    
    if not is_match:
        # Wrong guess
        hint_msg = create_wrong_guess_message(similarity)
        
        await message.reply_text(
            hint_msg,
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # ✅ Successful catch!
    card = drop["card"]
    card_id = card["card_id"]
    character_name = card["character_name"]
    anime = card["anime"]
    rarity = card["rarity"]
    
    # Mark as caught
    drop["caught_by"] = {
        "user_id": user.id,
        "first_name": user.first_name,
    }
    
    # Record in database
    success = await record_catch(
        user_id=user.id,
        card_id=card_id,
        group_id=chat.id,
        username=user.username,
        first_name=user.first_name
    )
    
    if not success:
        await message.reply_text(
            f"❌ {TextStyle.to_small_caps('error saving catch. please try again.')}",
            parse_mode=ParseMode.MARKDOWN
        )
        # Reset caught status
        drop["caught_by"] = None
        return
    
    # Check if this is a new card for the user
    existing = await db.fetchval(
        """
        SELECT COUNT(*) FROM collections 
        WHERE user_id = $1 AND card_id = $2
        """,
        user.id, card_id
    )
    is_new = (existing == 1)  # Just added, so count is 1
    
    # Create success message
    success_msg = create_catch_success_message(
        user_name=user.first_name,
        user_id=user.id,
        character_name=character_name,
        anime=anime,
        rarity=rarity,
        is_new=is_new
    )
    
    # Send success message
    await message.reply_text(
        success_msg,
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Add reaction to user's message
    try:
        reaction_emoji = get_catch_reaction(rarity)
        await message.set_reaction(
            reaction=[ReactionTypeEmoji(emoji=reaction_emoji)]
        )
    except TelegramError as e:
        # Reactions might not be available in all groups
        app_logger.debug(f"Could not set reaction: {e}")
    except Exception as e:
        app_logger.debug(f"Reaction error: {e}")
    
    # Update the original drop message to show it's caught
    try:
        rarity_emoji = get_rarity_emoji(rarity)
        caught_caption = (
            f"{rarity_emoji} *ᴄᴀᴜɢʜᴛ!* {rarity_emoji}\n\n"
            f"╭─────────────────────────╮\n"
            f"│  🎴 *{character_name}*\n"
            f"│  📺 _{anime}_\n"
            f"│\n"
            f"│  👤 ᴄᴀᴜɢʜᴛ ʙʏ:\n"
            f"│  [{user.first_name}](tg://user?id={user.id})\n"
            f"╰─────────────────────────╯"
        )
        
        await context.bot.edit_message_caption(
            chat_id=chat.id,
            message_id=drop["message_id"],
            caption=caught_caption,
            parse_mode=ParseMode.MARKDOWN
        )
    except TelegramError as e:
        app_logger.debug(f"Could not edit drop message: {e}")
    
    # Remove from active drops after a short delay
    # (keep it for a bit so late catchers get the "already caught" message)
    async def cleanup_drop():
        await asyncio.sleep(30)  # Keep for 30 seconds
        if chat.id in active_drops and active_drops[chat.id].get("caught_by"):
            del active_drops[chat.id]
    
    asyncio.create_task(cleanup_drop())
    
    app_logger.info(
        f"🎯 {user.first_name} ({user.id}) caught {character_name} "
        f"(Card ID: {card_id}, Rarity: {rarity}) in group {chat.id}"
    )


# ============================================================
# 💬 Message Handler - Count Messages & Trigger Drops
# ============================================================

async def message_counter_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Count messages in groups and trigger drops when threshold is reached."""
    # Ignore if not in group
    if not update.effective_chat:
        return
    
    chat = update.effective_chat
    
    if chat.type not in ["group", "supergroup"]:
        return
    
    # Ignore bot messages
    if update.effective_user and update.effective_user.is_bot:
        return
    
    # Ignore commands (they shouldn't count towards drop)
    if update.message and update.message.text and update.message.text.startswith('/'):
        return
    
    try:
        # Ensure group exists
        await ensure_group_exists(chat.id, chat.title)
        
        # Increment message count
        new_count = await increment_message_count(chat.id)
        
        # Get threshold
        settings = await get_group_drop_settings(chat.id)
        threshold = settings["threshold"]
        
        # Check if we should trigger a drop
        if new_count >= threshold:
            # Trigger drop!
            success = await spawn_card_drop(context, chat.id, chat.title)
            
            if success:
                app_logger.info(
                    f"🎴 Auto-drop triggered in group {chat.id} "
                    f"(messages: {new_count}/{threshold})"
                )
    
    except Exception as e:
        error_logger.error(f"Error in message counter: {e}", exc_info=True)


# ============================================================
# 👑 Admin Commands for Drop System
# ============================================================

async def forcedrop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /forcedrop command - Force a card drop (Admin only)."""
    user = update.effective_user
    chat = update.effective_chat
    
    log_command(user.id, "forcedrop", chat.id)
    
    # Only bot owner can use this command
    if not Config.is_admin(user.id):
        await update.message.reply_text(
            f"❌ {TextStyle.to_small_caps('only bot owner can use this command')}",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Check if in group
    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text(
            f"❌ {TextStyle.to_small_caps('this command only works in groups')}",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Check if there's already an active drop
    if chat.id in active_drops:
        drop = active_drops[chat.id]
        if not drop.get("caught_by"):
            await update.message.reply_text(
                f"⚠️ {TextStyle.to_small_caps('there is already an active drop')}!\n\n"
                f"💡 {TextStyle.to_small_caps('use')} `/cleardrop` {TextStyle.to_small_caps('to remove it first')}.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
    
    # Force spawn
    await update.message.reply_text(
        f"🎲 {TextStyle.to_small_caps('forcing a drop')}...",
        parse_mode=ParseMode.MARKDOWN
    )
    
    success = await spawn_card_drop(context, chat.id, chat.title)
    
    if not success:
        await update.message.reply_text(
            f"❌ {TextStyle.to_small_caps('failed to spawn drop. check if cards exist in database.')}",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        app_logger.info(f"🎲 Force drop triggered by admin {user.id} in group {chat.id}")


async def cleardrop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /cleardrop command - Clear active drop (Admin only)."""
    user = update.effective_user
    chat = update.effective_chat
    
    log_command(user.id, "cleardrop", chat.id)
    
    # Only bot owner can use this command
    if not Config.is_admin(user.id):
        await update.message.reply_text(
            f"❌ {TextStyle.to_small_caps('only bot owner can use this command')}",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Check if in group
    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text(
            f"❌ {TextStyle.to_small_caps('this command only works in groups')}",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Check if there's an active drop
    if chat.id not in active_drops:
        await update.message.reply_text(
            f"❌ {TextStyle.to_small_caps('no active drop to clear')}",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Clear the drop
    del active_drops[chat.id]
    
    await update.message.reply_text(
        f"✅ {TextStyle.to_small_caps('active drop cleared')}!",
        parse_mode=ParseMode.MARKDOWN
    )
    
    app_logger.info(f"🗑️ Drop cleared by admin {user.id} in group {chat.id}")


async def dropstats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /dropstats command - View drop statistics (Admin only)."""
    user = update.effective_user
    chat = update.effective_chat
    
    log_command(user.id, "dropstats", chat.id)
    
    # Only bot owner can use this command
    if not Config.is_admin(user.id):
        await update.message.reply_text(
            f"❌ {TextStyle.to_small_caps('only bot owner can use this command')}",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Get all group stats
    try:
        groups = await db.fetch(
            """
            SELECT group_id, group_name, drop_threshold, message_count, 
                   total_catches, total_spawns, drop_enabled
            FROM groups 
            WHERE drop_enabled = TRUE
            ORDER BY total_catches DESC
            LIMIT 10
            """
        )
    except Exception as e:
        error_logger.error(f"Failed to get drop stats: {e}")
        await update.message.reply_text(
            f"❌ {TextStyle.to_small_caps('failed to fetch statistics')}",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    if not groups:
        await update.message.reply_text(
            f"📊 {TextStyle.to_small_caps('no groups with drop system active')}",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Build stats message
    stats_lines = []
    for i, g in enumerate(groups, 1):
        name = g["group_name"] or "Unknown"
        if len(name) > 15:
            name = name[:12] + "..."
        
        catches = g["total_catches"] or 0
        threshold = g["drop_threshold"] or DEFAULT_DROP_THRESHOLD
        current = g["message_count"] or 0
        
        stats_lines.append(
            f"{i}. *{name}*\n"
            f"    🎯 `{catches}` ᴄᴀᴛᴄʜᴇꜱ │ 💬 `{current}`/`{threshold}`"
        )
    
    stats_text = "\n\n".join(stats_lines)
    
    # Count active drops
    active_count = len([d for d in active_drops.values() if not d.get("caught_by")])
    
    await update.message.reply_text(
        f"📊 *ᴅʀᴏᴘ ꜱʏꜱᴛᴇᴍ ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ*\n\n"
        f"╭─────────────────────────╮\n"
        f"│  🌐 *ᴀᴄᴛɪᴠᴇ ɢʀᴏᴜᴘꜱ:* `{len(groups)}`\n"
        f"│  🎴 *ᴀᴄᴛɪᴠᴇ ᴅʀᴏᴘꜱ:* `{active_count}`\n"
        f"╰─────────────────────────╯\n\n"
        f"🏆 *ᴛᴏᴘ ɢʀᴏᴜᴘꜱ ʙʏ ᴄᴀᴛᴄʜᴇꜱ:*\n\n"
        f"{stats_text}",
        parse_mode=ParseMode.MARKDOWN
    )


# ============================================================
# 🔧 Handler Exports
# ============================================================

# Command Handlers
setdrop_handler = CommandHandler("setdrop", setdrop_command)
droptime_handler = CommandHandler("droptime", droptime_command)
lulucatch_handler = CommandHandler("lulucatch", lulucatch_command)
forcedrop_handler = CommandHandler("forcedrop", forcedrop_command)
cleardrop_handler = CommandHandler("cleardrop", cleardrop_command)
dropstats_handler = CommandHandler("dropstats", dropstats_command)

# Message counter (counts all non-command text messages in groups)
message_counter = MessageHandler(
    filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
    message_counter_handler
)

# Export all handlers as a list for easy registration
drop_handlers = [
    setdrop_handler,
    droptime_handler,
    lulucatch_handler,
    forcedrop_handler,
    cleardrop_handler,
    dropstats_handler,
    message_counter,
]