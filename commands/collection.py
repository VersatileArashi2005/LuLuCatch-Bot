# ============================================================
# 📁 File: commands/collection.py
# 📍 Location: telegram_card_bot/commands/collection.py
# 📝 Description: Collection viewer with pagination (inline + command)
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

from db import (
    db,
    ensure_user,
    get_collection_cards,
    get_collection_count,
    get_user_by_id,
)
from utils.logger import app_logger, error_logger, log_command
from utils.rarity import rarity_to_text


# ============================================================
# 📊 Constants
# ============================================================

CARDS_PER_PAGE = 5  # Cards shown per page


# ============================================================
# 🎴 Collection Command Handler
# ============================================================

async def collection_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /collection command.
    Shows user's own collection with pagination.
    """
    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    log_command(user.id, "collection", update.effective_chat.id)

    # Ensure user exists
    await ensure_user(
        pool=None,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

    # Check DB connection
    if not db.is_connected:
        await update.message.reply_text(
            "⚠️ Database is currently offline. Please try again later.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Show collection page 1
    await show_collection_page(update, context, user.id, page=1)


async def show_collection_page(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    page: int = 1,
    rarity_filter: Optional[int] = None
) -> None:
    """
    Display a paginated collection view.
    
    Args:
        update: Telegram update
        context: Bot context
        user_id: User whose collection to show
        page: Page number (1-indexed)
        rarity_filter: Optional rarity filter
    """
    # Get user info
    user_info = await get_user_by_id(None, user_id)
    if not user_info:
        if update.callback_query:
            await update.callback_query.answer("User not found!", show_alert=True)
        return

    user_name = user_info.get("first_name", "User")

    # Get total count
    total_count = await get_collection_count(None, user_id, rarity_filter)

    if total_count == 0:
        text = (
            f"🎴 *{user_name}'s Collection*\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📦 No cards collected yet!\n\n"
            "💡 Use /catch in groups to collect cards."
        )

        if update.callback_query:
            await update.callback_query.edit_message_text(
                text=text,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        return

    # Calculate pagination
    total_pages = (total_count + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE
    page = max(1, min(page, total_pages))  # Clamp page number
    offset = (page - 1) * CARDS_PER_PAGE

    # Get cards for this page
    cards = await get_collection_cards(
        pool=None,
        user_id=user_id,
        offset=offset,
        limit=CARDS_PER_PAGE,
        rarity_filter=rarity_filter
    )

    if not cards:
        text = f"🎴 *{user_name}'s Collection*\n\nNo cards on this page."
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text=text,
                parse_mode=ParseMode.MARKDOWN
            )
        return

    # Build card list
    card_list = []
    for idx, card in enumerate(cards, start=offset + 1):
        character = card.get("character_name", "Unknown")
        anime = card.get("anime", "Unknown")
        rarity = card.get("rarity", 1)
        quantity = card.get("quantity", 1)
        card_id = card.get("card_id", 0)

        rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity)

        qty_text = f" (x{quantity})" if quantity > 1 else ""
        fav_marker = "⭐" if card.get("is_favorite") else ""

        card_list.append(
            f"{idx}. {rarity_emoji} *{character}*{qty_text} {fav_marker}\n"
            f"   🎬 _{anime}_ • ID: `#{card_id}`"
        )

    cards_text = "\n\n".join(card_list)

    # Build message
    filter_text = f" (Rarity: {rarity_to_text(rarity_filter)[2]})" if rarity_filter else ""

    text = (
        f"🎴 *{user_name}'s Collection{filter_text}*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{cards_text}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📄 Page {page}/{total_pages} • Total: {total_count} cards"
    )

    # Build pagination keyboard
    keyboard = build_collection_keyboard(user_id, page, total_pages, rarity_filter)

    # Send or edit message
    if update.callback_query:
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


def build_collection_keyboard(
    user_id: int,
    page: int,
    total_pages: int,
    rarity_filter: Optional[int] = None
) -> InlineKeyboardMarkup:
    """
    Build pagination keyboard for collection view.
    
    Args:
        user_id: User ID
        page: Current page
        total_pages: Total pages
        rarity_filter: Optional rarity filter
        
    Returns:
        InlineKeyboardMarkup with navigation buttons
    """
    buttons = []

    # Navigation row
    nav_buttons = []

    if page > 1:
        nav_buttons.append(
            InlineKeyboardButton("⬅️ Prev", callback_data=f"col:{user_id}:{page-1}:{rarity_filter or 0}")
        )

    nav_buttons.append(
        InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop")
    )

    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton("Next ➡️", callback_data=f"col:{user_id}:{page+1}:{rarity_filter or 0}")
        )

    buttons.append(nav_buttons)

    # Filter buttons (optional - can be expanded)
    # buttons.append([
    #     InlineKeyboardButton("🔍 Filter", callback_data=f"col_filter:{user_id}"),
    # ])

    return InlineKeyboardMarkup(buttons)


# ============================================================
# 🔘 Collection Navigation Callback Handler
# ============================================================

async def collection_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle collection pagination callbacks.
    
    Pattern: col:{user_id}:{page}:{rarity_filter}
    """
    query = update.callback_query

    if not query or not query.data:
        return

    await query.answer()

    # Ignore noop
    if query.data == "noop":
        return

    # Parse callback data
    try:
        parts = query.data.split(":")
        if parts[0] != "col":
            return

        user_id = int(parts[1])
        page = int(parts[2])
        rarity_filter = int(parts[3]) if len(parts) > 3 and parts[3] != "0" else None

    except (ValueError, IndexError):
        await query.answer("Invalid data", show_alert=True)
        return

    # Show the requested page
    await show_collection_page(update, context, user_id, page, rarity_filter)


# ============================================================
# 📦 Handler Registration
# ============================================================

def register_collection_handlers(application: Application) -> None:
    """
    Register collection-related handlers.
    
    Args:
        application: Telegram bot application
    """
    # Command handler
    application.add_handler(CommandHandler("collection", collection_command))

    # Callback query handler for pagination
    application.add_handler(
        CallbackQueryHandler(collection_callback_handler, pattern=r"^col:")
    )

    app_logger.info("✅ Collection handlers registered")