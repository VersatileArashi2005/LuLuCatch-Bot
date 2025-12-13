# ============================================================
# 📁 File: commands/harem.py
# 📍 Location: telegram_card_bot/commands/harem.py
# 📝 Description: Modern harem viewer with inline collection support
# ============================================================

from typing import Optional, List
from uuid import uuid4

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultCachedPhoto,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    InlineQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode

from config import Config
from db import (
    db,
    ensure_user,
    get_collection_cards,
    get_collection_count,
    get_user_by_id,
    get_user_collection_stats,
    get_card_with_details,
    get_user_card_quantity,
    toggle_favorite,
)
from utils.logger import app_logger, error_logger, log_command
from utils.constants import (
    RARITY_EMOJIS,
    RARITY_NAMES,
    Pagination,
    CallbackPrefixes,
    ButtonLabels,
)
from utils.rarity import rarity_to_text, RARITY_TABLE, get_rarity
from utils.ui import (
    format_card_caption,
    send_catch_reaction,
)


# ============================================================
# 📊 Configuration
# ============================================================

CARDS_PER_PAGE = Pagination.HAREM_PER_PAGE
INLINE_RESULTS_LIMIT = 50


# ============================================================
# 🎴 Main Harem Command
# ============================================================

async def harem_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /harem command - shows collection with inline view option."""
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

    # Check for arguments (view other user's harem)
    target_user_id = user.id
    target_user_name = user.first_name

    if context.args:
        try:
            target_user_id = int(context.args[0])
            target_user = await get_user_by_id(None, target_user_id)
            if target_user:
                target_user_name = target_user.get("first_name", "User")
            else:
                await update.message.reply_text("❌ User not found.")
                return
        except ValueError:
            pass

    await display_harem_page(
        update=update,
        context=context,
        user_id=target_user_id,
        user_name=target_user_name,
        page=1,
        is_own_harem=(target_user_id == user.id)
    )


# ============================================================
# 📄 Display Harem Page - Modern Design
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
    """Display modern, clean harem page with inline view option."""
    
    # Get stats
    stats = await get_user_collection_stats(None, user_id)
    total_unique = stats.get("total_unique", 0)
    total_cards = stats.get("total_cards", 0)

    bot_username = context.bot.username or Config.BOT_USERNAME

    # Empty collection
    if total_unique == 0:
        text = (
            f"🎴 *{user_name}'s Harem*\n\n"
            f"No cards yet!\n"
            f"Use /catch in groups to collect cards."
        )
        
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🔍 Browse All Cards",
                switch_inline_query_current_chat=""
            )
        ]])
        
        if edit_message and update.callback_query:
            await update.callback_query.edit_message_text(
                text, 
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
        else:
            await update.message.reply_text(
                text, 
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
        return

    # Get filtered count
    filtered_count = await get_collection_count(None, user_id, rarity_filter)
    
    if filtered_count == 0 and rarity_filter:
        rarity_name = RARITY_NAMES.get(rarity_filter, "Unknown")
        text = (
            f"🎴 *{user_name}'s Harem*\n\n"
            f"No {rarity_name} cards found."
        )
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("📋 Show All", callback_data=f"h:{user_id}:1:0")
        ]])
        if edit_message and update.callback_query:
            await update.callback_query.edit_message_text(
                text, 
                parse_mode=ParseMode.MARKDOWN, 
                reply_markup=keyboard
            )
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

    # Build card list
    card_lines = []
    for card in cards:
        emoji = RARITY_EMOJIS.get(card.get("rarity", 1), "☘️")
        name = card.get("character_name", "Unknown")
        qty = card.get("quantity", 1)
        fav = " ❤️" if card.get("is_favorite") else ""
        
        qty_text = f" ×{qty}" if qty > 1 else ""
        card_lines.append(f"{emoji} *{name}*{qty_text}{fav}")

    cards_text = "\n".join(card_lines)

    # Filter indicator
    filter_text = ""
    if rarity_filter:
        filter_emoji = RARITY_EMOJIS.get(rarity_filter, "")
        filter_name = RARITY_NAMES.get(rarity_filter, "")
        filter_text = f"\n🔍 Filter: {filter_emoji} {filter_name}"

    # Build message
    text = (
        f"🎴 *{user_name}'s Harem*\n\n"
        f"{cards_text}\n\n"
        f"📊 {total_unique} unique · {total_cards} total{filter_text}\n"
        f"📄 Page {page}/{total_pages}"
    )

    # Build keyboard
    keyboard = build_harem_keyboard(
        user_id=user_id,
        page=page,
        total_pages=total_pages,
        cards=cards,
        rarity_filter=rarity_filter,
        bot_username=bot_username
    )

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
# ⌨️ Keyboard Builder - Modern with Inline View
# ============================================================

def build_harem_keyboard(
    user_id: int,
    page: int,
    total_pages: int,
    cards: List[dict],
    rarity_filter: Optional[int] = None,
    bot_username: str = "LuLuCatchBot"
) -> InlineKeyboardMarkup:
    """Build modern keyboard with inline collection view."""
    
    buttons = []
    
    # Row 1: Quick card view buttons (3 per row max)
    if cards:
        quick_btns = []
        for idx, card in enumerate(cards):
            card_id = card.get("card_id", 0)
            emoji = RARITY_EMOJIS.get(card.get("rarity", 1), "☘️")
            quick_btns.append(
                InlineKeyboardButton(
                    f"{emoji}",
                    callback_data=f"hv:{user_id}:{card_id}:{page}:{rarity_filter or 0}"
                )
            )
            if len(quick_btns) == 6:
                buttons.append(quick_btns)
                quick_btns = []
        if quick_btns:
            buttons.append(quick_btns)

    # Row 2: Inline view button (KEY FEATURE)
    inline_query = f"collection.{user_id}"
    if rarity_filter:
        rarity_emoji = RARITY_EMOJIS.get(rarity_filter, "")
        inline_query += f".{rarity_emoji}"
    
    buttons.append([
        InlineKeyboardButton(
            "🔍 View Cards Inline",
            switch_inline_query_current_chat=inline_query
        )
    ])

    # Row 3: Navigation
    nav_row = []
    
    if page > 1:
        nav_row.append(InlineKeyboardButton(
            ButtonLabels.PREV, 
            callback_data=f"h:{user_id}:{page-1}:{rarity_filter or 0}"
        ))
    
    nav_row.append(InlineKeyboardButton(
        f"{page}/{total_pages}", 
        callback_data="noop"
    ))
    
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(
            ButtonLabels.NEXT, 
            callback_data=f"h:{user_id}:{page+1}:{rarity_filter or 0}"
        ))
    
    buttons.append(nav_row)

    # Row 4: Filter & Close
    buttons.append([
        InlineKeyboardButton("🎯 Filter", callback_data=f"hf:{user_id}:{page}"),
        InlineKeyboardButton(ButtonLabels.CLOSE, callback_data="hclose")
    ])

    return InlineKeyboardMarkup(buttons)


# ============================================================
# 🔍 Inline Collection Handler
# ============================================================

async def inline_collection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle inline queries for collection viewing.
    
    Query formats:
    - collection.{user_id} - View user's full collection
    - collection.{user_id}.{rarity_emoji} - Filter by rarity
    - collection.{user_id}.fav - View favorites only
    """
    if not update.inline_query:
        return
    
    query = update.inline_query.query.strip()
    
    # Only handle collection queries
    if not query.startswith("collection."):
        return
    
    # Parse query
    parts = query.split(".")
    
    if len(parts) < 2:
        await update.inline_query.answer(
            results=[],
            cache_time=5
        )
        return
    
    try:
        target_user_id = int(parts[1])
    except ValueError:
        await update.inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="❌ Invalid user ID",
                    description="Please use a valid collection link",
                    input_message_content=InputTextMessageContent(
                        message_text="❌ Invalid collection link"
                    )
                )
            ],
            cache_time=10
        )
        return
    
    # Parse rarity filter from emoji or name
    rarity_filter = None
    favorites_only = False
    
    if len(parts) >= 3:
        filter_part = parts[2]
        
        if filter_part == "fav":
            favorites_only = True
        else:
            # Check if it's a rarity emoji
            for rid, emoji in RARITY_EMOJIS.items():
                if filter_part == emoji or filter_part == emoji.strip():
                    rarity_filter = rid
                    break
            
            # Check if it's a rarity name
            if not rarity_filter:
                for rid, name in RARITY_NAMES.items():
                    if filter_part.lower() == name.lower():
                        rarity_filter = rid
                        break
    
    # Get offset for pagination
    offset_str = update.inline_query.offset
    offset = int(offset_str) if offset_str else 0
    
    app_logger.info(f"📦 Collection query: user={target_user_id}, rarity={rarity_filter}, offset={offset}")
    
    if not db.is_connected:
        await update.inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="⚠️ Database Offline",
                    description="Please try again later",
                    input_message_content=InputTextMessageContent(
                        message_text="⚠️ Database offline"
                    )
                )
            ],
            cache_time=10
        )
        return
    
    try:
        # Get user info
        user_info = await get_user_by_id(None, target_user_id)
        user_name = user_info.get("first_name", "User") if user_info else "User"
        
        # Fetch collection cards
        cards = await get_collection_cards(
            pool=None,
            user_id=target_user_id,
            offset=offset,
            limit=INLINE_RESULTS_LIMIT,
            rarity_filter=rarity_filter
        )
        
        # Filter favorites if requested
        if favorites_only:
            cards = [c for c in cards if c.get("is_favorite")]
        
        # No cards
        if not cards and offset == 0:
            filter_text = ""
            if rarity_filter:
                filter_text = f" with {RARITY_NAMES.get(rarity_filter, 'this')} rarity"
            elif favorites_only:
                filter_text = " marked as favorites"
            
            await update.inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        id=str(uuid4()),
                        title=f"📭 No cards{filter_text}",
                        description=f"{user_name}'s collection is empty",
                        input_message_content=InputTextMessageContent(
                            message_text=f"📭 {user_name} has no cards{filter_text}"
                        )
                    )
                ],
                cache_time=30
            )
            return
        
        # Build results
        results = []
        
        for card in cards:
            photo_file_id = card.get("photo_file_id")
            
            if not photo_file_id:
                continue
            
            card_id = card["card_id"]
            character_name = card["character_name"]
            anime = card["anime"]
            rarity = card.get("rarity", 1)
            quantity = card.get("quantity", 1)
            is_favorite = card.get("is_favorite", False)
            
            rarity_name, prob, rarity_emoji = rarity_to_text(rarity)
            
            # Build caption
            fav_text = " ❤️" if is_favorite else ""
            qty_text = f" ×{quantity}" if quantity > 1 else ""
            
            caption = (
                f"{rarity_emoji} *{character_name}*{qty_text}{fav_text}\n\n"
                f"🎬 {anime}\n"
                f"{rarity_emoji} {rarity_name}\n"
                f"🆔 `#{card_id}`\n\n"
                f"👤 _{user_name}'s collection_"
            )
            
            result = InlineQueryResultCachedPhoto(
                id=f"col_{target_user_id}_{card_id}_{uuid4().hex[:8]}",
                photo_file_id=photo_file_id,
                title=f"{rarity_emoji} {character_name}{qty_text}",
                description=f"{anime} • #{card_id}",
                caption=caption,
                parse_mode="Markdown"
            )
            results.append(result)
        
        # Pagination
        if len(cards) >= INLINE_RESULTS_LIMIT:
            next_offset = str(offset + INLINE_RESULTS_LIMIT)
        else:
            next_offset = ""
        
        await update.inline_query.answer(
            results=results,
            cache_time=60,
            is_personal=True,
            next_offset=next_offset
        )
        
        app_logger.info(f"✅ Collection: {len(results)} cards for user {target_user_id}")
        
    except Exception as e:
        error_logger.error(f"Collection inline error: {e}", exc_info=True)
        await update.inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="❌ Error",
                    description="Failed to load collection",
                    input_message_content=InputTextMessageContent(
                        message_text="❌ Failed to load collection"
                    )
                )
            ],
            cache_time=10
        )


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
    """Display card details with image."""
    
    query = update.callback_query
    
    card = await get_card_with_details(None, card_id)
    
    if not card:
        await query.answer("Card not found!", show_alert=True)
        return

    name = card.get("character_name", "Unknown")
    anime = card.get("anime", "Unknown")
    rarity = card.get("rarity", 1)
    photo = card.get("photo_file_id")
    unique_owners = card.get("unique_owners", 0)
    
    rarity_name, prob, emoji = rarity_to_text(rarity)
    user_qty = await get_user_card_quantity(None, user_id, card_id)

    caption = (
        f"{emoji} *{name}*\n\n"
        f"🎬 {anime}\n"
        f"{emoji} {rarity_name} ({prob}%)\n"
        f"🆔 `#{card_id}`\n\n"
        f"📦 You own: ×{user_qty}\n"
        f"👥 Total owners: {unique_owners}"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "❤️ Favorite", 
                callback_data=f"hfav:{user_id}:{card_id}:{return_page}:{rarity_filter}"
            ),
            InlineKeyboardButton(
                "🔄 Trade", 
                callback_data=f"htrade:{card_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                ButtonLabels.BACK, 
                callback_data=f"h:{user_id}:{return_page}:{rarity_filter}"
            )
        ]
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
            await query.edit_message_text(
                caption, 
                parse_mode=ParseMode.MARKDOWN, 
                reply_markup=keyboard
            )
    else:
        await query.edit_message_text(
            caption, 
            parse_mode=ParseMode.MARKDOWN, 
            reply_markup=keyboard
        )
    
    await query.answer()


# ============================================================
# 🔍 Filter Menu
# ============================================================

async def display_filter_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    current_page: int
) -> None:
    """Display rarity filter menu."""
    
    query = update.callback_query
    bot_username = context.bot.username or Config.BOT_USERNAME
    
    text = "🎯 *Filter by Rarity*\n\nTap a rarity or use inline view:"
    
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
    
    # Inline filter shortcuts
    buttons.append([
        InlineKeyboardButton(
            "💎 Rare+ Inline",
            switch_inline_query_current_chat=f"collection.{user_id}.💠"
        ),
        InlineKeyboardButton(
            "🌸 Legendary",
            switch_inline_query_current_chat=f"collection.{user_id}.🌸"
        ),
    ])
    
    buttons.append([
        InlineKeyboardButton(
            "❤️ Favorites",
            switch_inline_query_current_chat=f"collection.{user_id}.fav"
        ),
    ])
    
    buttons.append([
        InlineKeyboardButton("📋 Clear Filter", callback_data=f"h:{user_id}:1:0"),
        InlineKeyboardButton(ButtonLabels.BACK, callback_data=f"h:{user_id}:{current_page}:0")
    ])
    
    await query.edit_message_text(
        text, 
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    await query.answer()


# ============================================================
# ❤️ Toggle Favorite
# ============================================================

async def toggle_favorite_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Toggle card favorite status."""
    
    query = update.callback_query
    
    try:
        parts = query.data.split(":")
        user_id = int(parts[1])
        card_id = int(parts[2])
        return_page = int(parts[3]) if len(parts) > 3 else 1
        rarity_filter = int(parts[4]) if len(parts) > 4 else 0
    except (ValueError, IndexError):
        await query.answer("Error", show_alert=True)
        return
    
    # Verify ownership
    if query.from_user.id != user_id:
        await query.answer("Not your card!", show_alert=True)
        return
    
    # Toggle favorite
    new_status = await toggle_favorite(None, user_id, card_id)
    
    if new_status is not None:
        status_text = "❤️ Added to favorites" if new_status else "💔 Removed from favorites"
        await query.answer(status_text)
        
        # Refresh card view
        await display_card_detail(update, context, user_id, card_id, return_page, rarity_filter)
    else:
        await query.answer("Failed to update", show_alert=True)


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

    # Navigation: h:{user_id}:{page}:{filter}
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


async def harem_trade_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle trade initiation from harem."""
    
    query = update.callback_query
    
    try:
        card_id = int(query.data.split(":")[1])
    except (ValueError, IndexError):
        await query.answer("Error", show_alert=True)
        return
    
    await query.answer(
        f"💡 To trade this card, use:\n/offertrade {card_id} <user_id>",
        show_alert=True
    )


# ============================================================
# 📦 Handler Registration
# ============================================================

def register_harem_handlers(application: Application) -> None:
    """Register all harem handlers including inline collection."""
    
    # Commands
    application.add_handler(CommandHandler("harem", harem_command))
    application.add_handler(CommandHandler("collection", harem_command))

    # Inline collection handler (MUST check pattern carefully)
    application.add_handler(
        InlineQueryHandler(
            inline_collection_handler, 
            pattern=r"^collection\."
        )
    )

    # Callbacks
    application.add_handler(CallbackQueryHandler(harem_callback_handler, pattern=r"^h:"))
    application.add_handler(CallbackQueryHandler(harem_callback_handler, pattern=r"^hf:"))
    application.add_handler(CallbackQueryHandler(harem_callback_handler, pattern=r"^hclose$"))
    application.add_handler(CallbackQueryHandler(harem_callback_handler, pattern=r"^noop$"))
    application.add_handler(CallbackQueryHandler(harem_view_callback_handler, pattern=r"^hv:"))
    application.add_handler(CallbackQueryHandler(toggle_favorite_handler, pattern=r"^hfav:"))
    application.add_handler(CallbackQueryHandler(harem_trade_callback_handler, pattern=r"^htrade:"))

    app_logger.info("✅ Harem handlers registered (with inline collection)")


# Backward compatibility
register_collection_handlers = register_harem_handlers