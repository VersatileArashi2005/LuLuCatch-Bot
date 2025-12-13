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

DEFAULT_DROP_THRESHOLD = 90
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
            f"🎯 Type `/lulucatch` to catch!"
        )
    else:
        return (
            f"🎴 *A character appeared!*\n\n"
            f"{emoji} {rarity_name}\n\n"
            f"🎯 Type `/lulucatch` to catch!"
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


# ============================================================
# 🎴 Spawn Drop Function
# ============================================================

async def spawn_card_drop(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    chat_title: Optional[str] = None
) -> bool:
    """Spawn a card drop in group."""
    
    # Check lock
    if drop_locks.get(chat_id, False):
        return False
    
    drop_locks[chat_id] = True
    
    try:
        # Check existing drop
        if chat_id in active_drops:
            existing = active_drops[chat_id]
            spawned_at = existing.get("spawned_at")
            if spawned_at and (datetime.now() - spawned_at).seconds < DROP_TIMEOUT:
                drop_locks[chat_id] = False
                return False
            del active_drops[chat_id]
        
        # Reset count first
        await reset_message_count(chat_id)
        
        # Get card
        card = await get_random_card_for_drop()
        if not card:
            error_logger.warning(f"No cards for drop in {chat_id}")
            drop_locks[chat_id] = False
            return False
        
        photo_id = card.get("photo_file_id")
        if not photo_id:
            error_logger.warning(f"Card {card['card_id']} has no photo")
            drop_locks[chat_id] = False
            return False
        
        # Format message
        caption = format_drop_message(card, chat_title)
        
        # Send with spoiler
        message = await context.bot.send_photo(
            chat_id=chat_id,
            photo=photo_id,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
            has_spoiler=True
        )
        
        # Store active drop
        active_drops[chat_id] = {
            "card": card,
            "message_id": message.message_id,
            "spawned_at": datetime.now(),
            "caught_by": None
        }
        
        rarity = card.get("rarity", 1)
        emoji = RARITY_EMOJIS.get(rarity, "☘️")
        app_logger.info(f"🎴 Drop: {card['character_name']} ({emoji}) in {chat_id}")
        
        drop_locks[chat_id] = False
        return True
        
    except TelegramError as e:
        error_logger.error(f"Drop spawn failed: {e}")
        drop_locks[chat_id] = False
        return False
    except Exception as e:
        error_logger.error(f"Unexpected drop error: {e}", exc_info=True)
        drop_locks[chat_id] = False
        return False


# ============================================================
# 📝 Command Handlers
# ============================================================

async def setdrop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /setdrop command."""
    user = update.effective_user
    chat = update.effective_chat
    
    log_command(user.id, "setdrop", chat.id)
    
    if not Config.is_admin(user.id):
        await update.message.reply_text("🚫 Admin only.", parse_mode=ParseMode.MARKDOWN)
        return
    
    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❌ Groups only.", parse_mode=ParseMode.MARKDOWN)
        return
    
    if not context.args:
        settings = await get_group_drop_settings(chat.id)
        progress = min(100, int((settings['message_count'] / settings['threshold']) * 100)) if settings['threshold'] > 0 else 0
        
        await update.message.reply_text(
            f"⚙️ *Drop Settings*\n\n"
            f"📊 Threshold: `{settings['threshold']}` messages\n"
            f"💬 Current: `{settings['message_count']}` ({progress}%)\n"
            f"✅ Enabled: `{settings['enabled']}`\n\n"
            f"Usage: `/setdrop <number>`\n"
            f"Range: {MIN_DROP_THRESHOLD}-{MAX_DROP_THRESHOLD}",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    try:
        threshold = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid number.", parse_mode=ParseMode.MARKDOWN)
        return
    
    if threshold < MIN_DROP_THRESHOLD or threshold > MAX_DROP_THRESHOLD:
        await update.message.reply_text(
            f"❌ Must be {MIN_DROP_THRESHOLD}-{MAX_DROP_THRESHOLD}.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    await ensure_group_exists(chat.id, chat.title)
    
    if await set_group_drop_threshold(chat.id, threshold):
        await update.message.reply_text(
            f"✅ *Drop threshold set to* `{threshold}` *messages*",
            parse_mode=ParseMode.MARKDOWN
        )
        app_logger.info(f"⚙️ Drop threshold: {threshold} in {chat.id} by {user.id}")
    else:
        await update.message.reply_text("❌ Failed to update.", parse_mode=ParseMode.MARKDOWN)


async def droptime_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /droptime command."""
    user = update.effective_user
    chat = update.effective_chat
    
    log_command(user.id, "droptime", chat.id)
    
    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❌ Groups only.", parse_mode=ParseMode.MARKDOWN)
        return
    
    settings = await get_group_drop_settings(chat.id)
    threshold = settings["threshold"]
    current = settings["message_count"]
    remaining = max(0, threshold - current)
    progress = min(100, int((current / threshold) * 100)) if threshold > 0 else 0
    
    # Progress bar
    filled = progress // 5
    bar = "●" * filled + "○" * (20 - filled)
    
    # Active drop status
    active_text = ""
    if chat.id in active_drops and not active_drops[chat.id].get("caught_by"):
        active_text = "\n\n🚨 *Active drop!* Use `/lulucatch <name>`"
    
    await update.message.reply_text(
        f"⏱️ *Drop Status*\n\n"
        f"`{bar}` {progress}%\n\n"
        f"💬 `{current}` / `{threshold}` messages\n"
        f"⏳ `{remaining}` remaining{active_text}",
        parse_mode=ParseMode.MARKDOWN
    )


async def lulucatch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /lulucatch command with auto-reaction."""
    user = update.effective_user
    chat = update.effective_chat
    message = update.message
    
    log_command(user.id, "lulucatch", chat.id)
    
    if chat.type not in ["group", "supergroup"]:
        await message.reply_text("❌ Groups only.", parse_mode=ParseMode.MARKDOWN)
        return
    
    # Check active drop
    drop = active_drops.get(chat.id)
    if not drop:
        await message.reply_text(
            "❌ *No active drop!*\n\n"
            "Wait for a character to appear...",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Check if already caught
    if drop.get("caught_by"):
        catcher = drop["caught_by"]
        await message.reply_text(
            format_already_caught(
                catcher["first_name"],
                catcher["user_id"],
                drop["card"]["character_name"]
            ),
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Check timeout
    spawned_at = drop.get("spawned_at")
    if spawned_at and (datetime.now() - spawned_at).seconds >= DROP_TIMEOUT:
        del active_drops[chat.id]
        await message.reply_text(
            "⏰ *Drop expired!*\n\nThe character ran away...",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Check guess
    if not context.args:
        await message.reply_text(
            "❌ Provide the name!\n\n"
            "Usage: `/lulucatch <name>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    guess = " ".join(context.args).strip()
    actual_name = drop["card"]["character_name"]
    
    is_match, similarity = check_name_match(guess, actual_name)
    
    if not is_match:
        await message.reply_text(
            format_wrong_guess(similarity),
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # === SUCCESSFUL CATCH ===
    
    card = drop["card"]
    card_id = card["card_id"]
    character = card["character_name"]
    rarity = card["rarity"]
    
    # Mark as caught
    drop["caught_by"] = {
        "user_id": user.id,
        "first_name": user.first_name
    }
    
    # Record in database
    coin_reward = get_coin_reward(rarity)
    xp_reward = get_xp_reward(rarity)
    
    if not await record_catch(user.id, card_id, chat.id, user.username, user.first_name):
        await message.reply_text("❌ Error saving. Try again.", parse_mode=ParseMode.MARKDOWN)
        drop["caught_by"] = None
        return
    
    # Add coins
    try:
        await db.execute(
            "UPDATE users SET coins = COALESCE(coins, 0) + $2 WHERE user_id = $1",
            user.id, coin_reward
        )
    except Exception:
        pass
    
    # Check if new card
    try:
        count = await db.fetchval(
            "SELECT quantity FROM collections WHERE user_id = $1 AND card_id = $2",
            user.id, card_id
        )
        is_new = (count == 1)
    except Exception:
        is_new = True
    
    # Send success message
    await message.reply_text(
        format_catch_success(user.first_name, user.id, card, is_new),
        parse_mode=ParseMode.MARKDOWN
    )
    
    # === AUTO-REACTION ===
    if REACTIONS_AVAILABLE and Config.ENABLE_CATCH_REACTIONS:
        try:
            reaction_emoji = get_catch_reaction(rarity)
            await message.set_reaction(reaction=[ReactionTypeEmoji(emoji=reaction_emoji)])
        except Exception as e:
            app_logger.debug(f"Could not set reaction: {e}")
    
    # Update drop message
    try:
        await context.bot.edit_message_caption(
            chat_id=chat.id,
            message_id=drop["message_id"],
            caption=format_caught_caption(card, user.first_name, user.id),
            parse_mode=ParseMode.MARKDOWN
        )
    except TelegramError:
        pass
    
    emoji = RARITY_EMOJIS.get(rarity, "☘️")
    app_logger.info(f"🎯 {user.first_name} caught {character} ({emoji}) in {chat.id}")
    
    # Cleanup after delay
    async def cleanup():
        await asyncio.sleep(30)
        if chat.id in active_drops and active_drops[chat.id].get("caught_by"):
            del active_drops[chat.id]
    
    asyncio.create_task(cleanup())


async def forcedrop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /forcedrop command."""
    user = update.effective_user
    chat = update.effective_chat
    
    log_command(user.id, "forcedrop", chat.id)
    
    if not Config.is_admin(user.id):
        await update.message.reply_text("🚫 Admin only.", parse_mode=ParseMode.MARKDOWN)
        return
    
    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❌ Groups only.", parse_mode=ParseMode.MARKDOWN)
        return
    
    # Check existing drop
    if chat.id in active_drops and not active_drops[chat.id].get("caught_by"):
        await update.message.reply_text(
            "⚠️ Active drop exists!\n\nUse `/cleardrop` first.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    await update.message.reply_text("🎲 Forcing drop...", parse_mode=ParseMode.MARKDOWN)
    
    if await spawn_card_drop(context, chat.id, chat.title):
        app_logger.info(f"🎲 Force drop by {user.id} in {chat.id}")
    else:
        await update.message.reply_text("❌ Failed. Check if cards exist.", parse_mode=ParseMode.MARKDOWN)


async def cleardrop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /cleardrop command."""
    user = update.effective_user
    chat = update.effective_chat
    
    log_command(user.id, "cleardrop", chat.id)
    
    if not Config.is_admin(user.id):
        await update.message.reply_text("🚫 Admin only.", parse_mode=ParseMode.MARKDOWN)
        return
    
    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❌ Groups only.", parse_mode=ParseMode.MARKDOWN)
        return
    
    if chat.id not in active_drops:
        await update.message.reply_text("❌ No active drop.", parse_mode=ParseMode.MARKDOWN)
        return
    
    del active_drops[chat.id]
    await update.message.reply_text("✅ Drop cleared!", parse_mode=ParseMode.MARKDOWN)
    app_logger.info(f"🗑️ Drop cleared by {user.id} in {chat.id}")


async def dropstats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /dropstats command."""
    user = update.effective_user
    
    log_command(user.id, "dropstats", update.effective_chat.id)
    
    if not Config.is_admin(user.id):
        await update.message.reply_text("🚫 Admin only.", parse_mode=ParseMode.MARKDOWN)
        return
    
    try:
        groups = await db.fetch(
            """
            SELECT group_id, group_name, drop_threshold, message_count, total_catches
            FROM groups WHERE drop_enabled = TRUE
            ORDER BY total_catches DESC LIMIT 10
            """
        )
    except Exception as e:
        error_logger.error(f"Dropstats failed: {e}")
        await update.message.reply_text("❌ Failed to fetch.", parse_mode=ParseMode.MARKDOWN)
        return
    
    if not groups:
        await update.message.reply_text("📊 No active groups.", parse_mode=ParseMode.MARKDOWN)
        return
    
    lines = []
    for i, g in enumerate(groups, 1):
        name = (g.get("group_name") or "Unknown")[:15]
        catches = g.get("total_catches") or 0
        lines.append(f"{i}. {name} • 🎯 {catches}")
    
    active_count = len([d for d in active_drops.values() if not d.get("caught_by")])
    
    await update.message.reply_text(
        f"📊 *Drop Stats*\n\n"
        f"🌐 Groups: `{len(groups)}`\n"
        f"🎴 Active drops: `{active_count}`\n\n"
        f"*Top Groups:*\n" + "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN
    )


# ============================================================
# 💬 Message Counter Handler
# ============================================================

async def message_counter_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Count messages for auto-drops."""
    chat = update.effective_chat
    
    if not chat or chat.type not in ["group", "supergroup"]:
        return
    
    # Skip bots
    if update.effective_user and update.effective_user.is_bot:
        return
    
    # Skip commands
    if update.message and update.message.text and update.message.text.startswith('/'):
        return
    
    # Skip if active drop
    if chat.id in active_drops and not active_drops[chat.id].get("caught_by"):
        return
    
    # Skip if processing
    if drop_locks.get(chat.id, False):
        return
    
    try:
        await ensure_group_exists(chat.id, chat.title)
        new_count = await increment_message_count(chat.id)
        settings = await get_group_drop_settings(chat.id)
        
        if new_count >= settings["threshold"]:
            if await spawn_card_drop(context, chat.id, chat.title):
                app_logger.info(f"🎴 Auto-drop in {chat.id} ({new_count}/{settings['threshold']})")
    except Exception as e:
        error_logger.error(f"Message counter error: {e}")


# ============================================================
# 🔧 Handler Exports
# ============================================================

setdrop_handler = CommandHandler("setdrop", setdrop_command)
droptime_handler = CommandHandler("droptime", droptime_command)
lulucatch_handler = CommandHandler("lulucatch", lulucatch_command)
forcedrop_handler = CommandHandler("forcedrop", forcedrop_command)
cleardrop_handler = CommandHandler("cleardrop", cleardrop_command)
dropstats_handler = CommandHandler("dropstats", dropstats_command)

message_counter = MessageHandler(
    filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
    message_counter_handler
)

# Export list
drop_handlers = [
    setdrop_handler,
    droptime_handler,
    lulucatch_handler,
    forcedrop_handler,
    cleardrop_handler,
    dropstats_handler,
    message_counter
]