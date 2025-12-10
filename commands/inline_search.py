# ============================================================
# 📁 File: commands/inline_search.py
# 📍 Location: telegram_card_bot/commands/inline_search.py
# 📝 Description: Inline search engine for anime/character lookup
# 
# Usage:
#   In main.py:
#     from commands.inline_search import register_inline_handlers
#     register_inline_handlers(application)
#   
#   In Telegram:
#     @YourBotName naruto
#     @YourBotName itachi
#     @YourBotName legendary
#     @YourBotName 💎
# ============================================================

import re
from uuid import uuid4
from typing import Optional, List, Dict, Any
from functools import lru_cache

from telegram import (
    Update,
    InlineQueryResultPhoto,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    InlineQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode

from db import db
from utils.logger import app_logger, error_logger
from utils.rarity import rarity_to_text, RARITY_TABLE, get_rarity_emoji


# ============================================================
# 📊 Constants & Configuration
# ============================================================

# Maximum results to return (Telegram limit is 50)
MAX_RESULTS = 50

# Minimum query length to perform search
MIN_QUERY_LENGTH = 2

# Maximum query length to prevent abuse
MAX_QUERY_LENGTH = 200

# Cache size for hot queries (simple LRU cache)
CACHE_SIZE = 100

# Sample suggestions for empty queries
SAMPLE_SUGGESTIONS = [
    "Naruto", "One Piece", "Attack on Titan", 
    "Demon Slayer", "Jujutsu Kaisen", "Legendary", "Emerald"
]

# Rarity name mappings (for searching by rarity name or emoji)
RARITY_SEARCH_MAP: Dict[str, int] = {
    # Names (lowercase)
    "normal": 1,
    "common": 2,
    "uncommon": 3,
    "rare": 4,
    "epic": 5,
    "limited": 6,
    "limited edition": 6,
    "platinum": 7,
    "emerald": 8,
    "crystal": 9,
    "mythical": 10,
    "legendary": 11,
    # Emojis
    "🛞": 1,
    "🌀": 2,
    "🥏": 3,
    "☘️": 4,
    "🫧": 5,
    "🎐": 6,
    "❄️": 7,
    "💎": 8,
    "🌸": 9,
    "🧿": 10,
    "⚡": 11,
}


# ============================================================
# 🗄️ Database Functions
# ============================================================

async def search_cards_by_text(query: str, limit: int = MAX_RESULTS) -> List[Dict[str, Any]]:
    """
    Search cards by anime name, character name, or card ID.
    
    Uses ILIKE for case-insensitive partial matching.
    
    Args:
        query: Search query string
        limit: Maximum number of results
        
    Returns:
        List of card records matching the query
    """
    if not db.is_connected:
        return []
    
    try:
        # Prepare search pattern
        search_pattern = f"%{query}%"
        
        # Check if query is a card ID
        if query.isdigit():
            card_id = int(query)
            result = await db.fetch(
                """
                SELECT * FROM cards 
                WHERE card_id = $1 AND is_active = TRUE
                LIMIT 1
                """,
                card_id
            )
            if result:
                return [dict(r) for r in result]
        
        # Search by anime or character name
        results = await db.fetch(
            """
            SELECT * FROM cards
            WHERE is_active = TRUE
              AND (
                LOWER(anime) LIKE LOWER($1)
                OR LOWER(character_name) LIKE LOWER($1)
              )
            ORDER BY rarity DESC, character_name ASC
            LIMIT $2
            """,
            search_pattern, limit
        )
        
        return [dict(r) for r in results]
        
    except Exception as e:
        error_logger.error(f"Error searching cards: {e}", exc_info=True)
        return []


async def search_cards_by_rarity(rarity_id: int, limit: int = MAX_RESULTS) -> List[Dict[str, Any]]:
    """
    Search cards by rarity ID.
    
    Args:
        rarity_id: Rarity ID (1-11)
        limit: Maximum number of results
        
    Returns:
        List of card records with the specified rarity
    """
    if not db.is_connected:
        return []
    
    try:
        results = await db.fetch(
            """
            SELECT * FROM cards
            WHERE is_active = TRUE AND rarity = $1
            ORDER BY anime ASC, character_name ASC
            LIMIT $2
            """,
            rarity_id, limit
        )
        
        return [dict(r) for r in results]
        
    except Exception as e:
        error_logger.error(f"Error searching cards by rarity: {e}", exc_info=True)
        return []


async def get_card_owners(card_id: int, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Get top owners of a specific card.
    
    Args:
        card_id: Card ID to look up
        limit: Maximum number of owners to return
        
    Returns:
        List of user records who own this card
    """
    if not db.is_connected:
        return []
    
    try:
        results = await db.fetch(
            """
            SELECT u.user_id, u.first_name, u.username, c.quantity
            FROM collections c
            JOIN users u ON c.user_id = u.user_id
            WHERE c.card_id = $1
            ORDER BY c.quantity DESC, c.caught_at ASC
            LIMIT $2
            """,
            card_id, limit
        )
        
        return [dict(r) for r in results]
        
    except Exception as e:
        error_logger.error(f"Error getting card owners: {e}", exc_info=True)
        return []


async def get_total_card_count() -> int:
    """Get total number of active cards in database."""
    if not db.is_connected:
        return 0
    
    try:
        result = await db.fetchval(
            "SELECT COUNT(*) FROM cards WHERE is_active = TRUE"
        )
        return result or 0
    except Exception:
        return 0


# ============================================================
# 🔧 Helper Functions
# ============================================================

def sanitize_query(query: str) -> str:
    """
    Sanitize and normalize the search query.
    
    Args:
        query: Raw query string from user
        
    Returns:
        Cleaned and trimmed query string
    """
    # Strip whitespace
    query = query.strip()
    
    # Limit length
    if len(query) > MAX_QUERY_LENGTH:
        query = query[:MAX_QUERY_LENGTH]
    
    # Remove potentially harmful characters (but keep emojis)
    # Only remove SQL-specific dangerous patterns
    query = re.sub(r'[;\'"\\]', '', query)
    
    return query


def check_rarity_query(query: str) -> Optional[int]:
    """
    Check if query matches a rarity name or emoji.
    
    Args:
        query: Search query
        
    Returns:
        Rarity ID if matched, None otherwise
    """
    query_lower = query.lower().strip()
    
    # Direct match
    if query_lower in RARITY_SEARCH_MAP:
        return RARITY_SEARCH_MAP[query_lower]
    
    # Check if query is in the emoji map
    if query in RARITY_SEARCH_MAP:
        return RARITY_SEARCH_MAP[query]
    
    # Partial match for rarity names
    for name, rarity_id in RARITY_SEARCH_MAP.items():
        if isinstance(name, str) and name.startswith(query_lower) and len(query_lower) >= 3:
            return rarity_id
    
    return None


def format_card_caption(card: Dict[str, Any], detailed: bool = False) -> str:
    """
    Format a card's caption for display.
    
    Args:
        card: Card record dictionary
        detailed: Whether to include extra details
        
    Returns:
        Formatted caption string
    """
    rarity_id = card.get("rarity", 1)
    rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity_id)
    
    character = card.get("character_name", "Unknown")
    anime = card.get("anime", "Unknown")
    card_id = card.get("card_id", 0)
    
    if detailed:
        caption = (
            f"{rarity_emoji} *{character}*\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎬 *Anime:* {anime}\n"
            f"🆔 *ID:* `#{card_id}`\n"
            f"✨ *Rarity:* {rarity_emoji} {rarity_name}\n"
            f"📊 *Drop Rate:* {rarity_prob}%\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
    else:
        caption = (
            f"{rarity_emoji} *{character}*\n"
            f"🎬 {anime}\n"
            f"🆔 #{card_id} • {rarity_name} ({rarity_prob}%)"
        )
    
    return caption


def format_result_description(card: Dict[str, Any]) -> str:
    """
    Format a short description for inline result.
    
    Args:
        card: Card record dictionary
        
    Returns:
        Short description string
    """
    rarity_id = card.get("rarity", 1)
    rarity_emoji = get_rarity_emoji(rarity_id)
    rarity_name = RARITY_TABLE.get(rarity_id, RARITY_TABLE[1]).name
    
    anime = card.get("anime", "Unknown")
    card_id = card.get("card_id", 0)
    
    return f"🎬 {anime} — ID: {card_id} — {rarity_emoji} {rarity_name}"


# ============================================================
# 🎯 Inline Query Handler
# ============================================================

async def inline_search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle inline queries for card search.
    
    Supports searching by:
    - Anime name (partial match)
    - Character name (partial match)
    - Card ID (exact match)
    - Rarity name or emoji (exact match)
    
    Args:
        update: Telegram update object
        context: Bot context
    """
    # Safety check
    if not update.inline_query:
        return
    
    query = update.inline_query.query
    user = update.inline_query.from_user
    
    app_logger.info(f"🔍 Inline search: '{query}' from user {user.id}")
    
    # ========================================
    # Check database connection
    # ========================================
    if not db.is_connected:
        await update.inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="⚠️ Database Offline",
                    description="The database is currently unavailable. Please try again later.",
                    input_message_content=InputTextMessageContent(
                        message_text="⚠️ Database is currently offline. Please try again later.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                )
            ],
            cache_time=10
        )
        return
    
    # ========================================
    # Sanitize query
    # ========================================
    query = sanitize_query(query)
    
    # ========================================
    # Handle empty query - show suggestions
    # ========================================
    if not query:
        total_cards = await get_total_card_count()
        
        suggestions = ", ".join(SAMPLE_SUGGESTIONS[:5])
        
        await update.inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="🔍 Search Cards",
                    description=f"Try: {suggestions}",
                    input_message_content=InputTextMessageContent(
                        message_text=(
                            f"🎴 *LuLuCatch Card Search*\n\n"
                            f"📦 Total cards: {total_cards:,}\n\n"
                            f"💡 *How to search:*\n"
                            f"• Type anime name: `@bot Naruto`\n"
                            f"• Type character: `@bot Itachi`\n"
                            f"• Type rarity: `@bot Legendary`\n"
                            f"• Type card ID: `@bot 42`"
                        ),
                        parse_mode=ParseMode.MARKDOWN
                    )
                )
            ],
            cache_time=300,
            switch_pm_text="🎴 Open Bot",
            switch_pm_parameter="inline_help"
        )
        return
    
    # ========================================
    # Handle very short queries
    # ========================================
    if len(query) < MIN_QUERY_LENGTH:
        await update.inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="✏️ Keep Typing...",
                    description=f"Enter at least {MIN_QUERY_LENGTH} characters to search",
                    input_message_content=InputTextMessageContent(
                        message_text="💡 Please enter at least 2 characters to search for cards.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                )
            ],
            cache_time=5
        )
        return
    
    # ========================================
    # Search for cards
    # ========================================
    results: List[Dict[str, Any]] = []
    
    # Check if query is a rarity search
    rarity_id = check_rarity_query(query)
    
    if rarity_id:
        # Search by rarity
        app_logger.info(f"🔍 Searching by rarity: {rarity_id}")
        results = await search_cards_by_rarity(rarity_id, limit=MAX_RESULTS)
    else:
        # Search by text (anime/character name or ID)
        results = await search_cards_by_text(query, limit=MAX_RESULTS)
    
    # ========================================
    # Handle no results
    # ========================================
    if not results:
        await update.inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title=f"😔 No cards found for '{query}'",
                    description="Try a different search term",
                    input_message_content=InputTextMessageContent(
                        message_text=f"🔍 No cards found matching: *{query}*",
                        parse_mode=ParseMode.MARKDOWN
                    )
                )
            ],
            cache_time=30
        )
        return
    
    # ========================================
    # Build inline results
    # ========================================
    inline_results = []
    
    for card in results[:MAX_RESULTS]:
        try:
            card_id = card.get("card_id", 0)
            character = card.get("character_name", "Unknown")
            anime = card.get("anime", "Unknown")
            rarity = card.get("rarity", 1)
            photo_file_id = card.get("photo_file_id")
            
            # Get rarity info
            rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity)
            
            # Format caption
            caption = format_card_caption(card, detailed=False)
            description = format_result_description(card)
            
            # Create result based on whether we have a photo
            if photo_file_id:
                # Use InlineQueryResultPhoto for cards with images
                result = InlineQueryResultPhoto(
                    id=str(uuid4()),
                    photo_file_id=photo_file_id,
                    title=f"{rarity_emoji} {character}",
                    description=description,
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                # Use InlineQueryResultArticle for cards without images
                result = InlineQueryResultArticle(
                    id=str(uuid4()),
                    title=f"{rarity_emoji} {character}",
                    description=description,
                    input_message_content=InputTextMessageContent(
                        message_text=caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
                )
            
            inline_results.append(result)
            
        except Exception as e:
            error_logger.error(f"Error building result for card {card.get('card_id')}: {e}")
            continue
    
    # ========================================
    # Check if we have more results (pagination indicator)
    # ========================================
    total_found = len(results)
    
    # If exactly at limit, there might be more
    if total_found >= MAX_RESULTS:
        inline_results.append(
            InlineQueryResultArticle(
                id=str(uuid4()),
                title=f"📊 Showing first {MAX_RESULTS} results",
                description="Try a more specific search to see more cards",
                input_message_content=InputTextMessageContent(
                    message_text=(
                        f"🔍 *Search Results*\n\n"
                        f"Found {MAX_RESULTS}+ cards matching: *{query}*\n\n"
                        f"💡 Try a more specific search to find what you're looking for!"
                    ),
                    parse_mode=ParseMode.MARKDOWN
                )
            )
        )
    
    # ========================================
    # Answer the inline query
    # ========================================
    try:
        await update.inline_query.answer(
            results=inline_results,
            cache_time=60,  # Cache for 1 minute
            is_personal=False,  # Results are same for all users
            switch_pm_text="🎴 Open Bot",
            switch_pm_parameter="search"
        )
        
        app_logger.info(f"✅ Returned {len(inline_results)} results for '{query}'")
        
    except Exception as e:
        error_logger.error(f"Error answering inline query: {e}", exc_info=True)


# ============================================================
# 🎯 Detailed Card View Handler (for exact matches)
# ============================================================

async def inline_card_detail_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle inline queries for specific card lookup with detailed info.
    
    Triggered when query matches pattern: #123 or id:123
    
    Args:
        update: Telegram update object
        context: Bot context
    """
    if not update.inline_query:
        return
    
    query = update.inline_query.query.strip()
    
    # Check for card ID patterns
    card_id: Optional[int] = None
    
    # Pattern: #123
    if query.startswith("#") and query[1:].isdigit():
        card_id = int(query[1:])
    # Pattern: id:123
    elif query.lower().startswith("id:") and query[3:].strip().isdigit():
        card_id = int(query[3:].strip())
    # Just a number
    elif query.isdigit():
        card_id = int(query)
    
    if card_id is None:
        return  # Not a card ID query, let main handler deal with it
    
    # Fetch card details
    if not db.is_connected:
        return
    
    try:
        card = await db.fetchrow(
            "SELECT * FROM cards WHERE card_id = $1 AND is_active = TRUE",
            card_id
        )
        
        if not card:
            await update.inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        id=str(uuid4()),
                        title=f"❌ Card #{card_id} not found",
                        description="This card doesn't exist or has been removed",
                        input_message_content=InputTextMessageContent(
                            message_text=f"❌ Card `#{card_id}` was not found.",
                            parse_mode=ParseMode.MARKDOWN
                        )
                    )
                ],
                cache_time=30
            )
            return
        
        card = dict(card)
        
        # Get card owners
        owners = await get_card_owners(card_id, limit=5)
        
        # Format detailed caption
        rarity_id = card.get("rarity", 1)
        rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity_id)
        
        character = card.get("character_name", "Unknown")
        anime = card.get("anime", "Unknown")
        total_caught = card.get("total_caught", 0)
        photo_file_id = card.get("photo_file_id")
        
        # Build owners text
        if owners:
            owners_text = "\n".join([
                f"  • {o.get('first_name', 'Unknown')} (x{o.get('quantity', 1)})"
                for o in owners[:5]
            ])
            owners_section = f"\n\n👥 *Top Owners:*\n{owners_text}"
        else:
            owners_section = "\n\n👥 *Owners:* None yet!"
        
        detailed_caption = (
            f"{rarity_emoji} *{character}*\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎬 *Anime:* {anime}\n"
            f"🆔 *Card ID:* `#{card_id}`\n"
            f"✨ *Rarity:* {rarity_emoji} {rarity_name}\n"
            f"📊 *Drop Rate:* {rarity_prob}%\n"
            f"🎯 *Times Caught:* {total_caught:,}\n"
            f"━━━━━━━━━━━━━━━━━━━━"
            f"{owners_section}"
        )
        
        # Build inline keyboard
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎴 View in Bot", url=f"t.me/{context.bot.username}?start=card_{card_id}"),
            ]
        ])
        
        # Build result
        if photo_file_id:
            result = InlineQueryResultPhoto(
                id=str(uuid4()),
                photo_file_id=photo_file_id,
                title=f"{rarity_emoji} {character} — Detailed View",
                description=f"🎬 {anime} — #{card_id} — {rarity_name}",
                caption=detailed_caption,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
        else:
            result = InlineQueryResultArticle(
                id=str(uuid4()),
                title=f"{rarity_emoji} {character} — Detailed View",
                description=f"🎬 {anime} — #{card_id} — {rarity_name}",
                input_message_content=InputTextMessageContent(
                    message_text=detailed_caption,
                    parse_mode=ParseMode.MARKDOWN
                ),
                reply_markup=keyboard
            )
        
        await update.inline_query.answer(
            results=[result],
            cache_time=60,
            is_personal=False
        )
        
        app_logger.info(f"✅ Returned detailed view for card #{card_id}")
        
    except Exception as e:
        error_logger.error(f"Error in card detail handler: {e}", exc_info=True)


# ============================================================
# 🔧 Combined Handler (routes to appropriate handler)
# ============================================================

async def inline_query_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Main inline query router.
    
    Routes queries to the appropriate handler based on query pattern.
    
    Args:
        update: Telegram update object
        context: Bot context
    """
    if not update.inline_query:
        return
    
    query = update.inline_query.query.strip()
    
    # Check if this is a specific card ID lookup
    if (
        query.startswith("#") or
        query.lower().startswith("id:") or
        (query.isdigit() and len(query) <= 10)
    ):
        # Route to detailed handler for single card lookups
        await inline_card_detail_handler(update, context)
    else:
        # Route to main search handler
        await inline_search_handler(update, context)


# ============================================================
# 📦 Handler Registration
# ============================================================

def register_inline_handlers(application: Application) -> None:
    """
    Register inline query handlers with the application.
    
    This function should be called from main.py to set up
    inline search functionality.
    
    Args:
        application: The Telegram bot Application instance
        
    Example:
        from commands.inline_search import register_inline_handlers
        register_inline_handlers(application)
    """
    # Register the main inline query handler
    application.add_handler(InlineQueryHandler(inline_query_router))
    
    app_logger.info("✅ Inline search handlers registered")


# ============================================================
# 🧪 Optional: Callback handlers for inline buttons
# ============================================================

async def inline_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle callback queries from inline message buttons.
    
    Handles:
    - addcol_<card_id>: Add card to collection (placeholder)
    - owners_<card_id>: View card owners
    
    Args:
        update: Telegram update object
        context: Bot context
    """
    if not update.callback_query:
        return
    
    query = update.callback_query
    data = query.data
    
    if not data:
        return
    
    # Handle add to collection
    if data.startswith("addcol_"):
        await query.answer(
            "🎴 Use /catch in a group to collect cards!",
            show_alert=True
        )
        return
    
    # Handle view owners
    if data.startswith("owners_"):
        try:
            card_id = int(data.replace("owners_", ""))
            owners = await get_card_owners(card_id, limit=10)
            
            if owners:
                owners_text = "\n".join([
                    f"• {o.get('first_name', 'Unknown')} — x{o.get('quantity', 1)}"
                    for o in owners
                ])
                message = f"👥 *Card #{card_id} Owners:*\n\n{owners_text}"
            else:
                message = f"👥 *Card #{card_id}*\n\nNo one owns this card yet!"
            
            await query.answer()
            await query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            error_logger.error(f"Error in owners callback: {e}")
            await query.answer("❌ Error loading owners", show_alert=True)


def register_inline_callback_handlers(application: Application) -> None:
    """
    Register callback handlers for inline message buttons.
    
    Args:
        application: The Telegram bot Application instance
    """
    from telegram.ext import CallbackQueryHandler
    
    application.add_handler(
        CallbackQueryHandler(inline_button_callback, pattern=r"^(addcol_|owners_)")
    )
    
    app_logger.info("✅ Inline callback handlers registered")