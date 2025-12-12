# ============================================================
# 📁 File: commands/inline_search.py
# 📍 Location: telegram_card_bot/commands/inline_search.py
# 📝 Description: Inline search - shows all cards by ID order with pagination
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
    ContextTypes,
)

from db import db
from utils.logger import app_logger, error_logger
from utils.rarity import get_rarity_emoji


# ============================================================
# 📊 Constants
# ============================================================

# Telegram allows max 50 results per query
RESULTS_PER_PAGE = 50


# ============================================================
# 🎯 Main Inline Query Handler
# ============================================================

async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle inline queries with pagination.
    
    - Empty query (@bot): Show all cards ordered by ID (1, 2, 3...)
    - With query (@bot naruto): Filter cards by name/anime
    - Supports infinite scroll via offset pagination
    """
    if not update.inline_query:
        return
    
    query = update.inline_query.query.strip()
    user = update.inline_query.from_user
    
    # Get offset for pagination (empty string = first page)
    offset_str = update.inline_query.offset
    offset = int(offset_str) if offset_str else 0
    
    app_logger.info(f"🔍 Inline: '{query}' offset={offset} from {user.id}")
    
    # Check database connection
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
        # Fetch cards from database
        if query:
            # Search with filter, ordered by card_id
            search_pattern = f"%{query}%"
            cards = await db.fetch(
                """
                SELECT card_id, character_name, anime, rarity, photo_file_id
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
            # No query - show all cards ordered by card_id (1, 2, 3...)
            cards = await db.fetch(
                """
                SELECT card_id, character_name, anime, rarity, photo_file_id
                FROM cards
                WHERE is_active = TRUE
                ORDER BY card_id ASC
                LIMIT $1 OFFSET $2
                """,
                RESULTS_PER_PAGE, offset
            )
        
        # No cards found (only show message on first page)
        if not cards and offset == 0:
            message = f"No cards found for '{query}'" if query else "No cards in database"
            await update.inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        id=str(uuid4()),
                        title="📭 No cards found",
                        description=message,
                        input_message_content=InputTextMessageContent(
                            message_text=message
                        )
                    )
                ],
                cache_time=30
            )
            return
        
        # Build results (images only, no caption)
        results = []
        
        for card in cards:
            photo_file_id = card.get("photo_file_id")
            
            # Skip cards without images
            if not photo_file_id:
                continue
            
            card_id = card["card_id"]
            character_name = card["character_name"]
            anime = card["anime"]
            rarity = card.get("rarity", 1)
            rarity_emoji = get_rarity_emoji(rarity)
            
            result = InlineQueryResultCachedPhoto(
                id=str(uuid4()),
                photo_file_id=photo_file_id,
                title=f"{rarity_emoji} {character_name}",
                description=f"🎬 {anime} • #{card_id}",
                caption="",  # Empty = image only
            )
            results.append(result)
        
        # Calculate next offset for pagination
        # If we got full page, there might be more
        if len(cards) == RESULTS_PER_PAGE:
            next_offset = str(offset + RESULTS_PER_PAGE)
        else:
            next_offset = ""  # No more results
        
        # Send results
        await update.inline_query.answer(
            results=results,
            cache_time=60,
            is_personal=False,
            next_offset=next_offset  # Enables infinite scroll
        )
        
        app_logger.info(f"✅ Returned {len(results)} cards, next_offset={next_offset}")
        
    except Exception as e:
        error_logger.error(f"Inline search error: {e}", exc_info=True)
        await update.inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="❌ Error",
                    description="Something went wrong",
                    input_message_content=InputTextMessageContent(
                        message_text="❌ An error occurred"
                    )
                )
            ],
            cache_time=10
        )


# ============================================================
# 📦 Handler Registration
# ============================================================

def register_inline_handlers(application: Application) -> None:
    """Register inline query handlers."""
    application.add_handler(InlineQueryHandler(inline_query_handler))
    app_logger.info("✅ Inline search handlers registered")


def register_inline_callback_handlers(application: Application) -> None:
    """Placeholder for compatibility."""
    pass