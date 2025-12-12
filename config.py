# ============================================================
# 📁 File: handlers/admin.py
# 📍 Location: telegram_card_bot/handlers/admin.py
# 📝 Description: Admin commands and broadcast system
# ============================================================

import asyncio
from datetime import datetime
from typing import Optional, List

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.error import TelegramError, Forbidden

from config import Config
from db import (
    db,
    get_global_stats,
    get_card_count,
    get_all_groups,
    get_rarity_distribution,
    health_check,
    get_card_by_id,
    get_user_by_id,
    ensure_user,
    add_to_collection,
    update_user_stats,
)
from utils.logger import app_logger, error_logger, log_command
from utils.rarity import RARITY_TABLE, get_rarity_emoji, rarity_to_text, calculate_rarity_value


# ============================================================
# ⏱️ Bot Start Time (for uptime calculation)
# ============================================================

_bot_start_time: Optional[datetime] = None


def set_bot_start_time() -> None:
    """Set the bot start time for uptime calculation."""
    global _bot_start_time
    _bot_start_time = datetime.now()


def get_uptime() -> str:
    """Get formatted bot uptime string."""
    if _bot_start_time is None:
        return "Unknown"

    delta = datetime.now() - _bot_start_time

    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")

    return " ".join(parts)


# Initialize start time when module loads
set_bot_start_time()


# ============================================================
# 🔐 Admin Check Function
# ============================================================

def is_admin(user_id: int) -> bool:
    """Check if a user is an admin."""
    return Config.is_admin(user_id)


async def check_admin(update: Update) -> bool:
    """Check if the update is from an admin. Sends error if not."""
    user = update.effective_user

    if not is_admin(user.id):
        if update.callback_query:
            await update.callback_query.answer(
                "❌ You are not allowed to use this command.",
                show_alert=True
            )
        else:
            await update.message.reply_text(
                "❌ *Permission Denied*\n\n"
                "You are not allowed to use this command.\n"
                "This incident will be logged.",
                parse_mode="Markdown"
            )

        error_logger.warning(
            f"⚠️ Unauthorized admin access attempt by user {user.id} ({user.first_name})"
        )
        return False

    return True


# ============================================================
# 👑 Admin Command Handler
# ============================================================

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /admin command - Show admin panel."""
    user = update.effective_user
    log_command(user.id, "admin", update.effective_chat.id)

    # Check admin permission
    if not await check_admin(update):
        return

    # Build admin panel keyboard
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Statistics", callback_data="admin_stats"),
            InlineKeyboardButton("🎴 Cards Info", callback_data="admin_cards"),
        ],
        [
            InlineKeyboardButton("👥 Users", callback_data="admin_users"),
            InlineKeyboardButton("💬 Groups", callback_data="admin_groups"),
        ],
        [
            InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
            InlineKeyboardButton("🔄 Reload DB", callback_data="admin_reload"),
        ],
        [
            InlineKeyboardButton("❤️ Health Check", callback_data="admin_health"),
            InlineKeyboardButton("⏱️ Uptime", callback_data="admin_uptime"),
        ],
        [
            InlineKeyboardButton("❌ Close Panel", callback_data="admin_close"),
        ],
    ])

    # Send admin panel
    await update.message.reply_text(
        "👑 *Admin Control Panel*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Admin: {user.first_name}\n"
        f"🆔 ID: `{user.id}`\n"
        f"⏱️ Uptime: {get_uptime()}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "*Quick Commands:*\n"
        "• `/delete <card_id>` - Delete card\n"
        "• `/edit <card_id>` - Edit card\n"
        "• `/userinfo` (reply) - User info\n"
        "• `/gcard <card_id>` (reply) - Give card\n"
        "• `/gcoins <amount>` (reply) - Give coins\n\n"
        "Select an option below:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

    app_logger.info(f"👑 Admin panel opened by {user.id} ({user.first_name})")


async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle admin panel callback queries."""
    query = update.callback_query
    user = query.from_user
    data = query.data

    # Check admin permission
    if not is_admin(user.id):
        await query.answer("❌ You are not allowed to use this.", show_alert=True)
        return

    await query.answer()

    # Statistics
    if data == "admin_stats":
        stats = await get_global_stats(None)

        text = (
            "📊 *Bot Statistics*\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 Total Users: `{stats['total_users']:,}`\n"
            f"🎴 Total Cards: `{stats['total_cards']:,}`\n"
            f"🎯 Total Catches: `{stats['total_catches']:,}`\n"
            f"💬 Active Groups: `{stats['active_groups']:,}`\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"⏱️ Uptime: {get_uptime()}"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="admin_stats")],
            [InlineKeyboardButton("⬅️ Back", callback_data="admin_back")],
        ])

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)

    # Cards Info
    elif data == "admin_cards":
        total_cards = await get_card_count(None)
        distribution = await get_rarity_distribution(None)

        dist_lines = []
        for row in distribution:
            rarity_id = row["rarity"]
            count = row["count"]
            emoji = get_rarity_emoji(rarity_id)
            name = RARITY_TABLE[rarity_id].name if rarity_id in RARITY_TABLE else "Unknown"
            dist_lines.append(f"{emoji} {name}: `{count}`")

        dist_text = "\n".join(dist_lines) if dist_lines else "No cards yet"

        text = (
            "🎴 *Cards Information*\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 Total Cards: `{total_cards}`\n\n"
            "*Rarity Distribution:*\n"
            f"{dist_text}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="admin_back")],
        ])

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)

    # Users Info
    elif data == "admin_users":
        stats = await get_global_stats(None)

        text = (
            "👥 *Users Information*\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Total Users: `{stats['total_users']:,}`\n"
            f"👑 Admins: `{len(Config.ADMIN_IDS)}`\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "*Admin IDs:*\n"
            + "\n".join([f"• `{aid}`" for aid in Config.ADMIN_IDS[:10]])
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="admin_back")],
        ])

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)

    # Groups Info
    elif data == "admin_groups":
        groups = await get_all_groups(None, active_only=True)

        groups_text = ""
        for i, group in enumerate(groups[:10], 1):
            name = group["group_name"] or "Unknown"
            gid = group["group_id"]
            spawns = group["total_spawns"]
            catches = group["total_catches"]
            groups_text += f"{i}. {name}\n   ID: `{gid}` | 🎴 {spawns} | 🎯 {catches}\n"

        if not groups_text:
            groups_text = "No active groups yet."

        text = (
            "💬 *Active Groups*\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Total Active: `{len(groups)}`\n\n"
            f"{groups_text}"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="admin_groups")],
            [InlineKeyboardButton("⬅️ Back", callback_data="admin_back")],
        ])

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)

    # Broadcast
    elif data == "admin_broadcast":
        text = (
            "📢 *Broadcast Message*\n\n"
            "To send a broadcast to all users:\n\n"
            "Use the command:\n"
            "`/broadcast Your message here`\n\n"
            "⚠️ *Warning:* This will send a message to ALL registered users."
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="admin_back")],
        ])

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)

    # Reload DB
    elif data == "admin_reload":
        try:
            is_healthy = await health_check(None)

            if is_healthy:
                text = (
                    "🔄 *Database Reloaded*\n\n"
                    "✅ Connection pool refreshed\n"
                    "✅ Tables verified\n"
                    "✅ All systems operational"
                )
            else:
                text = (
                    "⚠️ *Database Issues*\n\n"
                    "❌ Health check failed\n"
                    "Please check the logs"
                )
        except Exception as e:
            error_logger.error(f"DB reload failed: {e}", exc_info=True)
            text = f"❌ *Error:* `{str(e)[:100]}`"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="admin_back")],
        ])

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)

    # Health Check
    elif data == "admin_health":
        is_healthy = await health_check(None)

        text = (
            "❤️ *Health Check*\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🗄️ Database: {'✅ Connected' if is_healthy else '❌ Disconnected'}\n"
            f"🤖 Bot: ✅ Running\n"
            f"⏱️ Uptime: {get_uptime()}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="admin_health")],
            [InlineKeyboardButton("⬅️ Back", callback_data="admin_back")],
        ])

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)

    # Uptime
    elif data == "admin_uptime":
        uptime = get_uptime()

        text = (
            "⏱️ *Bot Uptime*\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🕐 Running for: *{uptime}*\n"
            f"🚀 Started: {_bot_start_time.strftime('%Y-%m-%d %H:%M:%S') if _bot_start_time else 'Unknown'}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="admin_uptime")],
            [InlineKeyboardButton("⬅️ Back", callback_data="admin_back")],
        ])

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)

    # Back to main panel
    elif data == "admin_back":
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📊 Statistics", callback_data="admin_stats"),
                InlineKeyboardButton("🎴 Cards Info", callback_data="admin_cards"),
            ],
            [
                InlineKeyboardButton("👥 Users", callback_data="admin_users"),
                InlineKeyboardButton("💬 Groups", callback_data="admin_groups"),
            ],
            [
                InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
                InlineKeyboardButton("🔄 Reload DB", callback_data="admin_reload"),
            ],
            [
                InlineKeyboardButton("❤️ Health Check", callback_data="admin_health"),
                InlineKeyboardButton("⏱️ Uptime", callback_data="admin_uptime"),
            ],
            [
                InlineKeyboardButton("❌ Close Panel", callback_data="admin_close"),
            ],
        ])

        await query.edit_message_text(
            "👑 *Admin Control Panel*\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Admin: {user.first_name}\n"
            f"🆔 ID: `{user.id}`\n"
            f"⏱️ Uptime: {get_uptime()}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Select an option below:",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

    # Close panel
    elif data == "admin_close":
        await query.edit_message_text(
            "👑 *Admin Panel Closed*\n\n"
            "Use /admin to open again.",
            parse_mode="Markdown"
        )


# ============================================================
# 📢 Broadcast System
# ============================================================

BROADCAST_MESSAGE = 0


async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /broadcast command - Start broadcast flow."""
    user = update.effective_user
    log_command(user.id, "broadcast", update.effective_chat.id)

    # Check admin permission
    if not await check_admin(update):
        return ConversationHandler.END

    # Check if message text is provided directly
    message_text = update.message.text.replace("/broadcast", "").strip()

    if message_text:
        # Direct broadcast with message
        context.user_data["broadcast_message"] = message_text
        return await broadcast_execute(update, context)

    # Ask for message
    await update.message.reply_text(
        "📢 *Broadcast Message*\n\n"
        "Send the message you want to broadcast to all users.\n\n"
        "⚠️ This will send to ALL registered users.\n\n"
        "Type your message or /cancel to abort:",
        parse_mode="Markdown"
    )

    return BROADCAST_MESSAGE


async def broadcast_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle broadcast message input."""
    message_text = update.message.text
    context.user_data["broadcast_message"] = message_text
    return await broadcast_execute(update, context)


async def broadcast_execute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Execute the broadcast."""
    message_text = context.user_data.get("broadcast_message", "")
    user = update.effective_user

    if not message_text:
        await update.message.reply_text("❌ No message to broadcast.")
        return ConversationHandler.END

    # Get all users
    try:
        users = await db.fetch("SELECT user_id FROM users WHERE is_banned = FALSE")
    except Exception as e:
        error_logger.error(f"Failed to get users for broadcast: {e}", exc_info=True)
        await update.message.reply_text("❌ Failed to get user list.")
        return ConversationHandler.END

    total_users = len(users)

    if total_users == 0:
        await update.message.reply_text("❌ No users to broadcast to.")
        return ConversationHandler.END

    # Send confirmation
    confirm_msg = await update.message.reply_text(
        f"📢 *Broadcasting...*\n\n"
        f"Sending to {total_users} users...",
        parse_mode="Markdown"
    )

    # Send broadcast
    success_count = 0
    fail_count = 0
    blocked_count = 0

    app_logger.info(f"📢 Broadcast started by admin {user.id} to {total_users} users")

    for row in users:
        user_id = row["user_id"]

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📢 *Broadcast Message*\n\n{message_text}",
                parse_mode="Markdown"
            )
            success_count += 1

            # Small delay to avoid rate limits
            if success_count % 30 == 0:
                await asyncio.sleep(1)

        except Forbidden:
            blocked_count += 1
        except TelegramError as e:
            fail_count += 1
            error_logger.warning(f"Broadcast failed for user {user_id}: {e}")
        except Exception as e:
            fail_count += 1
            error_logger.error(f"Broadcast error for user {user_id}: {e}")

    # Send result
    await confirm_msg.edit_text(
        f"📢 *Broadcast Complete!*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Sent: `{success_count}`\n"
        f"🚫 Blocked: `{blocked_count}`\n"
        f"❌ Failed: `{fail_count}`\n"
        f"📊 Total: `{total_users}`\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown"
    )

    app_logger.info(
        f"📢 Broadcast finished: {success_count} sent, "
        f"{blocked_count} blocked, {fail_count} failed"
    )

    return ConversationHandler.END


async def broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel broadcast."""
    await update.message.reply_text(
        "❌ *Broadcast Cancelled*",
        parse_mode="Markdown"
    )
    return ConversationHandler.END


# Broadcast conversation handler
broadcast_conversation_handler = ConversationHandler(
    entry_points=[
        CommandHandler("broadcast", broadcast_start),
    ],
    states={
        BROADCAST_MESSAGE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message_received),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", broadcast_cancel),
    ],
    conversation_timeout=120,
)


# ============================================================
# 🗑️ Delete Card Command
# ============================================================

async def delete_card_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /delete command - Delete a card from database."""
    user = update.effective_user
    log_command(user.id, "delete", update.effective_chat.id)

    if not is_admin(user.id):
        await update.message.reply_text("❌ Admin only command.")
        return

    args = context.args

    if not args:
        await update.message.reply_text(
            "🗑️ *Delete Card*\n\n"
            "*Usage:* `/delete <card_id>`\n\n"
            "*Example:* `/delete 42`\n\n"
            "⚠️ This will permanently delete the card and remove it from all collections!",
            parse_mode="Markdown"
        )
        return

    try:
        card_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid card ID. Please provide a number.")
        return

    # Get card info first
    card = await get_card_by_id(None, card_id)

    if not card:
        await update.message.reply_text(f"❌ Card with ID `{card_id}` not found.", parse_mode="Markdown")
        return

    character = card["character_name"]
    anime = card["anime"]
    rarity = card["rarity"]
    rarity_name, _, rarity_emoji = rarity_to_text(rarity)

    # Create confirmation keyboard
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Yes, Delete", callback_data=f"admin_delcard_confirm_{card_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data="admin_delcard_cancel"),
        ]
    ])

    await update.message.reply_text(
        f"🗑️ *Delete Card Confirmation*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 *ID:* `{card_id}`\n"
        f"👤 *Character:* {character}\n"
        f"🎬 *Anime:* {anime}\n"
        f"✨ *Rarity:* {rarity_emoji} {rarity_name}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚠️ *Warning:* This will:\n"
        f"• Delete the card permanently\n"
        f"• Remove from ALL user collections\n"
        f"• This action cannot be undone!\n\n"
        f"Are you sure?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


async def delete_card_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle delete card confirmation callbacks."""
    query = update.callback_query
    user = query.from_user
    data = query.data

    if not is_admin(user.id):
        await query.answer("❌ Not authorized.", show_alert=True)
        return

    await query.answer()

    if data == "admin_delcard_cancel":
        await query.edit_message_text(
            "❌ *Card deletion cancelled.*",
            parse_mode="Markdown"
        )
        return

    if data.startswith("admin_delcard_confirm_"):
        try:
            card_id = int(data.replace("admin_delcard_confirm_", ""))
        except ValueError:
            await query.edit_message_text("❌ Invalid card ID.")
            return

        # Get card info for logging
        card = await get_card_by_id(None, card_id)

        if not card:
            await query.edit_message_text("❌ Card not found or already deleted.")
            return

        character = card["character_name"]

        try:
            # Delete from collections first (foreign key constraint)
            # FIXED: Use 'collections' table instead of 'user_cards'
            await db.execute(
                "DELETE FROM collections WHERE card_id = $1",
                card_id
            )

            # Delete the card
            await db.execute(
                "DELETE FROM cards WHERE card_id = $1",
                card_id
            )

            await query.edit_message_text(
                f"✅ *Card Deleted Successfully!*\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🆔 *ID:* `{card_id}`\n"
                f"👤 *Character:* {character}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🗑️ Removed from all collections.",
                parse_mode="Markdown"
            )

            app_logger.info(f"🗑️ Card {card_id} ({character}) deleted by admin {user.id}")

        except Exception as e:
            error_logger.error(f"Failed to delete card {card_id}: {e}", exc_info=True)
            await query.edit_message_text(f"❌ Error deleting card: `{str(e)[:100]}`", parse_mode="Markdown")


# ============================================================
# ✏️ Edit Card Command
# ============================================================

# Conversation states for edit
EDIT_SELECT_FIELD, EDIT_NEW_VALUE = range(2)

_edit_sessions = {}  # Store edit sessions


async def edit_card_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /edit command - Edit a card's data."""
    user = update.effective_user
    log_command(user.id, "edit", update.effective_chat.id)

    if not is_admin(user.id):
        await update.message.reply_text("❌ Admin only command.")
        return ConversationHandler.END

    args = context.args

    if not args:
        await update.message.reply_text(
            "✏️ *Edit Card*\n\n"
            "*Usage:* `/edit <card_id>`\n\n"
            "*Example:* `/edit 42`",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    try:
        card_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid card ID.")
        return ConversationHandler.END

    # Get card info
    card = await get_card_by_id(None, card_id)

    if not card:
        await update.message.reply_text(f"❌ Card with ID `{card_id}` not found.", parse_mode="Markdown")
        return ConversationHandler.END

    character = card["character_name"]
    anime = card["anime"]
    rarity = card["rarity"]
    rarity_name, _, rarity_emoji = rarity_to_text(rarity)

    # Store card info in session
    _edit_sessions[user.id] = {
        "card_id": card_id,
        "card": card
    }

    # Create field selection keyboard
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👤 Character Name", callback_data="admin_edit_character"),
            InlineKeyboardButton("🎬 Anime", callback_data="admin_edit_anime"),
        ],
        [
            InlineKeyboardButton("✨ Rarity", callback_data="admin_edit_rarity"),
        ],
        [
            InlineKeyboardButton("❌ Cancel", callback_data="admin_edit_cancel"),
        ]
    ])

    await update.message.reply_text(
        f"✏️ *Edit Card*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 *ID:* `{card_id}`\n"
        f"👤 *Character:* {character}\n"
        f"🎬 *Anime:* {anime}\n"
        f"✨ *Rarity:* {rarity_emoji} {rarity_name}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Select the field to edit:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

    return EDIT_SELECT_FIELD


async def edit_field_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle edit field selection."""
    query = update.callback_query
    user = query.from_user
    data = query.data

    if not is_admin(user.id):
        await query.answer("❌ Not authorized.", show_alert=True)
        return ConversationHandler.END

    await query.answer()

    if data == "admin_edit_cancel":
        _edit_sessions.pop(user.id, None)
        await query.edit_message_text("❌ *Edit cancelled.*", parse_mode="Markdown")
        return ConversationHandler.END

    session = _edit_sessions.get(user.id)
    if not session:
        await query.edit_message_text("❌ Edit session expired. Please start again with /edit")
        return ConversationHandler.END

    if data == "admin_edit_character":
        session["edit_field"] = "character_name"
        await query.edit_message_text(
            "👤 *Edit Character Name*\n\n"
            f"Current: `{session['card']['character_name']}`\n\n"
            "Send the new character name:",
            parse_mode="Markdown"
        )
        return EDIT_NEW_VALUE

    elif data == "admin_edit_anime":
        session["edit_field"] = "anime"
        await query.edit_message_text(
            "🎬 *Edit Anime*\n\n"
            f"Current: `{session['card']['anime']}`\n\n"
            "Send the new anime name:",
            parse_mode="Markdown"
        )
        return EDIT_NEW_VALUE

    elif data == "admin_edit_rarity":
        session["edit_field"] = "rarity"

        # Build rarity selection keyboard
        rarity_buttons = []
        for rarity_id, rarity_info in RARITY_TABLE.items():
            emoji = rarity_info.emoji
            name = rarity_info.name
            rarity_buttons.append(
                InlineKeyboardButton(f"{emoji} {name}", callback_data=f"admin_edit_rarity_{rarity_id}")
            )

        # Arrange in rows of 2
        keyboard_rows = [rarity_buttons[i:i+2] for i in range(0, len(rarity_buttons), 2)]
        keyboard_rows.append([InlineKeyboardButton("❌ Cancel", callback_data="admin_edit_cancel")])

        await query.edit_message_text(
            "✨ *Edit Rarity*\n\n"
            f"Current: `{rarity_to_text(session['card']['rarity'])[0]}`\n\n"
            "Select new rarity:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard_rows)
        )
        return EDIT_SELECT_FIELD

    # Handle rarity selection
    elif data.startswith("admin_edit_rarity_"):
        try:
            new_rarity = int(data.replace("admin_edit_rarity_", ""))
        except ValueError:
            await query.edit_message_text("❌ Invalid rarity.")
            return ConversationHandler.END

        card_id = session["card_id"]

        try:
            await db.execute(
                "UPDATE cards SET rarity = $1 WHERE card_id = $2",
                new_rarity, card_id
            )

            new_rarity_name, _, new_emoji = rarity_to_text(new_rarity)

            await query.edit_message_text(
                f"✅ *Card Updated!*\n\n"
                f"🆔 Card ID: `{card_id}`\n"
                f"✨ New Rarity: {new_emoji} {new_rarity_name}",
                parse_mode="Markdown"
            )

            app_logger.info(f"✏️ Card {card_id} rarity updated to {new_rarity_name} by admin {user.id}")

        except Exception as e:
            error_logger.error(f"Failed to update card {card_id}: {e}", exc_info=True)
            await query.edit_message_text(f"❌ Error: `{str(e)[:100]}`", parse_mode="Markdown")

        _edit_sessions.pop(user.id, None)
        return ConversationHandler.END

    return EDIT_SELECT_FIELD


async def edit_new_value_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle new value input for editing."""
    user = update.effective_user
    new_value = update.message.text.strip()

    if not is_admin(user.id):
        return ConversationHandler.END

    session = _edit_sessions.get(user.id)
    if not session:
        await update.message.reply_text("❌ Edit session expired. Please start again with /edit")
        return ConversationHandler.END

    card_id = session["card_id"]
    field = session["edit_field"]

    if not new_value:
        await update.message.reply_text("❌ Please provide a valid value.")
        return EDIT_NEW_VALUE

    try:
        await db.execute(
            f"UPDATE cards SET {field} = $1 WHERE card_id = $2",
            new_value, card_id
        )

        field_display = "Character Name" if field == "character_name" else "Anime"

        await update.message.reply_text(
            f"✅ *Card Updated!*\n\n"
            f"🆔 Card ID: `{card_id}`\n"
            f"📝 {field_display}: `{new_value}`",
            parse_mode="Markdown"
        )

        app_logger.info(f"✏️ Card {card_id} {field} updated to '{new_value}' by admin {user.id}")

    except Exception as e:
        error_logger.error(f"Failed to update card {card_id}: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: `{str(e)[:100]}`", parse_mode="Markdown")

    _edit_sessions.pop(user.id, None)
    return ConversationHandler.END


async def edit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel edit operation."""
    user = update.effective_user
    _edit_sessions.pop(user.id, None)
    await update.message.reply_text("❌ *Edit cancelled.*", parse_mode="Markdown")
    return ConversationHandler.END


# Edit conversation handler
edit_conversation_handler = ConversationHandler(
    entry_points=[
        CommandHandler("edit", edit_card_command),
    ],
    states={
        EDIT_SELECT_FIELD: [
            CallbackQueryHandler(edit_field_callback, pattern=r"^admin_edit_"),
        ],
        EDIT_NEW_VALUE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, edit_new_value_handler),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", edit_cancel),
    ],
    conversation_timeout=120,
    per_message=False,
)


# ============================================================
# 👤 User Info Command (with Reset functionality)
# ============================================================

async def userinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /userinfo command - View and manage user data."""
    user = update.effective_user
    log_command(user.id, "userinfo", update.effective_chat.id)

    if not is_admin(user.id):
        await update.message.reply_text("❌ Admin only command.")
        return

    # Get target user ID
    target_id = None

    # Check if replying to a message
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
    # Check if user ID provided as argument
    elif context.args:
        try:
            target_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID.")
            return

    if not target_id:
        await update.message.reply_text(
            "👤 *User Info Command*\n\n"
            "*Usage:*\n"
            "• Reply to a user's message: `/userinfo`\n"
            "• With user ID: `/userinfo <user_id>`\n\n"
            "*Example:* `/userinfo 123456789`",
            parse_mode="Markdown"
        )
        return

    # Get user data - FIXED: Use 'collections' table
    try:
        user_data = await db.fetchrow(
            """
            SELECT u.*, 
                   COUNT(c.collection_id) as card_count,
                   COALESCE(SUM(CASE WHEN ca.rarity >= 10 THEN 1 ELSE 0 END), 0) as legendary_count
            FROM users u
            LEFT JOIN collections c ON u.user_id = c.user_id
            LEFT JOIN cards ca ON c.card_id = ca.card_id
            WHERE u.user_id = $1
            GROUP BY u.user_id
            """,
            target_id
        )
    except Exception as e:
        error_logger.error(f"Failed to get user info: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: `{str(e)[:100]}`", parse_mode="Markdown")
        return

    if not user_data:
        await update.message.reply_text(
            f"❌ User with ID `{target_id}` not found in database.",
            parse_mode="Markdown"
        )
        return

    # Format user info
    username = user_data.get("username") or "N/A"
    first_name = user_data.get("first_name") or "N/A"
    coins = user_data.get("coins", 0)
    total_catches = user_data.get("total_catches", 0)
    card_count = user_data.get("card_count", 0)
    legendary_count = user_data.get("legendary_count", 0)
    is_banned = user_data.get("is_banned", False)
    ban_reason = user_data.get("ban_reason") or "N/A"
    created_at = user_data.get("created_at")

    created_str = created_at.strftime("%Y-%m-%d %H:%M") if created_at else "Unknown"

    # Create management keyboard
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Reset Cards", callback_data=f"admin_user_resetcards_{target_id}"),
            InlineKeyboardButton("💰 Reset Coins", callback_data=f"admin_user_resetcoins_{target_id}"),
        ],
        [
            InlineKeyboardButton("🗑️ Reset All", callback_data=f"admin_user_resetall_{target_id}"),
        ],
        [
            InlineKeyboardButton(
                "🔓 Unban" if is_banned else "🔨 Ban",
                callback_data=f"admin_user_toggleban_{target_id}"
            ),
        ],
        [
            InlineKeyboardButton("❌ Close", callback_data="admin_user_close"),
        ]
    ])

    ban_status = "🔨 BANNED" if is_banned else "✅ Active"

    await update.message.reply_text(
        f"👤 *User Information*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 *ID:* `{target_id}`\n"
        f"👤 *Name:* {first_name}\n"
        f"📛 *Username:* @{username}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *Coins:* `{coins:,}`\n"
        f"🎴 *Cards:* `{card_count}`\n"
        f"💎 *Legendaries:* `{legendary_count}`\n"
        f"🎯 *Total Catches:* `{total_catches}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 *Status:* {ban_status}\n"
        f"📝 *Ban Reason:* {ban_reason}\n"
        f"📅 *Joined:* {created_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Select an action:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


async def user_management_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle user management callbacks."""
    query = update.callback_query
    user = query.from_user
    data = query.data

    if not is_admin(user.id):
        await query.answer("❌ Not authorized.", show_alert=True)
        return

    await query.answer()

    if data == "admin_user_close":
        await query.edit_message_text("👤 *User management closed.*", parse_mode="Markdown")
        return

    # Parse target user ID
    if data.startswith("admin_user_resetcards_"):
        target_id = int(data.replace("admin_user_resetcards_", ""))

        try:
            # FIXED: Use 'collections' table instead of 'user_cards'
            await db.execute("DELETE FROM collections WHERE user_id = $1", target_id)

            await query.edit_message_text(
                f"✅ *Cards Reset*\n\n"
                f"All cards removed from user `{target_id}`",
                parse_mode="Markdown"
            )
            app_logger.info(f"🔄 User {target_id} cards reset by admin {user.id}")

        except Exception as e:
            error_logger.error(f"Failed to reset cards: {e}", exc_info=True)
            await query.edit_message_text(f"❌ Error: `{str(e)[:100]}`", parse_mode="Markdown")

    elif data.startswith("admin_user_resetcoins_"):
        target_id = int(data.replace("admin_user_resetcoins_", ""))

        try:
            await db.execute("UPDATE users SET coins = 0 WHERE user_id = $1", target_id)

            await query.edit_message_text(
                f"✅ *Coins Reset*\n\n"
                f"Coins set to 0 for user `{target_id}`",
                parse_mode="Markdown"
            )
            app_logger.info(f"💰 User {target_id} coins reset by admin {user.id}")

        except Exception as e:
            error_logger.error(f"Failed to reset coins: {e}", exc_info=True)
            await query.edit_message_text(f"❌ Error: `{str(e)[:100]}`", parse_mode="Markdown")

    elif data.startswith("admin_user_resetall_"):
        target_id = int(data.replace("admin_user_resetall_", ""))

        try:
            # FIXED: Use 'collections' table instead of 'user_cards'
            await db.execute("DELETE FROM collections WHERE user_id = $1", target_id)
            # Reset coins and stats
            await db.execute(
                "UPDATE users SET coins = 0, total_catches = 0 WHERE user_id = $1",
                target_id
            )

            await query.edit_message_text(
                f"✅ *Full Reset Complete*\n\n"
                f"User `{target_id}` has been reset:\n"
                f"• All cards removed\n"
                f"• Coins set to 0\n"
                f"• Stats cleared",
                parse_mode="Markdown"
            )
            app_logger.info(f"🗑️ User {target_id} fully reset by admin {user.id}")

        except Exception as e:
            error_logger.error(f"Failed to reset user: {e}", exc_info=True)
            await query.edit_message_text(f"❌ Error: `{str(e)[:100]}`", parse_mode="Markdown")

    elif data.startswith("admin_user_toggleban_"):
        target_id = int(data.replace("admin_user_toggleban_", ""))

        try:
            # Get current ban status
            current = await db.fetchrow("SELECT is_banned FROM users WHERE user_id = $1", target_id)

            if current:
                new_status = not current["is_banned"]
                await db.execute(
                    "UPDATE users SET is_banned = $1, ban_reason = $2 WHERE user_id = $3",
                    new_status,
                    "Banned by admin" if new_status else None,
                    target_id
                )

                status_text = "banned 🔨" if new_status else "unbanned 🔓"

                await query.edit_message_text(
                    f"✅ *User {status_text}*\n\n"
                    f"User `{target_id}` has been {status_text}",
                    parse_mode="Markdown"
                )
                app_logger.info(f"🔨 User {target_id} {status_text} by admin {user.id}")

        except Exception as e:
            error_logger.error(f"Failed to toggle ban: {e}", exc_info=True)
            await query.edit_message_text(f"❌ Error: `{str(e)[:100]}`", parse_mode="Markdown")


# ============================================================
# 🎁 Give Card Command
# ============================================================

async def give_card_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /gcard command - Give a card to a user."""
    user = update.effective_user
    log_command(user.id, "gcard", update.effective_chat.id)

    if not is_admin(user.id):
        await update.message.reply_text("❌ Admin only command.")
        return

    # Get target user
    target_id = None
    target_name = "User"

    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        target_name = update.message.reply_to_message.from_user.first_name

    if not target_id:
        await update.message.reply_text(
            "🎁 *Give Card*\n\n"
            "*Usage:* Reply to a user's message with:\n"
            "`/gcard <card_id>`\n\n"
            "*Example:* `/gcard 42`",
            parse_mode="Markdown"
        )
        return

    # Get card ID
    if not context.args:
        await update.message.reply_text(
            "❌ Please provide a card ID.\n\n"
            "*Usage:* `/gcard <card_id>`",
            parse_mode="Markdown"
        )
        return

    try:
        card_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid card ID.")
        return

    # Get card info
    card = await get_card_by_id(None, card_id)

    if not card:
        await update.message.reply_text(f"❌ Card with ID `{card_id}` not found.", parse_mode="Markdown")
        return

    character = card["character_name"]
    anime = card["anime"]
    rarity = card["rarity"]
    rarity_name, _, rarity_emoji = rarity_to_text(rarity)

    # Ensure user exists
    await ensure_user(None, target_id, None, target_name, None)

    # Add card to collection
    try:
        await add_to_collection(None, target_id, card_id, update.effective_chat.id)

        await update.message.reply_text(
            f"🎁 *Card Given!*\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 *To:* [{target_name}](tg://user?id={target_id})\n"
            f"🎴 *Card:* {character}\n"
            f"🎬 *Anime:* {anime}\n"
            f"✨ *Rarity:* {rarity_emoji} {rarity_name}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━",
            parse_mode="Markdown"
        )

        app_logger.info(f"🎁 Card {card_id} given to {target_id} by admin {user.id}")

    except Exception as e:
        error_logger.error(f"Failed to give card: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: `{str(e)[:100]}`", parse_mode="Markdown")


# ============================================================
# 💰 Give Coins Command
# ============================================================

async def give_coins_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /gcoins command - Give coins to a user."""
    user = update.effective_user
    log_command(user.id, "gcoins", update.effective_chat.id)

    if not is_admin(user.id):
        await update.message.reply_text("❌ Admin only command.")
        return

    # Get target user
    target_id = None
    target_name = "User"

    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        target_name = update.message.reply_to_message.from_user.first_name

    if not target_id:
        await update.message.reply_text(
            "💰 *Give Coins*\n\n"
            "*Usage:* Reply to a user's message with:\n"
            "`/gcoins <amount>`\n\n"
            "*Example:* `/gcoins 1000`\n"
            "*Negative:* `/gcoins -500` (to remove coins)",
            parse_mode="Markdown"
        )
        return

    # Get amount
    if not context.args:
        await update.message.reply_text(
            "❌ Please provide an amount.\n\n"
            "*Usage:* `/gcoins <amount>`",
            parse_mode="Markdown"
        )
        return

    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid amount. Please provide a number.")
        return

    # Ensure user exists
    await ensure_user(None, target_id, None, target_name, None)

    # Update coins
    try:
        await update_user_stats(None, target_id, coins_delta=amount)

        # Get new balance
        new_balance = await db.fetchval(
            "SELECT coins FROM users WHERE user_id = $1",
            target_id
        )

        action = "added to" if amount >= 0 else "removed from"
        amount_display = abs(amount)

        await update.message.reply_text(
            f"💰 *Coins Updated!*\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 *User:* [{target_name}](tg://user?id={target_id})\n"
            f"💵 *Amount:* `{amount_display:,}` coins {action}\n"
            f"💰 *New Balance:* `{new_balance:,}` coins\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━",
            parse_mode="Markdown"
        )

        app_logger.info(f"💰 {amount} coins given to {target_id} by admin {user.id}")

    except Exception as e:
        error_logger.error(f"Failed to give coins: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: `{str(e)[:100]}`", parse_mode="Markdown")


# ============================================================
# 🔧 Additional Admin Commands
# ============================================================

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stats command - Quick stats view."""
    user = update.effective_user

    if not is_admin(user.id):
        await update.message.reply_text("❌ Admin only command.")
        return

    stats = await get_global_stats(None)

    await update.message.reply_text(
        "📊 *Quick Stats*\n\n"
        f"👥 Users: `{stats['total_users']:,}`\n"
        f"🎴 Cards: `{stats['total_cards']:,}`\n"
        f"🎯 Catches: `{stats['total_catches']:,}`\n"
        f"💬 Groups: `{stats['active_groups']:,}`\n"
        f"⏱️ Uptime: {get_uptime()}",
        parse_mode="Markdown"
    )


async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ban command - Ban a user."""
    user = update.effective_user

    if not is_admin(user.id):
        await update.message.reply_text("❌ Admin only command.")
        return

    args = context.args

    if not args:
        await update.message.reply_text(
            "📝 *Usage:* `/ban <user_id> [reason]`\n\n"
            "Example: `/ban 123456789 Spamming`",
            parse_mode="Markdown"
        )
        return

    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")
        return

    reason = " ".join(args[1:]) if len(args) > 1 else "No reason provided"

    try:
        await db.execute(
            "UPDATE users SET is_banned = TRUE, ban_reason = $2 WHERE user_id = $1",
            target_id, reason
        )

        await update.message.reply_text(
            f"✅ *User Banned*\n\n"
            f"🆔 User ID: `{target_id}`\n"
            f"📝 Reason: {reason}",
            parse_mode="Markdown"
        )

        app_logger.info(f"🔨 User {target_id} banned by admin {user.id}. Reason: {reason}")

    except Exception as e:
        error_logger.error(f"Failed to ban user {target_id}: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {e}")


async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /unban command - Unban a user."""
    user = update.effective_user

    if not is_admin(user.id):
        await update.message.reply_text("❌ Admin only command.")
        return

    args = context.args

    if not args:
        await update.message.reply_text(
            "📝 *Usage:* `/unban <user_id>`",
            parse_mode="Markdown"
        )
        return

    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")
        return

    try:
        await db.execute(
            "UPDATE users SET is_banned = FALSE, ban_reason = NULL WHERE user_id = $1",
            target_id
        )

        await update.message.reply_text(
            f"✅ *User Unbanned*\n\n"
            f"🆔 User ID: `{target_id}`",
            parse_mode="Markdown"
        )

        app_logger.info(f"✅ User {target_id} unbanned by admin {user.id}")

    except Exception as e:
        error_logger.error(f"Failed to unban user {target_id}: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {e}")


# ============================================================
# 🔧 Command Handlers Export
# ============================================================

admin_command_handler = CommandHandler("admin", admin_command)
stats_command_handler = CommandHandler("stats", stats_command)
ban_command_handler = CommandHandler("ban", ban_command)
unban_command_handler = CommandHandler("unban", unban_command)

# New admin command handlers
delete_command_handler = CommandHandler("delete", delete_card_command)
userinfo_command_handler = CommandHandler("userinfo", userinfo_command)
give_card_command_handler = CommandHandler("gcard", give_card_command)
give_coins_command_handler = CommandHandler("gcoins", give_coins_command)

# Callback handlers for admin functions
delete_card_callback_handler = CallbackQueryHandler(
    delete_card_callback,
    pattern=r"^admin_delcard_"
)

user_management_callback_handler = CallbackQueryHandler(
    user_management_callback,
    pattern=r"^admin_user_"
)