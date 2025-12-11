# ============================================================
# 📁 File: handlers/catch.py
# 📍 Location: telegram_card_bot/handlers/catch.py
# 📝 Description: Card catching system with battle mechanic
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
    get_rarity_emoji,
    calculate_rarity_value,
    RARITY_TABLE,
)


# ============================================================
# ⚔️ Battle Configuration
# ============================================================

# Cooldown: 4 minutes (240 seconds)
CATCH_COOLDOWN_SECONDS = 240
CATCH_TIMEOUT_SECONDS = 60  # Time to click the battle button

# Win chance percentage (50% = fair fight)
WIN_CHANCE = 50

# Victory Messages 🏆
WIN_MESSAGES = [
    "⚔️ **LEGENDARY VICTORY!** ⚔️\n\n"
    "The ground trembles as you strike! {card_name} falls to their knees!\n"
    "\"You... you're too powerful!\" they whisper in awe.\n\n"
    "🏆 **THE CARD IS YOURS, CHAMPION!** 🏆",
    
    "🔥 **FLAWLESS TRIUMPH!** 🔥\n\n"
    "With a battle cry that echoes through the heavens, you unleash your ultimate attack!\n"
    "{card_name} never stood a chance!\n\n"
    "👑 **KNEEL BEFORE THE VICTOR!** 👑",
    
    "✨ **DESTINED VICTORY!** ✨\n\n"
    "The stars aligned for this moment! Your fist connects perfectly!\n"
    "{card_name} is sent flying across the battlefield!\n\n"
    "🌟 **FATE CHOSE YOU AS THE WINNER!** 🌟",
    
    "💪 **OVERWHELMING POWER!** 💪\n\n"
    "You didn't just win... you DOMINATED!\n"
    "{card_name} bows before your unmatched strength!\n\n"
    "⚡ **ABSOLUTE CONQUEST!** ⚡",
    
    "🎯 **PERFECT EXECUTION!** 🎯\n\n"
    "One strike. That's all it took.\n"
    "{card_name} collapses in defeat, acknowledging your supremacy!\n\n"
    "🎖️ **MASTERFUL VICTORY!** 🎖️"
]

# Defeat Messages 💀
LOSE_MESSAGES = [
    "💀 **CRUSHING DEFEAT!** 💀\n\n"
    "{card_name} looks at you with pity...\n"
    "\"Was that seriously your best shot?\" they laugh.\n\n"
    "😭 **YOU GOT DESTROYED, LOSER!** 😭",
    
    "🪦 **TOTAL ANNIHILATION!** 🪦\n\n"
    "Before you could even blink, {card_name} demolished you!\n"
    "Your pride lies shattered on the ground...\n\n"
    "🤡 **PATHETIC! ABSOLUTELY PATHETIC!** 🤡",
    
    "💔 **HUMILIATING FAILURE!** 💔\n\n"
    "{card_name} didn't even break a sweat!\n"
    "They're literally yawning while you cry in the corner!\n\n"
    "😱 **EMBARRASSING! JUST EMBARRASSING!** 😱",
    
    "🏃 **COWARDLY RETREAT!** 🏃\n\n"
    "You tried to fight {card_name}... BIG MISTAKE!\n"
    "You ran away screaming like a baby!\n\n"
    "💩 **WHAT A DISAPPOINTMENT YOU ARE!** 💩",
    
    "⚰️ **OBLITERATED!** ⚰️\n\n"
    "{card_name} sent you straight to the shadow realm!\n"
    "Do you even know how to fight?!\n\n"
    "👎 **GIT GUD, SCRUB!** 👎"
]

# Battle initiation messages
BATTLE_START_MESSAGES = [
    "⚔️ {user_name} charges into battle against {card_name}!",
    "🔥 {user_name} challenges {card_name} to a duel!",
    "💥 {user_name} throws the first punch at {card_name}!",
    "⚡ {user_name} unleashes their power against {card_name}!",
    "🎯 {user_name} locks eyes with {card_name}... FIGHT!"
]


# ============================================================
# ⏱️ Cooldown Management
# ============================================================

_group_cooldowns: Dict[int, datetime] = {}
_active_spawns: Dict[int, Dict[str, Any]] = {}
_user_battle_cooldowns: Dict[str, datetime] = {}  # For individual battle cooldowns


def check_group_cooldown(group_id: int) -> tuple[bool, int]:
    """Check if a group is on spawn cooldown."""
    if group_id not in _group_cooldowns:
        return False, 0

    last_spawn = _group_cooldowns[group_id]
    elapsed = (datetime.now() - last_spawn).total_seconds()
    cooldown = CATCH_COOLDOWN_SECONDS

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

    _active_spawns.pop(group_id, None)
    return None


def set_active_spawn(group_id: int, card_id: int, message_id: int) -> None:
    """Set an active spawn for a group."""
    _active_spawns[group_id] = {
        "card_id": card_id,
        "message_id": message_id,
        "expires": datetime.now() + timedelta(seconds=CATCH_TIMEOUT_SECONDS),
        "caught_by": None,
        "battle_in_progress": None,  # Track who is currently battling
        "failed_users": set(),  # Track users who lost the battle
    }


def clear_active_spawn(group_id: int) -> None:
    """Clear the active spawn for a group."""
    _active_spawns.pop(group_id, None)


def mark_spawn_caught(group_id: int, user_id: int) -> bool:
    """Mark a spawn as caught by a user."""
    spawn = _active_spawns.get(group_id)

    if not spawn:
        return False

    if spawn["caught_by"] is not None:
        return False

    if datetime.now() >= spawn["expires"]:
        return False

    spawn["caught_by"] = user_id
    return True


def start_battle(group_id: int, user_id: int) -> bool:
    """Start a battle for a user. Returns False if battle already in progress."""
    spawn = _active_spawns.get(group_id)
    
    if not spawn:
        return False
    
    if spawn["caught_by"] is not None:
        return False
    
    if spawn["battle_in_progress"] is not None:
        return False
    
    if user_id in spawn.get("failed_users", set()):
        return False
    
    spawn["battle_in_progress"] = user_id
    return True


def end_battle(group_id: int, user_id: int, won: bool) -> None:
    """End a battle and record the result."""
    spawn = _active_spawns.get(group_id)
    
    if not spawn:
        return
    
    spawn["battle_in_progress"] = None
    
    if not won:
        if "failed_users" not in spawn:
            spawn["failed_users"] = set()
        spawn["failed_users"].add(user_id)


def is_battle_in_progress(group_id: int) -> bool:
    """Check if a battle is currently in progress."""
    spawn = _active_spawns.get(group_id)
    if not spawn:
        return False
    return spawn.get("battle_in_progress") is not None


def has_user_failed(group_id: int, user_id: int) -> bool:
    """Check if a user has already failed to catch this card."""
    spawn = _active_spawns.get(group_id)
    if not spawn:
        return False
    return user_id in spawn.get("failed_users", set())


# ============================================================
# 🎴 Spawn Card Function
# ============================================================

async def spawn_card_in_group(
    context: ContextTypes.DEFAULT_TYPE,
    group_id: int,
    force: bool = False
) -> Optional[Message]:
    """Spawn a random card in a group."""

    # Check cooldown
    if not force:
        is_cooldown, remaining = check_group_cooldown(group_id)
        if is_cooldown:
            app_logger.debug(f"Group {group_id} on cooldown ({remaining}s remaining)")
            return None

    # Check for active spawn
    if get_active_spawn(group_id):
        app_logger.debug(f"Group {group_id} already has an active spawn")
        return None

    # Get random card
    rarity_id = get_random_rarity()
    card = await get_random_card(None, rarity=rarity_id)

    if not card:
        card = await get_random_card(None)

    if not card:
        app_logger.warning(f"No cards in database to spawn in group {group_id}")
        return None

    # Build spawn message
    card_id = card["card_id"]
    anime = card["anime"]
    character = card["character_name"]
    rarity = card["rarity"]
    photo_file_id = card["photo_file_id"]

    rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity)
    value = calculate_rarity_value(rarity)

    spawn_text = (
        "🎴 **A Wild Card Appeared!**\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎬 **Anime:** {anime}\n"
        f"✨ **Rarity:** {rarity_emoji} {rarity_name}\n"
        f"💰 **Value:** {value:,} coins\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "⚔️ **Ready to Battle?**\n"
        f"⏱️ You have **{CATCH_TIMEOUT_SECONDS} seconds** to fight!\n\n"
        "🎲 _Win the battle to capture the card!_"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚔️ BATTLE!", callback_data=f"battle_{group_id}_{card_id}"),
        ],
        [
            InlineKeyboardButton("👀 Observe", callback_data=f"observe_{group_id}"),
        ],
    ])

    try:
        message = await context.bot.send_photo(
            chat_id=group_id,
            photo=photo_file_id,
            caption=spawn_text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )

        set_active_spawn(group_id, card_id, message.message_id)
        set_group_cooldown(group_id)

        await update_group_spawn(None, group_id, card_id, message.message_id)

        app_logger.info(f"🎴 Card spawned in group {group_id}: {character} ({rarity_emoji} {rarity_name})")

        # Schedule expiration
        asyncio.create_task(handle_spawn_expiration(context, group_id, message.message_id, card_id))

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
    """Handle spawn expiration after timeout."""
    await asyncio.sleep(CATCH_TIMEOUT_SECONDS)

    spawn = _active_spawns.get(group_id)

    if spawn and spawn["message_id"] == message_id and spawn["caught_by"] is None:
        try:
            card = await get_card_by_id(None, card_id)

            if card:
                character = card["character_name"]
                anime = card["anime"]
                rarity = card["rarity"]
                rarity_emoji = get_rarity_emoji(rarity)

                expired_text = (
                    "⏳ **Time's Up!**\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 **Character:** {character}\n"
                    f"🎬 **Anime:** {anime}\n"
                    f"✨ **Rarity:** {rarity_emoji}\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "💨 _The card escaped while everyone hesitated..._\n"
                    "🏃 _Maybe next time, cowards!_"
                )
            else:
                expired_text = "⏳ **Time's Up!**\n\n💨 _The card vanished into thin air..._"

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⏳ Escaped!", callback_data="expired")]
            ])

            await context.bot.edit_message_caption(
                chat_id=group_id,
                message_id=message_id,
                caption=expired_text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )

            app_logger.info(f"⏳ Card spawn expired in group {group_id}")

        except BadRequest:
            pass
        except TelegramError as e:
            error_logger.error(f"Error updating expired spawn: {e}")

        clear_active_spawn(group_id)
        await clear_group_spawn(None, group_id)


# ============================================================
# 🎯 Catch Command Handler
# ============================================================

async def catch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /catch command."""
    user = update.effective_user
    chat = update.effective_chat
    message = update.message

    if not message:
        return

    log_command(user.id, "catch", chat.id)

    # Ensure user exists
    await ensure_user(
        pool=None,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

    # Private chat - show help
    if chat.type == ChatType.PRIVATE:
        await message.reply_text(
            "⚔️ **Battle System**\n\n"
            "This command works in groups!\n\n"
            "When a card spawns:\n"
            "• Click the **⚔️ BATTLE!** button\n"
            "• Fight the card in an epic duel!\n"
            "• **Win** = Card is yours! 🏆\n"
            "• **Lose** = Card escapes... 💀\n\n"
            "May the odds be in your favor! 🎲",
            parse_mode="Markdown"
        )
        return

    # Group chat
    group_id = chat.id

    await ensure_group(None, group_id, chat.title)

    spawn = get_active_spawn(group_id)

    if spawn:
        if spawn["caught_by"] is not None:
            await message.reply_text("❌ This card was already caught!")
            return
        
        await message.reply_text(
            "⚔️ **A card is waiting!**\n\n"
            "Click the **BATTLE** button on the card above to fight!",
            parse_mode="Markdown"
        )
        return

    # No active spawn - try to spawn one
    is_cooldown, remaining = check_group_cooldown(group_id)
    if is_cooldown:
        minutes = remaining // 60
        seconds = remaining % 60
        
        if minutes > 0:
            time_str = f"{minutes}m {seconds}s"
        else:
            time_str = f"{seconds}s"
        
        await message.reply_text(
            f"⏳ **Please Wait**\n\n"
            f"Next card spawns in: **{time_str}**\n\n"
            f"💡 _Cards spawn every {CATCH_COOLDOWN_SECONDS // 60} minutes!_",
            parse_mode="Markdown"
        )
        return

    total_cards = await get_card_count(None)
    if total_cards == 0:
        await message.reply_text(
            "❌ **No Cards Available**\n\n"
            "There are no cards in the database yet.\n"
            "Ask an admin to upload some cards first!",
            parse_mode="Markdown"
        )
        return

    spawn_message = await spawn_card_in_group(context, group_id, force=True)

    if not spawn_message:
        await message.reply_text("❌ Failed to spawn a card. Please try again.")


# ============================================================
# ⚔️ Battle Callback Handler
# ============================================================

async def battle_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle battle button clicks."""
    query = update.callback_query
    user = query.from_user
    data = query.data

    # Handle expired button
    if data == "expired":
        await query.answer("⏳ This card has escaped!", show_alert=True)
        return

    # Handle observe button
    if data.startswith("observe_"):
        await query.answer("👀 You watch from a safe distance... Coward! 😏", show_alert=True)
        return

    # Handle battle button
    if not data.startswith("battle_"):
        return

    try:
        parts = data.split("_")
        group_id = int(parts[1])
        card_id = int(parts[2])
    except (IndexError, ValueError):
        await query.answer("❌ Invalid action.", show_alert=True)
        return

    # Ensure user exists
    await ensure_user(
        pool=None,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

    spawn = get_active_spawn(group_id)

    if not spawn:
        await query.answer("⏳ This card has escaped!", show_alert=True)
        return

    if spawn["card_id"] != card_id:
        await query.answer("❌ This card is no longer available.", show_alert=True)
        return

    if spawn["caught_by"] is not None:
        if spawn["caught_by"] == user.id:
            await query.answer("✅ You already caught this card!", show_alert=True)
        else:
            await query.answer("❌ Someone else already caught this card!", show_alert=True)
        return

    # Check if user already failed
    if has_user_failed(group_id, user.id):
        await query.answer("💀 You already lost! Wait for the next card!", show_alert=True)
        return

    # Check if battle is in progress
    if is_battle_in_progress(group_id):
        await query.answer("⚔️ A battle is in progress! Wait your turn!", show_alert=True)
        return

    # Start the battle
    if not start_battle(group_id, user.id):
        await query.answer("❌ Couldn't start battle. Try again!", show_alert=True)
        return

    await query.answer("⚔️ BATTLE STARTED!", show_alert=False)

    # Get card info
    card = await get_card_by_id(None, card_id)
    if not card:
        end_battle(group_id, user.id, False)
        await query.answer("❌ Card not found!", show_alert=True)
        return

    character = card["character_name"]
    anime = card["anime"]
    rarity = card["rarity"]
    rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity)

    # Show battle starting message
    battle_start = random.choice(BATTLE_START_MESSAGES).format(
        user_name=user.first_name,
        card_name=character
    )

    battle_text = (
        f"⚔️ **BATTLE IN PROGRESS!** ⚔️\n\n"
        f"{battle_start}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎴 **{character}**\n"
        f"🎬 {anime}\n"
        f"✨ {rarity_emoji} {rarity_name}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎲 **Rolling dice...**"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ Fighting...", callback_data="fighting")]
    ])

    try:
        await query.message.edit_caption(
            caption=battle_text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    except (BadRequest, TelegramError):
        pass

    # Dramatic pause for battle
    await asyncio.sleep(2)

    # Determine battle outcome
    won = random.randint(1, 100) <= WIN_CHANCE

    if won:
        # Victory!
        end_battle(group_id, user.id, True)
        
        if mark_spawn_caught(group_id, user.id):
            await process_victory(update, context, group_id, card_id, user, card)
        else:
            # Someone else caught it during battle (edge case)
            await query.message.reply_text(
                f"😱 **PLOT TWIST!**\n\n"
                f"{user.first_name} won the battle but someone snatched the card!\n"
                f"_How is that even possible?!_",
                parse_mode="Markdown"
            )
    else:
        # Defeat!
        end_battle(group_id, user.id, False)
        await process_defeat(update, context, group_id, card_id, user, card)


async def process_victory(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    group_id: int,
    card_id: int,
    user,
    card: dict
) -> None:
    """Process a battle victory."""
    query = update.callback_query
    
    character = card["character_name"]
    anime = card["anime"]
    rarity = card["rarity"]
    rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity)
    value = calculate_rarity_value(rarity)

    # Add to collection
    try:
        await add_to_collection(None, user.id, card_id, group_id)
        await increment_card_caught(None, card_id)
        await update_user_stats(None, user.id, coins_delta=value, catches_delta=1)
        log_card_catch(user.id, character, rarity_name)
    except Exception as e:
        error_logger.error(f"Failed to add card to collection: {e}", exc_info=True)
        return

    # Get victory message
    victory_msg = random.choice(WIN_MESSAGES).format(card_name=character)

    success_text = (
        f"{victory_msg}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Character:** {character}\n"
        f"🎬 **Anime:** {anime}\n"
        f"✨ **Rarity:** {rarity_emoji} {rarity_name}\n"
        f"💰 **Reward:** +{value:,} coins\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏆 **Winner:** [{user.first_name}](tg://user?id={user.id})"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎴 View Collection", url=f"t.me/{context.bot.username}?start=harem")]
    ])

    try:
        await query.message.edit_caption(
            caption=success_text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    except (BadRequest, TelegramError) as e:
        error_logger.error(f"Error updating victory message: {e}")

    clear_active_spawn(group_id)
    await clear_group_spawn(None, group_id)

    app_logger.info(f"🏆 {user.first_name} ({user.id}) won battle for {character} in group {group_id}")


async def process_defeat(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    group_id: int,
    card_id: int,
    user,
    card: dict
) -> None:
    """Process a battle defeat."""
    query = update.callback_query
    
    character = card["character_name"]
    anime = card["anime"]
    rarity = card["rarity"]
    rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity)
    value = calculate_rarity_value(rarity)

    # Get defeat message
    defeat_msg = random.choice(LOSE_MESSAGES).format(card_name=character)

    # Check spawn status
    spawn = get_active_spawn(group_id)
    
    if spawn and spawn["caught_by"] is None:
        # Card still available
        remaining = int((spawn["expires"] - datetime.now()).total_seconds())
        remaining = max(0, remaining)
        
        defeat_text = (
            f"{defeat_msg}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎬 **Anime:** {anime}\n"
            f"✨ **Rarity:** {rarity_emoji} {rarity_name}\n"
            f"💰 **Value:** {value:,} coins\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"⏱️ **{remaining}s** remaining!\n"
            "💪 _Someone else can still try!_"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚔️ BATTLE!", callback_data=f"battle_{group_id}_{card_id}")],
            [InlineKeyboardButton("👀 Observe", callback_data=f"observe_{group_id}")],
        ])
    else:
        # Card expired or caught
        defeat_text = (
            f"{defeat_msg}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **Character:** {character}\n"
            f"🎬 **Anime:** {anime}\n"
            f"✨ **Rarity:** {rarity_emoji}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "💨 _The card disappeared..._"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💀 Defeated", callback_data="expired")]
        ])

    try:
        await query.message.edit_caption(
            caption=defeat_text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    except (BadRequest, TelegramError) as e:
        error_logger.error(f"Error updating defeat message: {e}")

    # Send taunt message to the loser
    taunt_messages = [
        f"😂 {user.first_name} got DESTROYED by {character}!",
        f"💀 {user.first_name} needs to train more! WEAK!",
        f"🤡 {user.first_name} thought they could win? LMAO!",
        f"😭 {user.first_name} is crying in the corner...",
        f"👎 {user.first_name} should just give up collecting!"
    ]

    try:
        await query.message.reply_text(
            random.choice(taunt_messages),
            parse_mode="Markdown"
        )
    except TelegramError:
        pass

    app_logger.info(f"💀 {user.first_name} ({user.id}) lost battle for {character} in group {group_id}")


# ============================================================
# 📝 Name Guessing Handler (Alternative catch method)
# ============================================================

async def name_guess_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages in groups as potential name guesses."""
    if not update.message or not update.message.text:
        return

    message = update.message
    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user:
        return

    if chat.type == ChatType.PRIVATE:
        return

    group_id = chat.id
    guess = message.text.strip().lower()

    if not guess or len(guess) < 2:
        return

    spawn = get_active_spawn(group_id)

    if not spawn or spawn["caught_by"] is not None:
        return

    # Check if battle in progress
    if is_battle_in_progress(group_id):
        return

    # Check if user already failed
    if has_user_failed(group_id, user.id):
        return

    card = await get_card_by_id(None, spawn["card_id"])

    if not card:
        return

    character_name = card["character_name"].lower()
    name_parts = character_name.split()

    # Check exact match or partial match
    is_match = (
        guess == character_name or
        guess in name_parts or
        any(part.startswith(guess) for part in name_parts if len(guess) >= 3)
    )

    if is_match:
        # Start battle automatically
        if not start_battle(group_id, user.id):
            return

        await message.reply_text(
            f"🎯 **Name Guessed!** You said: _{guess}_\n\n"
            f"⚔️ Initiating battle...",
            parse_mode="Markdown"
        )

        await asyncio.sleep(1)

        # Battle!
        won = random.randint(1, 100) <= WIN_CHANCE

        if won:
            end_battle(group_id, user.id, True)
            if mark_spawn_caught(group_id, user.id):
                # Manual victory process for name guess
                character = card["character_name"]
                anime = card["anime"]
                rarity = card["rarity"]
                rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity)
                value = calculate_rarity_value(rarity)

                try:
                    await add_to_collection(None, user.id, spawn["card_id"], group_id)
                    await increment_card_caught(None, spawn["card_id"])
                    await update_user_stats(None, user.id, coins_delta=value, catches_delta=1)
                    log_card_catch(user.id, character, rarity_name)
                except Exception as e:
                    error_logger.error(f"Failed to add card: {e}")
                    return

                victory_msg = random.choice(WIN_MESSAGES).format(card_name=character)

                await message.reply_text(
                    f"{victory_msg}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 **{character}**\n"
                    f"🎬 {anime}\n"
                    f"✨ {rarity_emoji} {rarity_name}\n"
                    f"💰 +{value:,} coins\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━",
                    parse_mode="Markdown"
                )

                clear_active_spawn(group_id)
                await clear_group_spawn(None, group_id)
        else:
            end_battle(group_id, user.id, False)
            defeat_msg = random.choice(LOSE_MESSAGES).format(card_name=card["character_name"])
            await message.reply_text(defeat_msg, parse_mode="Markdown")


# ============================================================
# 🔧 Force Spawn Command (Admin)
# ============================================================

async def force_spawn_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /forcespawn command - Admin force spawn."""
    user = update.effective_user
    chat = update.effective_chat

    if not update.message:
        return

    if not Config.is_admin(user.id):
        await update.message.reply_text("❌ Admin only command.")
        return

    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text("❌ Use this command in a group.")
        return

    # Clear any existing spawn
    clear_active_spawn(chat.id)

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

battle_callback = CallbackQueryHandler(
    battle_callback_handler,
    pattern=r"^(battle_|observe_|expired|fighting)"
)

name_guess_message_handler = MessageHandler(
    filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
    name_guess_handler
)