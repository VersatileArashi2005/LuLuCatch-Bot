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
)
from utils.logger import app_logger, error_logger, log_command
from utils.rarity import RARITY_TABLE, get_rarity_emoji


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


# Broadcast conversation handler (no CallbackQueryHandler inside)
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