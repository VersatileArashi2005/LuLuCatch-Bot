# ============================================================
# 📁 File: handlers/admin.py (Part 1 of 2)
# 📍 Location: telegram_card_bot/handlers/admin.py
# 📝 Description: Modern admin panel with clean UI
# ============================================================

import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any

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
from telegram.constants import ParseMode

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
from utils.rarity import RARITY_TABLE, get_rarity_emoji, rarity_to_text
from utils.constants import (
    RARITY_EMOJIS,
    RARITY_NAMES,
    ButtonLabels,
    format_number,
)


# ============================================================
# ⏱️ Bot Start Time
# ============================================================

_bot_start_time: Optional[datetime] = None


def set_bot_start_time() -> None:
    """Set the bot start time."""
    global _bot_start_time
    _bot_start_time = datetime.now()


def get_uptime() -> str:
    """Get formatted uptime string."""
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


set_bot_start_time()


# ============================================================
# 🔐 Admin Check
# ============================================================

def is_admin(user_id: int) -> bool:
    """Check if user is admin."""
    return Config.is_admin(user_id)


async def check_admin(update: Update) -> bool:
    """Check admin permission with error message."""
    user = update.effective_user

    if not is_admin(user.id):
        if update.callback_query:
            await update.callback_query.answer("🚫 Not authorized", show_alert=True)
        else:
            await update.message.reply_text(
                "🚫 *Permission Denied*\n\n"
                "This command requires admin access.",
                parse_mode=ParseMode.MARKDOWN
            )
        error_logger.warning(f"⚠️ Unauthorized admin access: {user.id}")
        return False
    return True


# ============================================================
# 👑 Admin Panel Command
# ============================================================

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /admin - Show modern admin panel."""
    user = update.effective_user
    log_command(user.id, "admin", update.effective_chat.id)

    if not await check_admin(update):
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Stats", callback_data="adm:stats"),
            InlineKeyboardButton("🎴 Cards", callback_data="adm:cards"),
        ],
        [
            InlineKeyboardButton("👥 Users", callback_data="adm:users"),
            InlineKeyboardButton("💬 Groups", callback_data="adm:groups"),
        ],
        [
            InlineKeyboardButton("📢 Broadcast", callback_data="adm:broadcast"),
            InlineKeyboardButton("❤️ Health", callback_data="adm:health"),
        ],
        [
            InlineKeyboardButton(ButtonLabels.CLOSE, callback_data="adm:close"),
        ],
    ])

    stats = await get_global_stats(None)

    await update.message.reply_text(
        f"👑 *Admin Panel*\n\n"
        f"👤 {user.first_name}\n"
        f"⏱️ Uptime: {get_uptime()}\n\n"
        f"📊 *Quick Stats*\n"
        f"├ Users: {format_number(stats.get('total_users', 0))}\n"
        f"├ Cards: {format_number(stats.get('total_cards', 0))}\n"
        f"├ Catches: {format_number(stats.get('total_catches', 0))}\n"
        f"└ Groups: {format_number(stats.get('active_groups', 0))}\n\n"
        f"Select an option:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle admin panel callbacks."""
    query = update.callback_query
    user = query.from_user
    data = query.data

    if not is_admin(user.id):
        await query.answer("🚫 Not authorized", show_alert=True)
        return

    await query.answer()

    # Statistics
    if data == "adm:stats":
        stats = await get_global_stats(None)

        text = (
            f"📊 *Bot Statistics*\n\n"
            f"👥 Users: {format_number(stats.get('total_users', 0))}\n"
            f"🎴 Cards: {format_number(stats.get('total_cards', 0))}\n"
            f"🎯 Catches: {format_number(stats.get('total_catches', 0))}\n"
            f"💬 Groups: {format_number(stats.get('active_groups', 0))}\n\n"
            f"⏱️ Uptime: {get_uptime()}"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(ButtonLabels.REFRESH, callback_data="adm:stats")],
            [InlineKeyboardButton(ButtonLabels.BACK, callback_data="adm:back")],
        ])

        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

    # Cards Info
    elif data == "adm:cards":
        total_cards = await get_card_count(None)
        distribution = await get_rarity_distribution(None)

        dist_lines = []
        for row in distribution:
            rid = row["rarity"]
            count = row["count"]
            emoji = RARITY_EMOJIS.get(rid, "❓")
            name = RARITY_NAMES.get(rid, "Unknown")
            dist_lines.append(f"{emoji} {name}: {count}")

        dist_text = "\n".join(dist_lines) if dist_lines else "_No cards yet_"

        text = (
            f"🎴 *Cards Database*\n\n"
            f"📦 Total: {format_number(total_cards)}\n\n"
            f"*By Rarity:*\n{dist_text}"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(ButtonLabels.BACK, callback_data="adm:back")],
        ])

        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

    # Users
    elif data == "adm:users":
        stats = await get_global_stats(None)

        text = (
            f"👥 *Users*\n\n"
            f"📊 Total: {format_number(stats.get('total_users', 0))}\n"
            f"👑 Admins: {len(Config.ADMIN_IDS)}\n\n"
            f"*Commands:*\n"
            f"• `/userinfo <id>` - View user\n"
            f"• `/gcard <id>` - Give card\n"
            f"• `/gcoins <amt>` - Give coins"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(ButtonLabels.BACK, callback_data="adm:back")],
        ])

        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

    # Groups
    elif data == "adm:groups":
        groups = await get_all_groups(None, active_only=True)

        if groups:
            lines = []
            for i, g in enumerate(groups[:8], 1):
                name = (g.get("group_name") or "Unknown")[:20]
                catches = g.get("total_catches", 0)
                lines.append(f"{i}. {name} • 🎯 {catches}")
            groups_text = "\n".join(lines)
            
            if len(groups) > 8:
                groups_text += f"\n_...and {len(groups) - 8} more_"
        else:
            groups_text = "_No active groups_"

        text = (
            f"💬 *Active Groups*\n\n"
            f"📊 Total: {len(groups)}\n\n"
            f"{groups_text}"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(ButtonLabels.REFRESH, callback_data="adm:groups")],
            [InlineKeyboardButton(ButtonLabels.BACK, callback_data="adm:back")],
        ])

        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

    # Broadcast
    elif data == "adm:broadcast":
        text = (
            f"📢 *Broadcast*\n\n"
            f"Send message to all users:\n"
            f"`/broadcast Your message`\n\n"
            f"⚠️ Use carefully!"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(ButtonLabels.BACK, callback_data="adm:back")],
        ])

        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

    # Health Check
    elif data == "adm:health":
        is_healthy = await health_check(None)
        db_status = "✅ Connected" if is_healthy else "❌ Disconnected"

        text = (
            f"❤️ *Health Check*\n\n"
            f"🗄️ Database: {db_status}\n"
            f"🤖 Bot: ✅ Running\n"
            f"⏱️ Uptime: {get_uptime()}"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(ButtonLabels.REFRESH, callback_data="adm:health")],
            [InlineKeyboardButton(ButtonLabels.BACK, callback_data="adm:back")],
        ])

        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

    # Back
    elif data == "adm:back":
        stats = await get_global_stats(None)
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📊 Stats", callback_data="adm:stats"),
                InlineKeyboardButton("🎴 Cards", callback_data="adm:cards"),
            ],
            [
                InlineKeyboardButton("👥 Users", callback_data="adm:users"),
                InlineKeyboardButton("💬 Groups", callback_data="adm:groups"),
            ],
            [
                InlineKeyboardButton("📢 Broadcast", callback_data="adm:broadcast"),
                InlineKeyboardButton("❤️ Health", callback_data="adm:health"),
            ],
            [
                InlineKeyboardButton(ButtonLabels.CLOSE, callback_data="adm:close"),
            ],
        ])

        await query.edit_message_text(
            f"👑 *Admin Panel*\n\n"
            f"📊 *Quick Stats*\n"
            f"├ Users: {format_number(stats.get('total_users', 0))}\n"
            f"├ Cards: {format_number(stats.get('total_cards', 0))}\n"
            f"└ Groups: {format_number(stats.get('active_groups', 0))}\n\n"
            f"Select an option:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )

    # Close
    elif data == "adm:close":
        await query.edit_message_text(
            "👑 *Panel Closed*\n\nUse /admin to reopen.",
            parse_mode=ParseMode.MARKDOWN
        )


# ============================================================
# 📢 Broadcast System
# ============================================================

BROADCAST_MESSAGE = 0


async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start broadcast flow."""
    user = update.effective_user
    log_command(user.id, "broadcast", update.effective_chat.id)

    if not await check_admin(update):
        return ConversationHandler.END

    message_text = update.message.text.replace("/broadcast", "").strip()

    if message_text:
        context.user_data["broadcast_message"] = message_text
        return await broadcast_execute(update, context)

    await update.message.reply_text(
        "📢 *Broadcast*\n\n"
        "Send the message to broadcast:\n\n"
        "Type /cancel to abort.",
        parse_mode=ParseMode.MARKDOWN
    )

    return BROADCAST_MESSAGE


async def broadcast_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle broadcast message input."""
    context.user_data["broadcast_message"] = update.message.text
    return await broadcast_execute(update, context)


async def broadcast_execute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Execute broadcast."""
    message_text = context.user_data.get("broadcast_message", "")
    user = update.effective_user

    if not message_text:
        await update.message.reply_text("❌ No message provided.")
        return ConversationHandler.END

    try:
        users = await db.fetch("SELECT user_id FROM users WHERE is_banned = FALSE")
    except Exception as e:
        error_logger.error(f"Broadcast user fetch failed: {e}")
        await update.message.reply_text("❌ Failed to get users.")
        return ConversationHandler.END

    total = len(users)
    if total == 0:
        await update.message.reply_text("❌ No users to broadcast to.")
        return ConversationHandler.END

    status_msg = await update.message.reply_text(
        f"📢 *Broadcasting...*\n\nSending to {total} users...",
        parse_mode=ParseMode.MARKDOWN
    )

    success = 0
    blocked = 0
    failed = 0

    for row in users:
        uid = row["user_id"]
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=f"📢 *Announcement*\n\n{message_text}",
                parse_mode=ParseMode.MARKDOWN
            )
            success += 1
            if success % 30 == 0:
                await asyncio.sleep(1)
        except Forbidden:
            blocked += 1
        except TelegramError:
            failed += 1

    await status_msg.edit_text(
        f"📢 *Broadcast Complete*\n\n"
        f"✅ Sent: {success}\n"
        f"🚫 Blocked: {blocked}\n"
        f"❌ Failed: {failed}\n"
        f"📊 Total: {total}",
        parse_mode=ParseMode.MARKDOWN
    )

    app_logger.info(f"📢 Broadcast: {success} sent, {blocked} blocked, {failed} failed")
    return ConversationHandler.END


async def broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel broadcast."""
    await update.message.reply_text("❌ *Broadcast cancelled*", parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END


broadcast_conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("broadcast", broadcast_start)],
    states={
        BROADCAST_MESSAGE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message_received),
        ],
    },
    fallbacks=[CommandHandler("cancel", broadcast_cancel)],
    conversation_timeout=120,
)


# ============================================================
# 🗑️ Delete Card Command
# ============================================================

async def delete_card_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /delete command."""
    user = update.effective_user
    log_command(user.id, "delete", update.effective_chat.id)

    if not is_admin(user.id):
        await update.message.reply_text("🚫 Admin only.")
        return

    if not context.args:
        await update.message.reply_text(
            "🗑️ *Delete Card*\n\n"
            "Usage: `/delete <card_id>`\n"
            "Example: `/delete 42`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        card_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid card ID.")
        return

    card = await get_card_by_id(None, card_id)
    if not card:
        await update.message.reply_text(f"❌ Card `#{card_id}` not found.", parse_mode=ParseMode.MARKDOWN)
        return

    character = card["character_name"]
    anime = card["anime"]
    rarity = card["rarity"]
    emoji = RARITY_EMOJIS.get(rarity, "❓")

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Delete", callback_data=f"del:y:{card_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data="del:n"),
        ]
    ])

    await update.message.reply_text(
        f"🗑️ *Delete Card?*\n\n"
        f"🆔 `#{card_id}`\n"
        f"{emoji} *{character}*\n"
        f"🎬 {anime}\n\n"
        f"⚠️ This removes from all collections!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


async def delete_card_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle delete confirmation."""
    query = update.callback_query
    user = query.from_user
    data = query.data

    if not is_admin(user.id):
        await query.answer("🚫 Not authorized", show_alert=True)
        return

    await query.answer()

    if data == "del:n":
        await query.edit_message_text("❌ *Deletion cancelled*", parse_mode=ParseMode.MARKDOWN)
        return

    if data.startswith("del:y:"):
        try:
            card_id = int(data.split(":")[2])
        except (ValueError, IndexError):
            await query.edit_message_text("❌ Invalid card ID.")
            return

        card = await get_card_by_id(None, card_id)
        if not card:
            await query.edit_message_text("❌ Card not found.")
            return

        character = card["character_name"]

        try:
            await db.execute("DELETE FROM collections WHERE card_id = $1", card_id)
            await db.execute("DELETE FROM cards WHERE card_id = $1", card_id)

            await query.edit_message_text(
                f"✅ *Card Deleted*\n\n"
                f"🆔 `#{card_id}`\n"
                f"👤 {character}",
                parse_mode=ParseMode.MARKDOWN
            )
            app_logger.info(f"🗑️ Card {card_id} deleted by {user.id}")

        except Exception as e:
            error_logger.error(f"Delete failed: {e}")
            await query.edit_message_text(f"❌ Error: {str(e)[:50]}")


# ============================================================
# ✏️ Edit Card System
# ============================================================

EDIT_SELECT_FIELD = 0
EDIT_NEW_VALUE = 1
_edit_sessions: Dict[int, Dict[str, Any]] = {}


async def edit_card_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /edit command."""
    user = update.effective_user
    log_command(user.id, "edit", update.effective_chat.id)

    if not is_admin(user.id):
        await update.message.reply_text("🚫 Admin only.")
        return ConversationHandler.END

    if not context.args:
        await update.message.reply_text(
            "✏️ *Edit Card*\n\n"
            "Usage: `/edit <card_id>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationHandler.END

    try:
        card_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid card ID.")
        return ConversationHandler.END

    card = await get_card_by_id(None, card_id)
    if not card:
        await update.message.reply_text(f"❌ Card `#{card_id}` not found.", parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    _edit_sessions[user.id] = {"card_id": card_id, "card": dict(card)}

    character = card["character_name"]
    anime = card["anime"]
    rarity = card["rarity"]
    emoji = RARITY_EMOJIS.get(rarity, "❓")
    rarity_name = RARITY_NAMES.get(rarity, "Unknown")

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👤 Name", callback_data="edit:character"),
            InlineKeyboardButton("🎬 Anime", callback_data="edit:anime"),
        ],
        [
            InlineKeyboardButton("✨ Rarity", callback_data="edit:rarity"),
        ],
        [
            InlineKeyboardButton("❌ Cancel", callback_data="edit:cancel"),
        ]
    ])

    await update.message.reply_text(
        f"✏️ *Edit Card*\n\n"
        f"🆔 `#{card_id}`\n"
        f"👤 {character}\n"
        f"🎬 {anime}\n"
        f"{emoji} {rarity_name}\n\n"
        f"Select field to edit:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )

    return EDIT_SELECT_FIELD


async def edit_field_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle edit field selection."""
    query = update.callback_query
    user = query.from_user
    data = query.data

    if not is_admin(user.id):
        await query.answer("🚫 Not authorized", show_alert=True)
        return ConversationHandler.END

    await query.answer()

    if data == "edit:cancel":
        _edit_sessions.pop(user.id, None)
        await query.edit_message_text("❌ *Edit cancelled*", parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    session = _edit_sessions.get(user.id)
    if not session:
        await query.edit_message_text("❌ Session expired. Use /edit again.")
        return ConversationHandler.END

    if data == "edit:character":
        session["edit_field"] = "character_name"
        await query.edit_message_text(
            f"👤 *Edit Name*\n\n"
            f"Current: `{session['card']['character_name']}`\n\n"
            f"Send new name:",
            parse_mode=ParseMode.MARKDOWN
        )
        return EDIT_NEW_VALUE

    elif data == "edit:anime":
        session["edit_field"] = "anime"
        await query.edit_message_text(
            f"🎬 *Edit Anime*\n\n"
            f"Current: `{session['card']['anime']}`\n\n"
            f"Send new anime:",
            parse_mode=ParseMode.MARKDOWN
        )
        return EDIT_NEW_VALUE

    elif data == "edit:rarity":
        session["edit_field"] = "rarity"

        buttons = []
        row = []
        for rid in sorted(RARITY_TABLE.keys()):
            emoji = RARITY_EMOJIS.get(rid, "❓")
            row.append(InlineKeyboardButton(emoji, callback_data=f"edit:r:{rid}"))
            if len(row) == 4:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="edit:cancel")])

        await query.edit_message_text(
            f"✨ *Edit Rarity*\n\n"
            f"Current: {RARITY_EMOJIS.get(session['card']['rarity'], '❓')}\n\n"
            f"Select new rarity:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return EDIT_SELECT_FIELD

    elif data.startswith("edit:r:"):
        try:
            new_rarity = int(data.split(":")[2])
        except (ValueError, IndexError):
            await query.edit_message_text("❌ Invalid rarity.")
            return ConversationHandler.END

        card_id = session["card_id"]

        try:
            await db.execute("UPDATE cards SET rarity = $1 WHERE card_id = $2", new_rarity, card_id)
            emoji = RARITY_EMOJIS.get(new_rarity, "❓")
            name = RARITY_NAMES.get(new_rarity, "Unknown")

            await query.edit_message_text(
                f"✅ *Rarity Updated*\n\n"
                f"🆔 `#{card_id}`\n"
                f"✨ {emoji} {name}",
                parse_mode=ParseMode.MARKDOWN
            )
            app_logger.info(f"✏️ Card {card_id} rarity → {new_rarity} by {user.id}")

        except Exception as e:
            error_logger.error(f"Edit failed: {e}")
            await query.edit_message_text(f"❌ Error: {str(e)[:50]}")

        _edit_sessions.pop(user.id, None)
        return ConversationHandler.END

    return EDIT_SELECT_FIELD


async def edit_new_value_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle new value input."""
    user = update.effective_user
    new_value = update.message.text.strip()

    if not is_admin(user.id):
        return ConversationHandler.END

    session = _edit_sessions.get(user.id)
    if not session:
        await update.message.reply_text("❌ Session expired.")
        return ConversationHandler.END

    card_id = session["card_id"]
    field = session["edit_field"]

    if len(new_value) < 2:
        await update.message.reply_text("❌ Value too short.")
        return EDIT_NEW_VALUE

    try:
        await db.execute(f"UPDATE cards SET {field} = $1 WHERE card_id = $2", new_value, card_id)
        field_name = "Name" if field == "character_name" else "Anime"

        await update.message.reply_text(
            f"✅ *{field_name} Updated*\n\n"
            f"🆔 `#{card_id}`\n"
            f"📝 {new_value}",
            parse_mode=ParseMode.MARKDOWN
        )
        app_logger.info(f"✏️ Card {card_id} {field} → '{new_value}' by {user.id}")

    except Exception as e:
        error_logger.error(f"Edit failed: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)[:50]}")

    _edit_sessions.pop(user.id, None)
    return ConversationHandler.END


async def edit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel edit."""
    _edit_sessions.pop(update.effective_user.id, None)
    await update.message.reply_text("❌ *Edit cancelled*", parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END


edit_conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("edit", edit_card_command)],
    states={
        EDIT_SELECT_FIELD: [
            CallbackQueryHandler(edit_field_callback, pattern=r"^edit:"),
        ],
        EDIT_NEW_VALUE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, edit_new_value_handler),
        ],
    },
    fallbacks=[CommandHandler("cancel", edit_cancel)],
    conversation_timeout=120,
    per_message=False,
)


# ============================================================
# 👤 User Info Command
# ============================================================

async def userinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /userinfo command."""
    user = update.effective_user
    log_command(user.id, "userinfo", update.effective_chat.id)

    if not is_admin(user.id):
        await update.message.reply_text("🚫 Admin only.")
        return

    target_id = None
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
    elif context.args:
        try:
            target_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID.")
            return

    if not target_id:
        await update.message.reply_text(
            "👤 *User Info*\n\n"
            "Reply to user or: `/userinfo <id>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        user_data = await db.fetchrow(
            """
            SELECT u.*, COUNT(c.collection_id) as card_count
            FROM users u
            LEFT JOIN collections c ON u.user_id = c.user_id
            WHERE u.user_id = $1
            GROUP BY u.user_id
            """,
            target_id
        )
    except Exception as e:
        error_logger.error(f"User info failed: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)[:50]}")
        return

    if not user_data:
        await update.message.reply_text(f"❌ User `{target_id}` not found.", parse_mode=ParseMode.MARKDOWN)
        return

    username = user_data.get("username") or "N/A"
    first_name = user_data.get("first_name") or "N/A"
    coins = user_data.get("coins", 0)
    catches = user_data.get("total_catches", 0)
    cards = user_data.get("card_count", 0)
    is_banned = user_data.get("is_banned", False)
    status = "🚫 Banned" if is_banned else "✅ Active"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Reset Cards", callback_data=f"usr:rc:{target_id}"),
            InlineKeyboardButton("💰 Reset Coins", callback_data=f"usr:rco:{target_id}"),
        ],
        [
            InlineKeyboardButton(
                "🔓 Unban" if is_banned else "🚫 Ban",
                callback_data=f"usr:tb:{target_id}"
            ),
        ],
        [
            InlineKeyboardButton(ButtonLabels.CLOSE, callback_data="usr:close"),
        ]
    ])

    await update.message.reply_text(
        f"👤 *User Info*\n\n"
        f"🆔 `{target_id}`\n"
        f"👤 {first_name}\n"
        f"📛 @{username}\n\n"
        f"💰 Coins: {format_number(coins)}\n"
        f"🎴 Cards: {cards}\n"
        f"🎯 Catches: {catches}\n\n"
        f"📊 Status: {status}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


async def user_management_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle user management callbacks."""
    query = update.callback_query
    user = query.from_user
    data = query.data

    if not is_admin(user.id):
        await query.answer("🚫 Not authorized", show_alert=True)
        return

    await query.answer()

    if data == "usr:close":
        await query.edit_message_text("👤 *Closed*", parse_mode=ParseMode.MARKDOWN)
        return

    parts = data.split(":")
    if len(parts) < 3:
        return

    action = parts[1]
    target_id = int(parts[2])

    try:
        if action == "rc":  # Reset cards
            await db.execute("DELETE FROM collections WHERE user_id = $1", target_id)
            await query.edit_message_text(f"✅ Cards reset for `{target_id}`", parse_mode=ParseMode.MARKDOWN)
            app_logger.info(f"🔄 User {target_id} cards reset by {user.id}")

        elif action == "rco":  # Reset coins
            await db.execute("UPDATE users SET coins = 0 WHERE user_id = $1", target_id)
            await query.edit_message_text(f"✅ Coins reset for `{target_id}`", parse_mode=ParseMode.MARKDOWN)
            app_logger.info(f"💰 User {target_id} coins reset by {user.id}")

        elif action == "tb":  # Toggle ban
            current = await db.fetchrow("SELECT is_banned FROM users WHERE user_id = $1", target_id)
            if current:
                new_status = not current["is_banned"]
                await db.execute(
                    "UPDATE users SET is_banned = $1, ban_reason = $2 WHERE user_id = $3",
                    new_status, "Admin action" if new_status else None, target_id
                )
                status_text = "banned 🚫" if new_status else "unbanned ✅"
                await query.edit_message_text(f"✅ User `{target_id}` {status_text}", parse_mode=ParseMode.MARKDOWN)
                app_logger.info(f"🔨 User {target_id} {status_text} by {user.id}")

    except Exception as e:
        error_logger.error(f"User management failed: {e}")
        await query.edit_message_text(f"❌ Error: {str(e)[:50]}")


# ============================================================
# 🎁 Give Card & Coins Commands
# ============================================================

async def give_card_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /gcard command."""
    user = update.effective_user

    if not is_admin(user.id):
        await update.message.reply_text("🚫 Admin only.")
        return

    target_id = None
    target_name = "User"

    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        target_name = update.message.reply_to_message.from_user.first_name

    if not target_id or not context.args:
        await update.message.reply_text(
            "🎁 *Give Card*\n\n"
            "Reply to user with:\n"
            "`/gcard <card_id>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        card_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid card ID.")
        return

    card = await get_card_by_id(None, card_id)
    if not card:
        await update.message.reply_text(f"❌ Card `#{card_id}` not found.", parse_mode=ParseMode.MARKDOWN)
        return

    await ensure_user(None, target_id, None, target_name, None)

    try:
        await add_to_collection(None, target_id, card_id, update.effective_chat.id)
        emoji = RARITY_EMOJIS.get(card["rarity"], "❓")

        await update.message.reply_text(
            f"🎁 *Card Given!*\n\n"
            f"👤 [{target_name}](tg://user?id={target_id})\n"
            f"{emoji} {card['character_name']}",
            parse_mode=ParseMode.MARKDOWN
        )
        app_logger.info(f"🎁 Card {card_id} → {target_id} by {user.id}")

    except Exception as e:
        error_logger.error(f"Give card failed: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)[:50]}")


async def give_coins_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /gcoins command."""
    user = update.effective_user

    if not is_admin(user.id):
        await update.message.reply_text("🚫 Admin only.")
        return

    target_id = None
    target_name = "User"

    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        target_name = update.message.reply_to_message.from_user.first_name

    if not target_id or not context.args:
        await update.message.reply_text(
            "💰 *Give Coins*\n\n"
            "Reply to user with:\n"
            "`/gcoins <amount>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid amount.")
        return

    await ensure_user(None, target_id, None, target_name, None)

    try:
        await update_user_stats(None, target_id, coins_delta=amount)
        new_balance = await db.fetchval("SELECT coins FROM users WHERE user_id = $1", target_id)

        action = "added" if amount >= 0 else "removed"

        await update.message.reply_text(
            f"💰 *Coins Updated!*\n\n"
            f"👤 [{target_name}](tg://user?id={target_id})\n"
            f"💵 {abs(amount):,} {action}\n"
            f"💰 Balance: {format_number(new_balance or 0)}",
            parse_mode=ParseMode.MARKDOWN
        )
        app_logger.info(f"💰 {amount} coins → {target_id} by {user.id}")

    except Exception as e:
        error_logger.error(f"Give coins failed: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)[:50]}")


# ============================================================
# 🔧 Quick Stats & Ban Commands
# ============================================================

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stats - Quick stats."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Admin only.")
        return

    stats = await get_global_stats(None)

    await update.message.reply_text(
        f"📊 *Quick Stats*\n\n"
        f"👥 Users: {format_number(stats.get('total_users', 0))}\n"
        f"🎴 Cards: {format_number(stats.get('total_cards', 0))}\n"
        f"🎯 Catches: {format_number(stats.get('total_catches', 0))}\n"
        f"💬 Groups: {format_number(stats.get('active_groups', 0))}\n"
        f"⏱️ Uptime: {get_uptime()}",
        parse_mode=ParseMode.MARKDOWN
    )


async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ban command."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Admin only.")
        return

    if not context.args:
        await update.message.reply_text("Usage: `/ban <user_id> [reason]`", parse_mode=ParseMode.MARKDOWN)
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")
        return

    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason"

    try:
        await db.execute(
            "UPDATE users SET is_banned = TRUE, ban_reason = $2 WHERE user_id = $1",
            target_id, reason
        )
        await update.message.reply_text(
            f"🚫 *User Banned*\n\n`{target_id}`\nReason: {reason}",
            parse_mode=ParseMode.MARKDOWN
        )
        app_logger.info(f"🚫 User {target_id} banned by {update.effective_user.id}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /unban command."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Admin only.")
        return

    if not context.args:
        await update.message.reply_text("Usage: `/unban <user_id>`", parse_mode=ParseMode.MARKDOWN)
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")
        return

    try:
        await db.execute(
            "UPDATE users SET is_banned = FALSE, ban_reason = NULL WHERE user_id = $1",
            target_id
        )
        await update.message.reply_text(f"✅ *User Unbanned*\n\n`{target_id}`", parse_mode=ParseMode.MARKDOWN)
        app_logger.info(f"✅ User {target_id} unbanned by {update.effective_user.id}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


# ============================================================
# 🔧 Handler Exports
# ============================================================

admin_command_handler = CommandHandler("admin", admin_command)
stats_command_handler = CommandHandler("stats", stats_command)
ban_command_handler = CommandHandler("ban", ban_command)
unban_command_handler = CommandHandler("unban", unban_command)

delete_command_handler = CommandHandler("delete", delete_card_command)
userinfo_command_handler = CommandHandler("userinfo", userinfo_command)
give_card_command_handler = CommandHandler("gcard", give_card_command)
give_coins_command_handler = CommandHandler("gcoins", give_coins_command)

delete_card_callback_handler = CallbackQueryHandler(delete_card_callback, pattern=r"^del:")
user_management_callback_handler = CallbackQueryHandler(user_management_callback, pattern=r"^usr:")