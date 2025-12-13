# ============================================================
# 📁 File: commands/harem.py
# 📍 Location: telegram_card_bot/commands/harem.py
# 📝 Description: Clean, minimal harem viewer with pagination
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
    get_user_collection_stats,
    get_card_with_details,
    get_card_owners,
    get_user_card_quantity,
    toggle_favorite,
)
from utils.logger import app_logger, error_logger, log_command
from utils.rarity import rarity_to_text, RARITY_TABLE


# ============================================================
# ⚙️ Configuration
# ============================================================

CARDS_PER_PAGE = 5


# ============================================================
# 🎨 Simple Rarity Emoji
# ============================================================

# ============================================================
# 🎨 Updated Rarity Emoji
# ============================================================

def get_rarity_emoji(rarity: int) -> str:
    """Get emoji for rarity level."""
    emojis = {
        1: "☘️",   # Normal
        2: "⚡",   # Common
        3: "⭐",   # Uncommon
        4: "💠",   # Rare
        5: "🔮",   # Epic
        6: "🧿",   # Limited Epic
        7: "🪩",   # Platinum
        8: "🎐",   # Emerald
        9: "❄️",   # Crystal
        10: "🏵️",  # Mythical
        11: "🌸",  # Legendary
    }
    return emojis.get(rarity, "☘️")


# ============================================================
# 🎴 Main Harem Command
# ============================================================

async def harem_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /harem command."""
    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    chat = update.effective_chat
    
    log_command(user.id, "harem", chat.id if chat else 0)

    await ensure_user(
        pool=None,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

    if not db.is_connected:
        await update.message.reply_text("⚠️ Database offline. Try again later.")
        return

    target_user_id = user.id
    target_user_name = user.first_name

    await display_harem_page(
        update=update,
        context=context,
        user_id=target_user_id,
        user_name=target_user_name,
        page=1,
        is_own_harem=True
    )


# ============================================================
# 📄 Display Harem Page - CLEAN DESIGN
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
    """Display a clean, minimal harem page."""
    
    # Get stats
    stats = await get_user_collection_stats(None, user_id)
    total_unique = stats.get("total_unique", 0)
    total_cards = stats.get("total_cards", 0)

    # Empty collection
    if total_unique == 0:
        text = (
            f"🎴 *{user_name}'s Harem*\n\n"
            f"No cards yet!\n"
            f"Use /catch to collect cards."
        )
        
        if edit_message and update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        return

    # Get count with filter
    filtered_count = await get_collection_count(None, user_id, rarity_filter)
    
    if filtered_count == 0 and rarity_filter:
        text = f"🎴 *{user_name}'s Harem*\n\nNo cards with this filter."
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Clear Filter", callback_data=f"h:{user_id}:1:0")
        ]])
        if edit_message and update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        return

    # Pagination
    total_pages = max(1, (filtered_count + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * CARDS_PER_PAGE

    # Fetch cards
    cards = await get_collection_cards(
        pool=None,
        user_id=user_id,
        offset=offset,
        limit=CARDS_PER_PAGE,
        rarity_filter=rarity_filter
    )

    if not cards:
        page = 1
        offset = 0
        cards = await get_collection_cards(None, user_id, offset, CARDS_PER_PAGE)

    # Build simple card list
    card_lines = []
    for idx, card in enumerate(cards):
        num = offset + idx + 1
        name = card.get("character_name", "Unknown")
        rarity = card.get("rarity", 1)
        qty = card.get("quantity", 1)
        
        emoji = get_rarity_emoji(rarity)
        qty_text = f" ×{qty}" if qty > 1 else ""
        
        card_lines.append(f"{num}. {emoji} {name}{qty_text}")

    cards_text = "\n".join(card_lines)

    # Build clean message
    text = (
        f"🎴 *{user_name}'s Harem*\n\n"
        f"{cards_text}\n\n"
        f"_{total_unique} unique • {total_cards} total_\n"
        f"Page {page}/{total_pages}"
    )

    # Build keyboard
    keyboard = build_harem_keyboard(user_id, page, total_pages, cards, offset, rarity_filter)

    # Send or edit
    if edit_message and update.callback_query:
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
# ⌨️ Keyboard Builder - CLEAN BUTTONS
# ============================================================

def build_harem_keyboard(
    user_id: int,
    page: int,
    total_pages: int,
    cards: List[dict],
    offset: int,
    rarity_filter: Optional[int] = None
) -> InlineKeyboardMarkup:
    """Build clean navigation keyboard."""
    
    buttons = []
    
    # Row 1: Quick view buttons (card numbers)
    if cards:
        quick_btns = []
        for idx, card in enumerate(cards):
            card_id = card.get("card_id", 0)
            quick_btns.append(
                InlineKeyboardButton(
                    str(offset + idx + 1),
                    callback_data=f"hv:{user_id}:{card_id}:{page}:{rarity_filter or 0}"
                )
            )
        buttons.append(quick_btns)

    # Row 2: Navigation
    nav_row = []
    
    # Back
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀", callback_data=f"h:{user_id}:{page-1}:{rarity_filter or 0}"))
    else:
        nav_row.append(InlineKeyboardButton(" ", callback_data="noop"))
    
    # Page indicator
    nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    
    # Next
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("▶", callback_data=f"h:{user_id}:{page+1}:{rarity_filter or 0}"))
    else:
        nav_row.append(InlineKeyboardButton(" ", callback_data="noop"))
    
    buttons.append(nav_row)

    # Row 3: Filter & Close
    buttons.append([
        InlineKeyboardButton("Filter", callback_data=f"hf:{user_id}:{page}"),
        InlineKeyboardButton("Close", callback_data="hclose")
    ])

    return InlineKeyboardMarkup(buttons)


# ============================================================
# 🔍 Card Detail View - CLEAN
# ============================================================

async def display_card_detail(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    card_id: int,
    return_page: int = 1,
    rarity_filter: int = 0
) -> None:
    """Display clean card details."""
    
    query = update.callback_query
    
    card = await get_card_with_details(None, card_id)
    
    if not card:
        await query.answer("Card not found!", show_alert=True)
        return

    name = card.get("character_name", "Unknown")
    anime = card.get("anime", "Unknown")
    rarity = card.get("rarity", 1)
    photo = card.get("photo_file_id")
    
    rarity_name, prob, emoji = rarity_to_text(rarity)
    user_qty = await get_user_card_quantity(None, user_id, card_id)

    caption = (
        f"{emoji} *{name}*\n\n"
        f"Anime: {anime}\n"
        f"Rarity: {rarity_name}\n"
        f"ID: `#{card_id}`\n"
        f"You own: ×{user_qty}"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("◀ Back", callback_data=f"h:{user_id}:{return_page}:{rarity_filter}")]
    ])

    if photo:
        try:
            await query.message.delete()
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=photo,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
        except Exception:
            await query.edit_message_text(caption, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    else:
        await query.edit_message_text(caption, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    
    await query.answer()


# ============================================================
# 🔍 Filter Menu - SIMPLE
# ============================================================

async def display_filter_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    current_page: int
) -> None:
    """Display simple filter menu."""
    
    query = update.callback_query
    
    text = "Select rarity filter:"
    
    buttons = []
    row = []
    
    for rid in sorted(RARITY_TABLE.keys()):
        r = RARITY_TABLE[rid]
        btn = InlineKeyboardButton(
            f"{r.emoji}",
            callback_data=f"h:{user_id}:1:{rid}"
        )
        row.append(btn)
        if len(row) == 4:
            buttons.append(row)
            row = []
    
    if row:
        buttons.append(row)
    
    buttons.append([
        InlineKeyboardButton("Clear", callback_data=f"h:{user_id}:1:0"),
        InlineKeyboardButton("Cancel", callback_data=f"h:{user_id}:{current_page}:0")
    ])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    await query.answer()


# ============================================================
# 🔘 Callback Handlers
# ============================================================

async def harem_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle harem navigation callbacks."""
    
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    
    # Noop
    if data == "noop":
        await query.answer()
        return
    
    # Close
    if data == "hclose":
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.answer()
        return

    # Parse: h:{user_id}:{page}:{filter}
    if data.startswith("h:"):
        try:
            parts = data.split(":")
            user_id = int(parts[1])
            page = int(parts[2])
            rarity_filter = int(parts[3]) if len(parts) > 3 and parts[3] != "0" else None
        except (ValueError, IndexError):
            await query.answer("Error", show_alert=True)
            return

        user_info = await get_user_by_id(None, user_id)
        user_name = user_info.get("first_name", "User") if user_info else "User"

        await display_harem_page(
            update=update,
            context=context,
            user_id=user_id,
            user_name=user_name,
            page=page,
            rarity_filter=rarity_filter,
            is_own_harem=(query.from_user.id == user_id),
            edit_message=True
        )
        return

    # Filter menu: hf:{user_id}:{page}
    if data.startswith("hf:"):
        try:
            parts = data.split(":")
            user_id = int(parts[1])
            page = int(parts[2])
        except (ValueError, IndexError):
            await query.answer("Error", show_alert=True)
            return
        
        await display_filter_menu(update, context, user_id, page)
        return


async def harem_view_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle card view callbacks."""
    
    query = update.callback_query
    if not query or not query.data:
        return

    # hv:{user_id}:{card_id}:{page}:{filter}
    try:
        parts = query.data.split(":")
        user_id = int(parts[1])
        card_id = int(parts[2])
        return_page = int(parts[3]) if len(parts) > 3 else 1
        rarity_filter = int(parts[4]) if len(parts) > 4 else 0
    except (ValueError, IndexError):
        await query.answer("Error", show_alert=True)
        return

    await display_card_detail(update, context, user_id, card_id, return_page, rarity_filter)


# ============================================================
# 📦 Handler Registration
# ============================================================

def register_harem_handlers(application: Application) -> None:
    """Register harem handlers."""
    
    # Commands
    application.add_handler(CommandHandler("harem", harem_command))
    application.add_handler(CommandHandler("collection", harem_command))

    # Callbacks
    application.add_handler(CallbackQueryHandler(harem_callback_handler, pattern=r"^h:"))
    application.add_handler(CallbackQueryHandler(harem_callback_handler, pattern=r"^hf:"))
    application.add_handler(CallbackQueryHandler(harem_callback_handler, pattern=r"^hclose$"))
    application.add_handler(CallbackQueryHandler(harem_callback_handler, pattern=r"^noop$"))
    application.add_handler(CallbackQueryHandler(harem_view_callback_handler, pattern=r"^hv:"))

    app_logger.info("✅ Harem handlers registered")


# Backward compatibility
register_collection_handlers = register_harem_handlers