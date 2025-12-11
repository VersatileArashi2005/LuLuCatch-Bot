# ============================================================
# 📁 File: commands/leaderboard.py
# 📍 Location: telegram_card_bot/commands/leaderboard.py
# 📝 Description: Leaderboard and global statistics
# ============================================================

from typing import Optional, List
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode

from config import Config
from db import (
    db,
    get_global_stats,
    get_rarity_distribution,
    get_top_catchers,
)
from utils.logger import app_logger, error_logger, log_command
from utils.rarity import rarity_to_text, RARITY_TABLE


# ============================================================
# 📊 Constants
# ============================================================

LEADERBOARD_PAGE_SIZE = 10  # Users per page


# ============================================================
# 🏆 Leaderboard Command Handler
# ============================================================

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /leaderboard command.
    Shows top users by total catches with pagination.
    """
    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    log_command(user.id, "leaderboard", update.effective_chat.id)

    # Check DB connection
    if not db.is_connected:
        await update.message.reply_text(
            "⚠️ Database is currently offline. Please try again later.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Parse arguments (optional: by=total or by=rarity:X)
    leaderboard_type = "total"  # Default
    page = 1

    if context.args:
        for arg in context.args:
            if arg.startswith("by="):
                leaderboard_type = arg.split("=")[1]
            elif arg.startswith("page="):
                try:
                    page = int(arg.split("=")[1])
                except ValueError:
                    page = 1

    # Show leaderboard
    await show_leaderboard_page(update, context, leaderboard_type, page)


async def show_leaderboard_page(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    leaderboard_type: str = "total",
    page: int = 1,
    from_callback: bool = False
) -> None:
    """
    Display a paginated leaderboard.
    
    Args:
        update: Telegram update
        context: Bot context
        leaderboard_type: Type of leaderboard (total, rarity:X)
        page: Page number (1-indexed)
        from_callback: Whether this is from a callback
    """
    # Get top catchers
    # For now, we'll implement "total catches" leaderboard
    # You can extend this to support rarity-specific leaderboards

    offset = (page - 1) * LEADERBOARD_PAGE_SIZE
    limit = LEADERBOARD_PAGE_SIZE

    # Get top users (simplified - uses existing function)
    top_users = await get_top_catchers(None, limit=100)  # Get top 100

    if not top_users:
        text = (
            "🏆 *Leaderboard*\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "No users yet!\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )

        if from_callback and update.callback_query:
            await update.callback_query.edit_message_text(
                text=text,
                parse_mode=ParseMode.MARKDOWN
            )
            await update.callback_query.answer()
        else:
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        return

    # Calculate pagination
    total_users = len(top_users)
    total_pages = (total_users + LEADERBOARD_PAGE_SIZE - 1) // LEADERBOARD_PAGE_SIZE
    page = max(1, min(page, total_pages))

    # Get users for this page
    start_idx = offset
    end_idx = min(offset + LEADERBOARD_PAGE_SIZE, total_users)
    page_users = top_users[start_idx:end_idx]

    # Build leaderboard text
    leaderboard_lines = []

    for idx, user_record in enumerate(page_users, start=start_idx + 1):
        user_id = user_record.get("user_id")
        first_name = user_record.get("first_name", "Unknown")
        username = user_record.get("username")
        total_catches = user_record.get("total_catches", 0)
        level = user_record.get("level", 1)

        # Medal for top 3
        if idx == 1:
            medal = "🥇"
        elif idx == 2:
            medal = "🥈"
        elif idx == 3:
            medal = "🥉"
        else:
            medal = f"{idx}."

        # Username display
        if username:
            user_display = f"@{username}"
        else:
            user_display = f"{first_name}"

        leaderboard_lines.append(
            f"{medal} *{user_display}*\n"
            f"   🎯 {total_catches:,} catches • ⭐ Lv.{level}"
        )

    leaderboard_text = "\n\n".join(leaderboard_lines)

    # Build message
    text = (
        f"🏆 *Top Catchers Leaderboard*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{leaderboard_text}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📄 Page {page}/{total_pages}"
    )

    # Build pagination keyboard
    keyboard = build_leaderboard_keyboard(leaderboard_type, page, total_pages)

    # Send or edit message
    if from_callback and update.callback_query:
        await update.callback_query.edit_message_text(
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        await update.callback_query.answer()
    else:
        await update.message.reply_text(
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )


def build_leaderboard_keyboard(
    leaderboard_type: str,
    page: int,
    total_pages: int
) -> InlineKeyboardMarkup:
    """
    Build pagination keyboard for leaderboard.
    
    Args:
        leaderboard_type: Type of leaderboard
        page: Current page
        total_pages: Total pages
        
    Returns:
        InlineKeyboardMarkup with navigation buttons
    """
    buttons = []

    # Navigation row
    nav_buttons = []

    if page > 1:
        nav_buttons.append(
            InlineKeyboardButton("⬅️ Prev", callback_data=f"leader:{leaderboard_type}:{page-1}")
        )

    nav_buttons.append(
        InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop")
    )

    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton("Next ➡️", callback_data=f"leader:{leaderboard_type}:{page+1}")
        )

    buttons.append(nav_buttons)

    # Close button
    buttons.append([
        InlineKeyboardButton("❌ Close", callback_data="close")
    ])

    return InlineKeyboardMarkup(buttons)


# ============================================================
# 🔘 Leaderboard Callback Handler
# ============================================================

async def leaderboard_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle leaderboard pagination callbacks.
    
    Pattern: leader:{type}:{page}
    """
    query = update.callback_query

    if not query or not query.data:
        return

    # Handle noop
    if query.data == "noop":
        await query.answer()
        return

    # Handle close
    if query.data == "close":
        await query.message.delete()
        await query.answer("Closed")
        return

    # Parse callback data
    try:
        parts = query.data.split(":")
        if parts[0] != "leader":
            return

        leaderboard_type = parts[1]
        page = int(parts[2])

    except (ValueError, IndexError):
        await query.answer("Invalid data", show_alert=True)
        return

    # Show the requested page
    await show_leaderboard_page(update, context, leaderboard_type, page, from_callback=True)


# ============================================================
# 📊 Stats Command Handler (Admin Only)
# ============================================================

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /stats command.
    Shows global bot statistics (admin only).
    """
    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    log_command(user.id, "stats", update.effective_chat.id)

    # Check admin permission
    if not Config.is_admin(user.id):
        await update.message.reply_text(
            "❌ This command is for admins only.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Check DB connection
    if not db.is_connected:
        await update.message.reply_text(
            "⚠️ Database is currently offline.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Get global stats
    global_stats = await get_global_stats(None)

    # Get rarity distribution
    rarity_dist = await get_rarity_distribution(None)

    # Build rarity distribution text
    rarity_lines = []
    for row in rarity_dist:
        rarity_id = row.get("rarity", 1)
        count = row.get("count", 0)
        
        rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity_id)
        
        rarity_lines.append(f"  {rarity_emoji} {rarity_name}: {count}")

    rarity_text = "\n".join(rarity_lines) if rarity_lines else "  None"

    # Build message
    text = (
        "📊 *Global Bot Statistics*\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 *Total Users:* {global_stats['total_users']:,}\n"
        f"🎴 *Total Cards:* {global_stats['total_cards']:,}\n"
        f"🎯 *Total Catches:* {global_stats['total_catches']:,}\n"
        f"💬 *Active Groups:* {global_stats['active_groups']:,}\n\n"
        f"✨ *Rarity Distribution:*\n{rarity_text}\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ============================================================
# 📦 Handler Registration
# ============================================================

def register_leaderboard_handlers(application: Application) -> None:
    """
    Register leaderboard and stats handlers.
    
    Args:
        application: Telegram bot application
    """
    # Command handlers
    application.add_handler(CommandHandler("leaderboard", leaderboard_command))
    application.add_handler(CommandHandler("stats", stats_command))

    # Callback query handlers
    application.add_handler(
        CallbackQueryHandler(leaderboard_callback_handler, pattern=r"^leader:")
    )

    app_logger.info("✅ Leaderboard handlers registered")