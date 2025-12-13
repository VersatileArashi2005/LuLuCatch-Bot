# ============================================================
# 📁 File: commands/leaderboard.py
# 📍 Location: telegram_card_bot/commands/leaderboard.py
# 📝 Description: Modern leaderboard with multiple categories
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
    get_top_catchers,
    ensure_user,
)
from utils.logger import app_logger, error_logger, log_command
from utils.constants import (
    MEDALS,
    Pagination,
    ButtonLabels,
    get_medal,
    format_number,
)
from utils.ui import format_bot_stats


# ============================================================
# 📊 Constants
# ============================================================

PAGE_SIZE = Pagination.LEADERBOARD_PER_PAGE

# Leaderboard types configuration
LEADERBOARD_TYPES = {
    "catches": {
        "title": "🎯 Top Catchers",
        "emoji": "🎯",
        "field": "total_catches",
        "label": "catches",
        "description": "Most cards caught"
    },
    "cards": {
        "title": "🎴 Biggest Collections",
        "emoji": "🎴",
        "field": "total_catches",  # Using catches as proxy
        "label": "cards",
        "description": "Largest collections"
    },
    "coins": {
        "title": "💰 Richest Players",
        "emoji": "💰",
        "field": "coins",
        "label": "coins",
        "description": "Most coins earned"
    },
    "level": {
        "title": "⭐ Highest Levels",
        "emoji": "⭐",
        "field": "level",
        "label": "level",
        "description": "Highest player levels"
    }
}


# ============================================================
# 🏆 Leaderboard Command
# ============================================================

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /leaderboard command.
    Shows top users with category switching.
    """
    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    log_command(user.id, "leaderboard", update.effective_chat.id)

    # Ensure user exists
    await ensure_user(
        pool=None,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

    # Check database
    if not db.is_connected:
        await update.message.reply_text(
            "⚠️ Database offline. Try again later.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Parse arguments for type
    lb_type = "catches"  # Default
    
    if context.args:
        arg = context.args[0].lower()
        if arg in LEADERBOARD_TYPES:
            lb_type = arg

    # Show leaderboard
    await show_leaderboard(
        update=update,
        context=context,
        lb_type=lb_type,
        page=1
    )


# ============================================================
# 📄 Display Leaderboard
# ============================================================

async def show_leaderboard(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    lb_type: str = "catches",
    page: int = 1,
    from_callback: bool = False
) -> None:
    """Display leaderboard with modern UI."""
    
    type_config = LEADERBOARD_TYPES.get(lb_type, LEADERBOARD_TYPES["catches"])
    
    # Get top users
    try:
        if lb_type == "coins":
            users = await db.fetch(
                """
                SELECT user_id, username, first_name, coins, level, total_catches
                FROM users
                WHERE is_banned = FALSE AND coins > 0
                ORDER BY coins DESC
                LIMIT 100
                """
            )
        elif lb_type == "level":
            users = await db.fetch(
                """
                SELECT user_id, username, first_name, coins, level, total_catches
                FROM users
                WHERE is_banned = FALSE AND level > 1
                ORDER BY level DESC, xp DESC
                LIMIT 100
                """
            )
        else:
            # catches or cards
            users = await db.fetch(
                """
                SELECT user_id, username, first_name, coins, level, total_catches
                FROM users
                WHERE is_banned = FALSE AND total_catches > 0
                ORDER BY total_catches DESC
                LIMIT 100
                """
            )
    except Exception as e:
        error_logger.error(f"Leaderboard query error: {e}")
        users = []

    # Empty leaderboard
    if not users:
        text = (
            f"{type_config['title']}\n\n"
            f"No players yet!\n"
            f"Start catching cards to appear here."
        )
        
        keyboard = build_leaderboard_keyboard(lb_type, 1, 1)
        
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
        return

    # Pagination
    total_users = len(users)
    total_pages = max(1, (total_users + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(1, min(page, total_pages))
    
    start_idx = (page - 1) * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, total_users)
    page_users = users[start_idx:end_idx]

    # Find viewer's rank
    viewer_id = update.callback_query.from_user.id if from_callback else update.effective_user.id
    viewer_rank = None
    for i, u in enumerate(users, 1):
        if u["user_id"] == viewer_id:
            viewer_rank = i
            break

    # Build leaderboard text
    lines = [f"*{type_config['title']}*\n"]

    for idx, user_record in enumerate(page_users):
        rank = start_idx + idx + 1
        medal = get_medal(rank)
        
        # User display name
        name = user_record.get("first_name") or user_record.get("username") or "Unknown"
        if len(name) > 15:
            name = name[:14] + "…"
        
        # Get value based on type
        if lb_type == "coins":
            value = user_record.get("coins", 0)
            value_text = f"💰 {format_number(value)}"
        elif lb_type == "level":
            level = user_record.get("level", 1)
            value_text = f"⭐ Lv.{level}"
        else:
            catches = user_record.get("total_catches", 0)
            value_text = f"🎯 {format_number(catches)}"
        
        # Highlight viewer
        if user_record["user_id"] == viewer_id:
            lines.append(f"{medal} *{name}* ← You\n     {value_text}")
        else:
            lines.append(f"{medal} {name}\n     {value_text}")

    leaderboard_text = "\n".join(lines)

    # Viewer rank footer
    rank_text = ""
    if viewer_rank:
        rank_text = f"\n\n📍 Your rank: #{viewer_rank}"
    else:
        rank_text = "\n\n📍 Catch cards to appear here!"

    # Build message
    text = (
        f"{leaderboard_text}"
        f"{rank_text}\n\n"
        f"📄 Page {page}/{total_pages}"
    )

    # Build keyboard
    keyboard = build_leaderboard_keyboard(lb_type, page, total_pages)

    # Send or edit
    if from_callback and update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text=text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
        except Exception:
            pass
        await update.callback_query.answer()
    else:
        await update.message.reply_text(
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )


# ============================================================
# ⌨️ Keyboard Builder
# ============================================================

def build_leaderboard_keyboard(
    current_type: str,
    page: int,
    total_pages: int
) -> InlineKeyboardMarkup:
    """Build leaderboard keyboard with type switching and pagination."""
    
    buttons = []

    # Row 1: Type selector
    type_row = []
    for type_key, type_config in LEADERBOARD_TYPES.items():
        emoji = type_config["emoji"]
        if type_key == current_type:
            label = f"{emoji} ✓"
        else:
            label = emoji
        
        type_row.append(
            InlineKeyboardButton(
                label,
                callback_data=f"lb:{type_key}:1"
            )
        )
    buttons.append(type_row)

    # Row 2: Navigation
    nav_row = []
    
    if page > 1:
        nav_row.append(
            InlineKeyboardButton(
                ButtonLabels.PREV,
                callback_data=f"lb:{current_type}:{page - 1}"
            )
        )
    
    nav_row.append(
        InlineKeyboardButton(
            f"{page}/{total_pages}",
            callback_data="noop"
        )
    )
    
    if page < total_pages:
        nav_row.append(
            InlineKeyboardButton(
                ButtonLabels.NEXT,
                callback_data=f"lb:{current_type}:{page + 1}"
            )
        )
    
    buttons.append(nav_row)

    # Row 3: Refresh & Close
    buttons.append([
        InlineKeyboardButton(
            ButtonLabels.REFRESH,
            callback_data=f"lb:{current_type}:{page}"
        ),
        InlineKeyboardButton(
            ButtonLabels.CLOSE,
            callback_data="lb_close"
        )
    ])

    return InlineKeyboardMarkup(buttons)


# ============================================================
# 🔘 Callback Handler
# ============================================================

async def leaderboard_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle leaderboard callbacks."""
    
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data

    # Noop
    if data == "noop":
        await query.answer()
        return

    # Close
    if data == "lb_close":
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.answer()
        return

    # Navigation/Type switch: lb:{type}:{page}
    if data.startswith("lb:"):
        try:
            parts = data.split(":")
            lb_type = parts[1]
            page = int(parts[2])
            
            if lb_type not in LEADERBOARD_TYPES:
                lb_type = "catches"
            
            await show_leaderboard(
                update=update,
                context=context,
                lb_type=lb_type,
                page=page,
                from_callback=True
            )
        except (ValueError, IndexError):
            await query.answer("Error", show_alert=True)
        return


# ============================================================
# 📊 Top Command (Alias)
# ============================================================

async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Alias for /leaderboard."""
    await leaderboard_command(update, context)


# ============================================================
# 📈 Stats Command (Bot Statistics)
# ============================================================

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /stats command.
    Shows global bot statistics.
    """
    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    log_command(user.id, "stats", update.effective_chat.id)

    if not db.is_connected:
        await update.message.reply_text(
            "⚠️ Database offline.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Get stats
    stats = await get_global_stats(None)
    
    text = (
        f"📊 *LuLuCatch Statistics*\n\n"
        f"👥 *Players:* {format_number(stats.get('total_users', 0))}\n"
        f"🎴 *Cards:* {format_number(stats.get('total_cards', 0))}\n"
        f"🎯 *Total Catches:* {format_number(stats.get('total_catches', 0))}\n"
        f"💬 *Active Groups:* {format_number(stats.get('active_groups', 0))}\n"
    )

    # Add rarity breakdown if admin
    if Config.is_admin(user.id):
        try:
            rarity_stats = await db.fetch(
                """
                SELECT rarity, COUNT(*) as count
                FROM cards
                WHERE is_active = TRUE
                GROUP BY rarity
                ORDER BY rarity DESC
                """
            )
            
            if rarity_stats:
                from utils.rarity import rarity_to_text
                text += "\n📈 *Cards by Rarity*\n"
                for row in rarity_stats:
                    _, _, emoji = rarity_to_text(row["rarity"])
                    text += f"{emoji} {row['count']} cards\n"
        except Exception:
            pass

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🏆 Leaderboard", callback_data="lb:catches:1"),
        InlineKeyboardButton(ButtonLabels.CLOSE, callback_data="lb_close")
    ]])

    await update.message.reply_text(
        text=text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


# ============================================================
# 📦 Handler Registration
# ============================================================

def register_leaderboard_handlers(application: Application) -> None:
    """Register leaderboard and stats handlers."""
    
    # Commands
    application.add_handler(CommandHandler("leaderboard", leaderboard_command))
    application.add_handler(CommandHandler("top", top_command))
    application.add_handler(CommandHandler("lb", leaderboard_command))  # Short alias
    application.add_handler(CommandHandler("stats", stats_command))

    # Callbacks
    application.add_handler(
        CallbackQueryHandler(leaderboard_callback_handler, pattern=r"^lb:")
    )
    application.add_handler(
        CallbackQueryHandler(leaderboard_callback_handler, pattern=r"^lb_")
    )

    app_logger.info("✅ Leaderboard handlers registered")