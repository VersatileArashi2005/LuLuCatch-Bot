# ============================================================
# 📁 File: commands/inline_search.py
# 📍 Location: telegram_card_bot/commands/inline_search.py
# 📝 Description: Clean inline search - images only, ordered by ID
# ============================================================

from uuid import uuid4

from telegram import (
    Update,
    InlineQueryResultCachedPhoto,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from telegram.ext import (
    Application,
    InlineQueryHandler,
    ChosenInlineResultHandler,
    ContextTypes,
)

from config import Config
from db import db
from utils.logger import app_logger, error_logger
from utils.constants import RARITY_EMOJIS, RARITY_NAMES


# ============================================================
# 📊 Constants
# ============================================================

# Telegram allows max 50 results per inline query
# We'll fetch more and paginate
RESULTS_PER_PAGE = 50


# ============================================================
# 🔍 Parse Search Query
# ============================================================

def parse_search_query(query: str) -> dict:
    """
    Parse search query for special filters.
    
    Supports:
    - Regular text search
    - #123 or 123 for card ID
    - Rarity names (legendary, mythical, etc.)
    - Rarity emojis (🌸, 🏵️, etc.)
    
    Returns:
        dict with keys: type, value, original
    """
    query = query.strip()
    
    if not query:
        return {"type": "all", "value": None, "original": query}
    
    # Check for card ID (#123 or just 123)
    if query.startswith("#"):
        try:
            card_id = int(query[1:])
            return {"type": "card_id", "value": card_id, "original": query}
        except ValueError:
            pass
    elif query.isdigit():
        return {"type": "card_id", "value": int(query), "original": query}
    
    # Check for rarity emoji
    for rid, emoji in RARITY_EMOJIS.items():
        if query == emoji or query.startswith(emoji):
            return {"type": "rarity", "value": rid, "original": query}
    
    # Check for rarity name
    query_lower = query.lower()
    for rid, name in RARITY_NAMES.items():
        if query_lower == name.lower() or query_lower.startswith(name.lower()):
            return {"type": "rarity", "value": rid, "original": query}
    
    # Regular text search
    return {"type": "text", "value": query, "original": query}


# ============================================================
# 🎯 Main Inline Query Handler
# ============================================================

async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle inline queries for card search.
    
    Returns ONLY card images, ordered by card_id (ascending).
    No captions, no metadata - just clean images.
    """
    if not update.inline_query:
        return
    
    query = update.inline_query.query.strip()
    user = update.inline_query.from_user
    
    # Skip if it's a collection query (handled by harem.py)
    if query.startswith("collection."):
        return
    
    # Get offset for pagination
    offset_str = update.inline_query.offset
    offset = int(offset_str) if offset_str else 0
    
    app_logger.info(f"🔍 Inline search: '{query}' offset={offset} from {user.id}")
    
    # Check database
    if not db.is_connected:
        await update.inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="⚠️ Database Offline",
                    description="Please try again later",
                    input_message_content=InputTextMessageContent(
                        message_text="⚠️ Database is currently offline"
                    )
                )
            ],
            cache_time=10
        )
        return
    
    try:
        # Parse query
        parsed = parse_search_query(query)
        
        # Build SQL based on query type
        # Always order by card_id ASC (first added first)
        if parsed["type"] == "card_id":
            # Search by specific card ID
            cards = await db.fetch(
                """
                SELECT card_id, photo_file_id
                FROM cards
                WHERE is_active = TRUE AND card_id = $1
                LIMIT 1
                """,
                parsed["value"]
            )
        
        elif parsed["type"] == "rarity":
            # Filter by rarity, ordered by card_id
            cards = await db.fetch(
                """
                SELECT card_id, photo_file_id
                FROM cards
                WHERE is_active = TRUE AND rarity = $1
                ORDER BY card_id ASC
                LIMIT $2 OFFSET $3
                """,
                parsed["value"], RESULTS_PER_PAGE, offset
            )
        
        elif parsed["type"] == "text":
            # Text search, ordered by card_id
            search_pattern = f"%{parsed['value']}%"
            cards = await db.fetch(
                """
                SELECT card_id, photo_file_id
                FROM cards
                WHERE is_active = TRUE
                  AND (
                    LOWER(character_name) LIKE LOWER($1)
                    OR LOWER(anime) LIKE LOWER($1)
                  )
                ORDER BY card_id ASC
                LIMIT $2 OFFSET $3
                """,
                search_pattern, RESULTS_PER_PAGE, offset
            )
        
        else:
            # All cards - ordered by card_id ASC (oldest first)
            cards = await db.fetch(
                """
                SELECT card_id, photo_file_id
                FROM cards
                WHERE is_active = TRUE
                ORDER BY card_id ASC
                LIMIT $1 OFFSET $2
                """,
                RESULTS_PER_PAGE, offset
            )
        
        # No results
        if not cards and offset == 0:
            await update.inline_query.answer(
                results=[],
                cache_time=30,
                is_personal=False
            )
            return
        
        # Build results - IMAGES ONLY, NO CAPTION
        results = []
        
        for card in cards:
            photo_file_id = card.get("photo_file_id")
            
            if not photo_file_id:
                continue
            
            card_id = card["card_id"]
            
            # Create result with NO caption - just the image
            result = InlineQueryResultCachedPhoto(
                id=f"card_{card_id}",
                photo_file_id=photo_file_id,
                # No title, description, or caption - just the image
            )
            results.append(result)
        
        # Calculate next offset for pagination
        if len(cards) >= RESULTS_PER_PAGE:
            next_offset = str(offset + RESULTS_PER_PAGE)
        else:
            next_offset = ""
        
        await update.inline_query.answer(
            results=results,
            cache_time=300,  # Cache for 5 minutes since images don't change
            is_personal=False,
            next_offset=next_offset
        )
        
        app_logger.info(f"✅ Inline: {len(results)} results, next_offset={next_offset}")
        
    except Exception as e:
        error_logger.error(f"Inline search error: {e}", exc_info=True)
        await update.inline_query.answer(
            results=[],
            cache_time=10
        )


# ============================================================
# 📊 Chosen Inline Result Handler (Analytics)
# ============================================================

async def chosen_inline_result_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Track which inline results users select (for analytics)."""
    
    if not update.chosen_inline_result:
        return
    
    result_id = update.chosen_inline_result.result_id
    user_id = update.chosen_inline_result.from_user.id
    query = update.chosen_inline_result.query
    
    app_logger.info(f"📊 Inline result chosen: {result_id} by {user_id} (query: '{query}')")


# ============================================================
# 📦 Handler Registration
# ============================================================

def register_inline_handlers(application: Application) -> None:
    """Register inline search handlers."""
    
    application.add_handler(
        InlineQueryHandler(inline_query_handler),
        group=1
    )
    
    app_logger.info("✅ Inline search handlers registered")


def register_inline_callback_handlers(application: Application) -> None:
    """Register chosen inline result handler for analytics."""
    
    application.add_handler(
        ChosenInlineResultHandler(chosen_inline_result_handler)
    )
    
    app_logger.info("✅ Inline analytics handler registered")