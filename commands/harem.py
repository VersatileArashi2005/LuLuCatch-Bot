# ============================================================
# 📁 File: commands/harem.py
# 📍 Location: telegram_card_bot/commands/harem.py
# 📝 Description: Premium harem viewer with clean pagination & card details
# ============================================================

from typing import Optional, List, Tuple
from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
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
    get_user_collection_stats,
    get_card_with_details,
    get_card_owners,
    check_user_owns_card,
    get_user_card_quantity,
)
from utils.logger import app_logger, error_logger, log_command
from utils.rarity import rarity_to_text, get_rarity_emoji, RARITY_TABLE


# ============================================================
# ⚙️ Configuration
# ============================================================

CARDS_PER_PAGE = 5  # Cards per page (optimized for mobile)
MAX_QUICK_BUTTONS = 5  # Quick view buttons per row


# ============================================================
# 🎨 Display Helpers
# ============================================================

def get_rarity_stars(rarity: int) -> str:
    """Convert rarity to visual star representation."""
    if rarity >= 11:
        return "⚡"  # Legendary
    elif rarity >= 10:
        return "🧿"  # Mythical
    elif rarity >= 9:
        return "🌸"  # Crystal
    elif rarity >= 8:
        return "💎"  # Emerald
    elif rarity >= 7:
        return "❄️"  # Platinum
    elif rarity >= 6:
        return "🎐"  # Limited
    elif rarity >= 5:
        return "🫧"  # Epic
    elif rarity >= 4:
        return "☘️"  # Rare
    elif rarity >= 3:
        return "🥏"  # Uncommon
    elif rarity >= 2:
        return "🌀"  # Common
    else:
        return "🛞"  # Normal


def format_card_line(
    index: int,
    card: dict,
    show_quantity: bool = True
) -> str:
    """
    Format a single card line for the harem list.
    Clean, minimal design.
    """
    character = card.get("character_name", "Unknown")
    rarity = card.get("rarity", 1)
    quantity = card.get("quantity", 1)
    card_id = card.get("card_id", 0)
    is_favorite = card.get("is_favorite", False)
    
    # Rarity emoji
    rarity_icon = get_rarity_stars(rarity)
    
    # Favorite marker
    fav = " ♥" if is_favorite else ""
    
    # Quantity badge
    qty = f" ×{quantity}" if quantity > 1 and show_quantity else ""
    
    # Format: "1. 💎 Character Name ×2 ♥"
    return f"`{index}.` {rarity_icon} **{character}**{qty}{fav}"


def build_stats_header(
    user_name: str,
    total_cards: int,
    total_unique: int,
    page: int,
    total_pages: int
) -> str:
    """Build the header with user stats."""
    return (
        f"🎴 **{user_name}'s Harem**\n"
        f"╭──────────────────╮\n"
        f"│  📦 {total_unique} unique  •  🃏 {total_cards} total\n"
        f"╰──────────────────╯"
    )


# ============================================================
# 🎴 Main Harem Command
# ============================================================

async def harem_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /harem command.
    Shows user's collection with premium pagination.
    
    Usage:
        /harem - View your own harem
        /harem @username - View another user's harem (if public)
    """
    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    chat = update.effective_chat
    
    log_command(user.id, "harem", chat.id if chat else 0)

    # Ensure user exists in database
    await ensure_user(
        pool=None,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

    # Check database connection
    if not db.is_connected:
        await update.message.reply_text(
            "⚠️ Database is currently offline. Please try again later."
        )
        return

    # Determine target user (self or mentioned)
    target_user_id = user.id
    target_user_name = user.first_name
    
    # Check if viewing another user's harem
    if context.args:
        # Try to parse as user ID or username
        arg = context.args[0]
        if arg.startswith("@"):
            # Username lookup would require additional DB function
            # For now, only support own harem
            pass
        elif arg.isdigit():
            target_user_id = int(arg)
            target_info = await get_user_by_id(None, target_user_id)
            if target_info:
                target_user_name = target_info.get("first_name", "User")
            else:
                await update.message.reply_text("❌ User not found.")
                return

    # Display first page
    await display_harem_page(
        update=update,
        context=context,
        user_id=target_user_id,
        user_name=target_user_name,
        page=1,
        is_own_harem=(target_user_id == user.id)
    )


# ============================================================
# 📄 Page Display Function
# ============================================================

async def display_harem_page(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    user_name: str,
    page: int = 1,
    rarity_filter: Optional[int] = None,
    is_own_harem: bool = True,
    edit_message: bool = False
) -> None:
    """
    Display a paginated harem page.
    
    Args:
        update: Telegram update object
        context: Bot context
        user_id: Target user's ID
        user_name: Target user's display name
        page: Page number (1-indexed)
        rarity_filter: Optional rarity filter (1-11)
        is_own_harem: Whether viewing own collection
        edit_message: Whether to edit existing message
    """
    # Get collection stats
    stats = await get_user_collection_stats(None, user_id)
    total_unique = stats.get("total_unique", 0)
    total_cards = stats.get("total_cards", 0)

    # Handle empty collection
    if total_unique == 0:
        text = (
            f"🎴 **{user_name}'s Harem**\n\n"
            f"╭───────────────────────╮\n"
            f"│     📦 Empty Harem      │\n"
            f"╰───────────────────────╯\n\n"
            f"No cards collected yet!\n"
            f"Use `/catch` in groups to start collecting."
        )
        
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔍 How to Catch", callback_data="harem:help")
        ]])

        if edit_message and update.callback_query:
            await update.callback_query.edit_message_text(
                text=text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
        else:
            await update.message.reply_text(
                text=text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
        return

    # Get filtered count for pagination
    filtered_count = await get_collection_count(None, user_id, rarity_filter)
    
    if filtered_count == 0 and rarity_filter:
        # No cards with this rarity filter
        text = (
            f"🎴 **{user_name}'s Harem**\n\n"
            f"No cards found with this rarity filter.\n"
            f"Try removing the filter."
        )
        
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Clear Filter", callback_data=f"harem:{user_id}:1:0")
        ]])

        if edit_message and update.callback_query:
            await update.callback_query.edit_message_text(
                text=text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
        return

    # Calculate pagination
    total_pages = max(1, (filtered_count + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * CARDS_PER_PAGE

    # Fetch cards for current page
    cards = await get_collection_cards(
        pool=None,
        user_id=user_id,
        offset=offset,
        limit=CARDS_PER_PAGE,
        rarity_filter=rarity_filter
    )

    if not cards:
        # Fallback for edge case
        page = 1
        offset = 0
        cards = await get_collection_cards(
            pool=None,
            user_id=user_id,
            offset=offset,
            limit=CARDS_PER_PAGE
        )

    # Build card list
    card_lines = []
    for idx, card in enumerate(cards):
        display_idx = offset + idx + 1
        line = format_card_line(display_idx, card)
        card_lines.append(line)

    cards_text = "\n".join(card_lines)

    # Build filter indicator
    filter_text = ""
    if rarity_filter:
        rarity_name, _, rarity_emoji = rarity_to_text(rarity_filter)
        filter_text = f"\n🔍 Filter: {rarity_emoji} {rarity_name}"

    # Build message
    text = (
        f"🎴 **{user_name}'s Harem**\n"
        f"╭───────────────────────╮\n"
        f"│  📦 `{total_unique}` unique  •  🃏 `{total_cards}` total\n"
        f"╰───────────────────────╯\n"
        f"{filter_text}\n\n"
        f"{cards_text}\n\n"
        f"📄 Page **{page}**/{total_pages}"
    )

    # Build keyboard
    keyboard = build_harem_keyboard(
        user_id=user_id,
        page=page,
        total_pages=total_pages,
        cards=cards,
        offset=offset,
        rarity_filter=rarity_filter,
        is_own_harem=is_own_harem
    )

    # Send or edit message
    if edit_message and update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text=text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
        except Exception as e:
            # Message content unchanged, just answer
            app_logger.debug(f"Edit message unchanged: {e}")
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

def build_harem_keyboard(
    user_id: int,
    page: int,
    total_pages: int,
    cards: List[dict],
    offset: int,
    rarity_filter: Optional[int] = None,
    is_own_harem: bool = True
) -> InlineKeyboardMarkup:
    """
    Build the harem navigation keyboard.
    
    Layout:
    Row 1: [1️⃣] [2️⃣] [3️⃣] [4️⃣] [5️⃣]  <- Quick view buttons
    Row 2: [◀️] [📊 Page X/Y] [▶️]      <- Navigation
    Row 3: [🔍 Filter] [❌ Close]        <- Actions
    """
    buttons = []
    
    # Row 1: Quick view buttons for each card
    if cards:
        quick_buttons = []
        for idx, card in enumerate(cards):
            card_id = card.get("card_id", 0)
            collection_id = card.get("collection_id", card_id)
            
            # Use number emojis for cleaner look
            num_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
            btn_label = num_emojis[idx] if idx < len(num_emojis) else str(idx + 1)
            
            quick_buttons.append(
                InlineKeyboardButton(
                    btn_label,
                    callback_data=f"hview:{user_id}:{card_id}:{page}:{rarity_filter or 0}"
                )
            )
        
        buttons.append(quick_buttons)

    # Row 2: Navigation
    nav_row = []
    
    # Back button
    if page > 1:
        nav_row.append(
            InlineKeyboardButton(
                "◀️",
                callback_data=f"harem:{user_id}:{page - 1}:{rarity_filter or 0}"
            )
        )
    else:
        nav_row.append(
            InlineKeyboardButton("◀️", callback_data="harem:noop")
        )
    
    # Page indicator (tappable to jump)
    nav_row.append(
        InlineKeyboardButton(
            f"📄 {page}/{total_pages}",
            callback_data=f"harem:jump:{user_id}:{total_pages}:{rarity_filter or 0}"
        )
    )
    
    # Next button
    if page < total_pages:
        nav_row.append(
            InlineKeyboardButton(
                "▶️",
                callback_data=f"harem:{user_id}:{page + 1}:{rarity_filter or 0}"
            )
        )
    else:
        nav_row.append(
            InlineKeyboardButton("▶️", callback_data="harem:noop")
        )
    
    buttons.append(nav_row)

    # Row 3: Actions
    action_row = []
    
    # Filter button
    action_row.append(
        InlineKeyboardButton(
            "🔍 Filter",
            callback_data=f"harem:filter:{user_id}:{page}"
        )
    )
    
    # Sort button (optional)
    # action_row.append(
    #     InlineKeyboardButton(
    #         "📊 Sort",
    #         callback_data=f"harem:sort:{user_id}:{page}"
    #     )
    # )
    
    # Close button
    action_row.append(
        InlineKeyboardButton(
            "❌ Close",
            callback_data="harem:close"
        )
    )
    
    buttons.append(action_row)

    return InlineKeyboardMarkup(buttons)


# ============================================================
# 🔍 Card Detail View
# ============================================================

async def display_card_detail(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    card_id: int,
    return_page: int = 1,
    rarity_filter: int = 0
) -> None:
    """
    Display detailed view of a single card from the harem.
    
    Args:
        update: Telegram update
        context: Bot context
        user_id: Owner's user ID
        card_id: Card to display
        return_page: Page to return to
        rarity_filter: Active rarity filter
    """
    query = update.callback_query
    viewer_id = query.from_user.id
    
    # Fetch card details
    card = await get_card_with_details(None, card_id)
    
    if not card:
        await query.answer("❌ Card not found!", show_alert=True)
        return

    # Extract card info
    character = card.get("character_name", "Unknown")
    anime = card.get("anime", "Unknown")
    rarity = card.get("rarity", 1)
    photo_file_id = card.get("photo_file_id")
    total_caught = card.get("total_caught", 0)
    unique_owners = card.get("unique_owners", 0)
    total_circulation = card.get("total_in_circulation", 0)
    
    # Get rarity info
    rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity)
    
    # Get user's quantity of this card
    user_quantity = await get_user_card_quantity(None, user_id, card_id)
    
    # Get top owners
    owners = await get_card_owners(None, card_id, limit=3)
    
    # Build owners text
    owners_text = ""
    if owners:
        owner_lines = []
        for i, owner in enumerate(owners, 1):
            name = owner.get("first_name", "Unknown")
            qty = owner.get("quantity", 1)
            medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
            owner_lines.append(f"{medal} {name} (×{qty})")
        owners_text = "\n".join(owner_lines)

    # Build caption
    caption = (
        f"{rarity_emoji} **{character}**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🎬 {anime}\n"
        f"🆔 `#{card_id}`\n"
        f"✨ {rarity_name} ({rarity_prob}%)\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"📊 **Stats**\n"
        f"• Total caught: `{total_caught:,}`\n"
        f"• Unique owners: `{unique_owners:,}`\n"
        f"• In circulation: `{total_circulation:,}`\n"
        f"• You own: `×{user_quantity}`\n"
    )
    
    if owners_text:
        caption += f"\n👑 **Top Owners**\n{owners_text}"

    # Build keyboard
    keyboard = build_card_detail_keyboard(
        user_id=user_id,
        card_id=card_id,
        return_page=return_page,
        rarity_filter=rarity_filter,
        viewer_id=viewer_id,
        is_owner=(user_id == viewer_id)
    )

    # Send photo with caption
    if photo_file_id:
        try:
            # Try to edit with media
            await query.message.delete()
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=photo_file_id,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
        except Exception as e:
            error_logger.error(f"Error sending card photo: {e}")
            # Fallback to text
            await query.edit_message_text(
                text=caption,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
    else:
        await query.edit_message_text(
            text=caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
    
    await query.answer()


def build_card_detail_keyboard(
    user_id: int,
    card_id: int,
    return_page: int,
    rarity_filter: int,
    viewer_id: int,
    is_owner: bool = True
) -> InlineKeyboardMarkup:
    """Build keyboard for card detail view."""
    buttons = []
    
    # Row 1: Actions
    action_row = []
    
    if is_owner:
        # Favorite toggle
        action_row.append(
            InlineKeyboardButton(
                "⭐ Favorite",
                callback_data=f"hfav:{user_id}:{card_id}:{return_page}:{rarity_filter}"
            )
        )
        
        # Trade offer
        action_row.append(
            InlineKeyboardButton(
                "🔁 Trade",
                callback_data=f"htrade:{card_id}"
            )
        )
    else:
        # Request trade
        action_row.append(
            InlineKeyboardButton(
                "📩 Request Trade",
                callback_data=f"htrade_req:{user_id}:{card_id}"
            )
        )
    
    if action_row:
        buttons.append(action_row)

    # Row 2: Back button
    buttons.append([
        InlineKeyboardButton(
            "◀️ Back to Harem",
            callback_data=f"harem:{user_id}:{return_page}:{rarity_filter}"
        )
    ])

    return InlineKeyboardMarkup(buttons)


# ============================================================
# 🔍 Filter Menu
# ============================================================

async def display_filter_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    current_page: int
) -> None:
    """Display rarity filter selection menu."""
    query = update.callback_query
    
    text = (
        "🔍 **Filter by Rarity**\n\n"
        "Select a rarity to filter your harem:"
    )
    
    # Build rarity buttons (2 per row)
    buttons = []
    row = []
    
    for rarity_id in sorted(RARITY_TABLE.keys()):
        rarity = RARITY_TABLE[rarity_id]
        btn = InlineKeyboardButton(
            f"{rarity.emoji} {rarity.name}",
            callback_data=f"harem:{user_id}:1:{rarity_id}"
        )
        row.append(btn)
        
        if len(row) == 2:
            buttons.append(row)
            row = []
    
    if row:
        buttons.append(row)
    
    # Clear filter button
    buttons.append([
        InlineKeyboardButton(
            "🔄 Clear Filter",
            callback_data=f"harem:{user_id}:1:0"
        )
    ])
    
    # Cancel button
    buttons.append([
        InlineKeyboardButton(
            "❌ Cancel",
            callback_data=f"harem:{user_id}:{current_page}:0"
        )
    ])
    
    keyboard = InlineKeyboardMarkup(buttons)
    
    await query.edit_message_text(
        text=text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )
    await query.answer()


# ============================================================
# 🔘 Callback Handlers
# ============================================================

async def harem_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle all harem-related callbacks.
    
    Patterns:
    - harem:{user_id}:{page}:{rarity_filter} - Navigate to page
    - harem:noop - Do nothing (disabled button)
    - harem:close - Close/delete message
    - harem:filter:{user_id}:{page} - Show filter menu
    - harem:jump:{user_id}:{total}:{filter} - Page jump (future)
    - harem:help - Show help
    """
    query = update.callback_query
    
    if not query or not query.data:
        return

    data = query.data
    
    # Handle noop (disabled buttons)
    if data == "harem:noop":
        await query.answer("You're at the edge!", show_alert=False)
        return
    
    # Handle close
    if data == "harem:close":
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.answer("Closed!")
        return
    
    # Handle help
    if data == "harem:help":
        await query.answer(
            "💡 Use /catch in groups when cards spawn!\n"
            "Win the battle to add cards to your harem.",
            show_alert=True
        )
        return

    # Parse callback data
    parts = data.split(":")
    
    if len(parts) < 2:
        await query.answer("Invalid action", show_alert=True)
        return

    action = parts[1] if len(parts) > 1 else None
    
    # Handle filter menu
    if action == "filter" and len(parts) >= 4:
        user_id = int(parts[2])
        current_page = int(parts[3])
        await display_filter_menu(update, context, user_id, current_page)
        return
    
    # Handle page jump (future feature)
    if action == "jump":
        await query.answer("Tap ◀️ or ▶️ to navigate", show_alert=False)
        return

    # Handle page navigation: harem:{user_id}:{page}:{rarity_filter}
    try:
        user_id = int(parts[1])
        page = int(parts[2]) if len(parts) > 2 else 1
        rarity_filter = int(parts[3]) if len(parts) > 3 and parts[3] != "0" else None
    except (ValueError, IndexError):
        await query.answer("Invalid data", show_alert=True)
        return

    # Get user info
    user_info = await get_user_by_id(None, user_id)
    user_name = user_info.get("first_name", "User") if user_info else "User"
    
    # Check if viewing own harem
    is_own = (query.from_user.id == user_id)

    # Display the page
    await display_harem_page(
        update=update,
        context=context,
        user_id=user_id,
        user_name=user_name,
        page=page,
        rarity_filter=rarity_filter,
        is_own_harem=is_own,
        edit_message=True
    )


async def harem_view_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle card view callbacks from harem.
    
    Pattern: hview:{user_id}:{card_id}:{return_page}:{rarity_filter}
    """
    query = update.callback_query
    
    if not query or not query.data:
        return

    try:
        parts = query.data.split(":")
        user_id = int(parts[1])
        card_id = int(parts[2])
        return_page = int(parts[3]) if len(parts) > 3 else 1
        rarity_filter = int(parts[4]) if len(parts) > 4 else 0
    except (ValueError, IndexError):
        await query.answer("Invalid card data", show_alert=True)
        return

    await display_card_detail(
        update=update,
        context=context,
        user_id=user_id,
        card_id=card_id,
        return_page=return_page,
        rarity_filter=rarity_filter
    )


async def harem_favorite_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle favorite toggle from card detail view.
    
    Pattern: hfav:{user_id}:{card_id}:{return_page}:{rarity_filter}
    """
    query = update.callback_query
    
    if not query or not query.data:
        return

    viewer_id = query.from_user.id
    
    try:
        parts = query.data.split(":")
        user_id = int(parts[1])
        card_id = int(parts[2])
        return_page = int(parts[3]) if len(parts) > 3 else 1
        rarity_filter = int(parts[4]) if len(parts) > 4 else 0
    except (ValueError, IndexError):
        await query.answer("Invalid data", show_alert=True)
        return

    # Only owner can toggle favorite
    if viewer_id != user_id:
        await query.answer("You can only favorite your own cards!", show_alert=True)
        return

    # Toggle favorite in database
    from db import toggle_favorite
    new_status = await toggle_favorite(None, user_id, card_id)
    
    if new_status is not None:
        status_text = "⭐ Added to favorites!" if new_status else "Removed from favorites"
        await query.answer(status_text, show_alert=False)
        
        # Refresh card detail view
        await display_card_detail(
            update=update,
            context=context,
            user_id=user_id,
            card_id=card_id,
            return_page=return_page,
            rarity_filter=rarity_filter
        )
    else:
        await query.answer("❌ Failed to update favorite", show_alert=True)


async def harem_trade_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle trade initiation from card detail view.
    
    Patterns:
    - htrade:{card_id} - Offer own card for trade
    - htrade_req:{owner_id}:{card_id} - Request someone else's card
    """
    query = update.callback_query
    
    if not query or not query.data:
        return

    await query.answer(
        "💡 Use /offertrade command to initiate trades!\n"
        "Example: /offertrade @user",
        show_alert=True
    )


# ============================================================
# 📦 Handler Registration
# ============================================================

def register_harem_handlers(application: Application) -> None:
    """
    Register all harem-related handlers.
    
    Args:
        application: Telegram bot application
    """
    # Command handlers
    application.add_handler(CommandHandler("harem", harem_command))
    
    # Keep /collection as alias for compatibility
    application.add_handler(CommandHandler("collection", harem_command))

    # Callback handlers
    application.add_handler(
        CallbackQueryHandler(harem_callback_handler, pattern=r"^harem:")
    )
    
    application.add_handler(
        CallbackQueryHandler(harem_view_callback_handler, pattern=r"^hview:")
    )
    
    application.add_handler(
        CallbackQueryHandler(harem_favorite_callback_handler, pattern=r"^hfav:")
    )
    
    application.add_handler(
        CallbackQueryHandler(harem_trade_callback_handler, pattern=r"^htrade")
    )

    app_logger.info("✅ Harem handlers registered")


# ============================================================
# 🔄 Backward Compatibility Alias
# ============================================================

# For imports that still use old function name
register_collection_handlers = register_harem_handlers
