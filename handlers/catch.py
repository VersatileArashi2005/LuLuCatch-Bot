# ============================================================
# 📁 File: handlers/catch.py
# 📍 Location: telegram_card_bot/handlers/catch.py
# 📝 Description: Card catching system with timed buttons
# ============================================================

import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import random

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from telegram.error import TelegramError, BadRequest
from telegram.constants import ChatType

from config import Config
from db import (
    db,
    ensure_user,
    get_random_card,
    get_card_by_id,
    add_to_collection,
    update_user_stats,
    increment_card_caught,
    ensure_group,
    update_group_spawn,
    clear_group_spawn,
    get_group_by_id,
    get_card_count,
)
from utils.logger import app_logger, error_logger, log_command, log_card_catch
from utils.rarity import (
    get_random_rarity,
    rarity_to_text,
    format_rarity_display,
    get_rarity_emoji,
    calculate_rarity_value,
    RARITY_TABLE,
)


# ============================================================
# ⏱️ Cooldown Management
# ============================================================

# Store cooldowns per group: {group_id: datetime}
_group_cooldowns: Dict[int, datetime] = {}

# Store active spawns: {group_id: {"card_id": int, "message_id": int, "expires": datetime}}
_active_spawns: Dict[int, Dict[str, Any]] = {}

# Catch timeout in seconds
CATCH_TIMEOUT_SECONDS = 10


def check_group_cooldown(group_id: int) -> tuple[bool, int]:
    """
    Check if a group is on spawn cooldown.
    
    Args:
        group_id: Telegram chat ID
        
    Returns:
        Tuple of (is_on_cooldown: bool, seconds_remaining: int)
    """
    if group_id not in _group_cooldowns:
        return False, 0
    
    last_spawn = _group_cooldowns[group_id]
    elapsed = (datetime.now() - last_spawn).total_seconds()
    cooldown = Config.COOLDOWN_SECONDS
    
    if elapsed < cooldown:
        remaining = int(cooldown - elapsed)
        return True, remaining
    
    return False, 0


def set_group_cooldown(group_id: int) -> None:
    """Set the spawn cooldown for a group."""
    _group_cooldowns[group_id] = datetime.now()


def get_active_spawn(group_id: int) -> Optional[Dict[str, Any]]:
    """Get the active spawn for a group."""
    spawn = _active_spawns.get(group_id)
    
    if spawn and datetime.now() < spawn["expires"]:
        return spawn
    
    # Spawn expired, remove it
    _active_spawns.pop(group_id, None)
    return None


def set_active_spawn(group_id: int, card_id: int, message_id: int) -> None:
    """Set an active spawn for a group."""
    _active_spawns[group_id] = {
        "card_id": card_id,
        "message_id": message_id,
        "expires": datetime.now() + timedelta(seconds=CATCH_TIMEOUT_SECONDS),
        "caught_by": None,
    }


def clear_active_spawn(group_id: int) -> None:
    """Clear the active spawn for a group."""
    _active_spawns.pop(group_id, None)


def mark_spawn_caught(group_id: int, user_id: int) -> bool:
    """
    Mark a spawn as caught by a user.
    
    Returns:
        True if successfully marked, False if already caught or expired
    """
    spawn = _active_spawns.get(group_id)
    
    if not spawn:
        return False
    
    if spawn["caught_by"] is not None:
        return False
    
    if datetime.now() >= spawn["expires"]:
        return False
    
    spawn["caught_by"] = user_id
    return True


# ============================================================
# 🎴 Spawn Card Function
# ============================================================

async def spawn_card_in_group(
    context: ContextTypes.DEFAULT_TYPE,
    group_id: int,
    force: bool = False
) -> Optional[Message]:
    """
    Spawn a random card in a group.
    
    Args:
        context: Bot context
        group_id: Target group chat ID
        force: Bypass cooldown check
        
    Returns:
        Sent message or None if failed
    """
    # ========================================
    # Check cooldown (unless forced)
    # ========================================
    if not force:
        is_cooldown, remaining = check_group_cooldown(group_id)
        if is_cooldown:
            app_logger.debug(f"Group {group_id} on cooldown ({remaining}s remaining)")
            return None
    
    # ========================================
    # Check for active spawn
    # ========================================
    if get_active_spawn(group_id):
        app_logger.debug(f"Group {group_id} already has an active spawn")
        return None
    
    # ========================================
    # Get random card from database
    # ========================================
    # First, generate a random rarity
    rarity_id = get_random_rarity()
    
    # Try to get a card with that rarity
    card = await get_random_card(None, rarity=rarity_id)
    
    # If no card with that rarity, get any random card
    if not card:
        card = await get_random_card(None)
    
    if not card:
        app_logger.warning(f"No cards in database to spawn in group {group_id}")
        return None
    
    # ========================================
    # Build spawn message
    # ========================================
    card_id = card["card_id"]
    anime = card["anime"]
    character = card["character_name"]
    rarity = card["rarity"]
    photo_file_id = card["photo_file_id"]
    
    rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity)
    
    # Calculate value (for display)
    value = calculate_rarity_value(rarity)
    
    spawn_text = (
        "🎴 *A Wild Card Appeared!*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎬 *Anime:* {anime}\n"
        f"✨ *Rarity:* {rarity_emoji} {rarity_name}\n"
        f"💰 *Value:* {value:,} coins\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⏱️ *{CATCH_TIMEOUT_SECONDS} seconds* to catch!\n"
        "Click the button below or guess the name!"
    )
    
    # Create catch buttons
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎯 Catch!",
                callback_data=f"catch_{group_id}_{card_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                "⏭️ Skip",
                callback_data=f"skip_{group_id}"
            ),
        ],
    ])
    
    # ========================================
    # Send spawn message
    # ========================================
    try:
        message = await context.bot.send_photo(
            chat_id=group_id,
            photo=photo_file_id,
            caption=spawn_text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        
        # ========================================
        # Set active spawn and cooldown
        # ========================================
        set_active_spawn(group_id, card_id, message.message_id)
        set_group_cooldown(group_id)
        
        # Update database
        await update_group_spawn(None, group_id, card_id, message.message_id)
        
        app_logger.info(
            f"🎴 Card spawned in group {group_id}: "
            f"{character} ({rarity_emoji} {rarity_name})"
        )
        
        # ========================================
        # Schedule expiration handler
        # ========================================
        asyncio.create_task(
            handle_spawn_expiration(context, group_id, message.message_id, card_id)
        )
        
        return message
        
    except TelegramError as e:
        error_logger.error(f"Failed to spawn card in group {group_id}: {e}")
        return None


async def handle_spawn_expiration(
    context: ContextTypes.DEFAULT_TYPE,
    group_id: int,
    message_id: int,
    card_id: int
) -> None:
    """
    Handle spawn expiration after timeout.
    
    Waits for the timeout period, then disables buttons if not caught.
    """
    await asyncio.sleep(CATCH_TIMEOUT_SECONDS)
    
    # Check if spawn was caught
    spawn = _active_spawns.get(group_id)
    
    if spawn and spawn["message_id"] == message_id and spawn["caught_by"] is None:
        # Spawn expired without being caught
        try:
            # Get card info for the expired message
            card = await get_card_by_id(None, card_id)
            
            if card:
                character = card["character_name"]
                anime = card["anime"]
                rarity = card["rarity"]
                rarity_emoji = get_rarity_emoji(rarity)
                
                expired_text = (
                    "⏳ *Time's Up!*\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 *Character:* {character}\n"
                    f"🎬 *Anime:* {anime}\n"
                    f"✨ *Rarity:* {rarity_emoji}\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "💨 The card disappeared..."
                )
            else:
                expired_text = (
                    "⏳ *Time's Up!*\n\n"
                    "💨 The card disappeared..."
                )
            
            # Disable buttons
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⏳ Expired", callback_data="expired")]
            ])
            
            await context.bot.edit_message_caption(
                chat_id=group_id,
                message_id=message_id,
                caption=expired_text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            
            app_logger.info(f"⏳ Card spawn expired in group {group_id}")
            
        except BadRequest as e:
            # Message was already modified or deleted
            app_logger.debug(f"Could not update expired message: {e}")
        except TelegramError as e:
            error_logger.error(f"Error updating expired spawn: {e}")
        
        # Clear the spawn
        clear_active_spawn(group_id)
        await clear_group_spawn(None, group_id)


# ============================================================
# 🎯 Catch Command Handler
# ============================================================

async def catch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /catch command - Spawn a card or catch active one.
    
    In groups: Spawns a new card if none active
    In PM: Shows help message
    """
    user = update.effective_user
    chat = update.effective_chat
    message = update.message
    
    log_command(user.id, "catch", chat.id)
    
    # ========================================
    # Ensure user exists
    # ========================================
    await ensure_user(
        pool=None,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    # ========================================
    # Private chat - show help
    # ========================================
    if chat.type == ChatType.PRIVATE:
        await message.reply_text(
            "🎯 *Catch Command*\n\n"
            "This command works in groups!\n\n"
            "When a card spawns in a group:\n"
            "• Click the *Catch* button\n"
            "• Or type the character's name\n\n"
            "First person to catch gets the card! 🎴",
            parse_mode="Markdown"
        )
        return
    
    # ========================================
    # Group chat - check for active spawn
    # ========================================
    group_id = chat.id
    
    # Ensure group exists in database
    await ensure_group(None, group_id, chat.title)
    
    # Check for active spawn
    spawn = get_active_spawn(group_id)
    
    if spawn:
        # There's an active spawn - try to catch it
        card_id = spawn["card_id"]
        
        # Check if already caught
        if spawn["caught_by"] is not None:
            await message.reply_text(
                "❌ This card was already caught!",
                parse_mode="Markdown"
            )
            return
        
        # Attempt to catch
        if mark_spawn_caught(group_id, user.id):
            await process_catch(update, context, group_id, card_id, user.id)
        else:
            await message.reply_text(
                "❌ Too late! The card was already caught or expired.",
                parse_mode="Markdown"
            )
        return
    
    # ========================================
    # No active spawn - try to spawn one
    # ========================================
    
    # Check cooldown
    is_cooldown, remaining = check_group_cooldown(group_id)
    if is_cooldown:
        await message.reply_text(
            f"⏳ *Please Wait*\n\n"
            f"Next card in *{remaining}* seconds...\n\n"
            f"💡 Cards spawn automatically every {Config.COOLDOWN_SECONDS}s!",
            parse_mode="Markdown"
        )
        return
    
    # Check if there are any cards
    total_cards = await get_card_count(None)
    if total_cards == 0:
        await message.reply_text(
            "❌ *No Cards Available*\n\n"
            "There are no cards in the database yet.\n"
            "Ask an admin to upload some cards first!",
            parse_mode="Markdown"
        )
        return
    
    # Spawn a new card
    spawn_message = await spawn_card_in_group(context, group_id, force=True)
    
    if not spawn_message:
        await message.reply_text(
            "❌ Failed to spawn a card. Please try again.",
            parse_mode="Markdown"
        )


# ============================================================
# 🎯 Catch Callback Handler
# ============================================================

async def catch_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle catch button clicks.
    """
    query = update.callback_query
    user = query.from_user
    data = query.data
    
    # ========================================
    # Parse callback data
    # ========================================
    
    # Handle expired button
    if data == "expired":
        await query.answer("⏳ This card has expired!", show_alert=True)
        return
    
    # Handle skip button
    if data.startswith("skip_"):
        await query.answer("⏭️ You skipped this card.", show_alert=False)
        return
    
    # Handle catch button: catch_{group_id}_{card_id}
    if not data.startswith("catch_"):
        return
    
    try:
        parts = data.split("_")
        group_id = int(parts[1])
        card_id = int(parts[2])
    except (IndexError, ValueError):
        await query.answer("❌ Invalid action.", show_alert=True)
        return
    
    # ========================================
    # Check active spawn
    # ========================================
    spawn = get_active_spawn(group_id)
    
    if not spawn:
        await query.answer("⏳ This card has expired!", show_alert=True)
        return
    
    if spawn["card_id"] != card_id:
        await query.answer("❌ This card is no longer available.", show_alert=True)
        return
    
    if spawn["caught_by"] is not None:
        catcher_id = spawn["caught_by"]
        if catcher_id == user.id:
            await query.answer("✅ You already caught this card!", show_alert=True)
        else:
            await query.answer("❌ Someone else caught this card!", show_alert=True)
        return
    
    # ========================================
    # Attempt to catch
    # ========================================
    if not mark_spawn_caught(group_id, user.id):
        await query.answer("❌ Failed to catch! Someone was faster.", show_alert=True)
        return
    
    await query.answer("🎉 You caught the card!", show_alert=True)
    
    # ========================================
    # Process the catch
    # ========================================
    await process_catch(update, context, group_id, card_id, user.id, is_callback=True)


async def process_catch(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    group_id: int,
    card_id: int,
    user_id: int,
    is_callback: bool = False
) -> None:
    """
    Process a successful card catch.
    
    Args:
        update: Telegram update
        context: Bot context
        group_id: Group where card was caught
        card_id: Caught card ID
        user_id: User who caught the card
        is_callback: Whether this was triggered by a callback
    """
    # ========================================
    # Get user info
    # ========================================
    if is_callback:
        user = update.callback_query.from_user
        message = update.callback_query.message
    else:
        user = update.effective_user
        message = update.message
    
    # ========================================
    # Ensure user exists
    # ========================================
    await ensure_user(
        pool=None,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    # ========================================
    # Get card info
    # ========================================
    card = await get_card_by_id(None, card_id)
    
    if not card:
        error_logger.error(f"Card {card_id} not found during catch")
        return
    
    anime = card["anime"]
    character = card["character_name"]
    rarity = card["rarity"]
    photo_file_id = card["photo_file_id"]
    
    rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity)
    value = calculate_rarity_value(rarity)
    
    # ========================================
    # Add card to collection
    # ========================================
    try:
        await add_to_collection(None, user.id, card_id, group_id)
        await increment_card_caught(None, card_id)
        await update_user_stats(None, user.id, coins_delta=value, catches_delta=1)
        
        log_card_catch(user.id, character, rarity_name)
        
    except Exception as e:
        error_logger.error(f"Failed to add card to collection: {e}", exc_info=True)
        return
    
    # ========================================
    # Clear the spawn
    # ========================================
    clear_active_spawn(group_id)
    await clear_group_spawn(None, group_id)
    
    # ========================================
    # Update the spawn message
    # ========================================
    success_text = (
        f"🎉 *Card Caught!*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Character:* {character}\n"
        f"🎬 *Anime:* {anime}\n"
        f"✨ *Rarity:* {rarity_emoji} {rarity_name}\n"
        f"💰 *Value:* +{value:,} coins\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏆 *Caught by:* [{user.first_name}](tg://user?id={user.id})"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎴 View Collection", url=f"t.me/{Config.BOT_USERNAME}?start=harem")]
    ])
    
    try:
        # Get the spawn message to edit
        spawn = _active_spawns.get(group_id)
        if spawn and is_callback:
            await message.edit_caption(
                caption=success_text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        elif spawn:
            await context.bot.edit_message_caption(
                chat_id=group_id,
                message_id=spawn["message_id"],
                caption=success_text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
    except BadRequest as e:
        app_logger.debug(f"Could not edit catch message: {e}")
    except TelegramError as e:
        error_logger.error(f"Error updating catch message: {e}")
    
    # ========================================
    # Send congratulations message
    # ========================================
    congrats_text = (
        f"🎊 *Congratulations {user.first_name}!*\n\n"
        f"You caught {rarity_emoji} *{character}* from _{anime}_!\n\n"
        f"💰 *+{value:,}* coins added to your balance!"
    )
    
    if not is_callback:
        await message.reply_text(congrats_text, parse_mode="Markdown")


# ============================================================
# 📝 Name Guessing Handler
# ============================================================

async def name_guess_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle text messages in groups as potential name guesses.
    
    Users can catch cards by typing the character's name.
    """
    message = update.message
    chat = update.effective_chat
    user = update.effective_user
    
    # Only process in groups
    if chat.type == ChatType.PRIVATE:
        return
    
    group_id = chat.id
    guess = message.text.strip().lower()
    
    # Check for active spawn
    spawn = get_active_spawn(group_id)
    
    if not spawn:
        return
    
    if spawn["caught_by"] is not None:
        return
    
    # Get card info
    card = await get_card_by_id(None, spawn["card_id"])
    
    if not card:
        return
    
    character_name = card["character_name"].lower()
    
    # Check if guess matches (partial or full match)
    # Allow matching first name or full name
    name_parts = character_name.split()
    is_match = (
        guess == character_name or
        guess in name_parts or
        any(part.startswith(guess) for part in name_parts if len(guess) >= 3)
    )
    
    if is_match:
        # User guessed correctly!
        if mark_spawn_caught(group_id, user.id):
            await message.reply_text(f"🎯 *Correct!* You guessed the name!", parse_mode="Markdown")
            await process_catch(update, context, group_id, spawn["card_id"], user.id)


# ============================================================
# 🔧 Force Spawn Command (Admin)
# ============================================================

async def force_spawn_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /forcespawn command - Admin force spawn.
    """
    user = update.effective_user
    chat = update.effective_chat
    
    if not Config.is_admin(user.id):
        await update.message.reply_text("❌ Admin only command.")
        return
    
    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text("❌ Use this command in a group.")
        return
    
    # Force spawn
    spawn_message = await spawn_card_in_group(context, chat.id, force=True)
    
    if spawn_message:
        app_logger.info(f"🎴 Force spawn by admin {user.id} in group {chat.id}")
    else:
        total = await get_card_count(None)
        if total == 0:
            await update.message.reply_text("❌ No cards in database!")
        else:
            await update.message.reply_text("❌ Failed to spawn. Try again.")


# ============================================================
# 🔧 Command Handlers Export
# ============================================================

catch_command_handler = CommandHandler("catch", catch_command)
force_spawn_handler = CommandHandler("forcespawn", force_spawn_command)
name_guess_message_handler = MessageHandler(
    filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
    name_guess_handler
)