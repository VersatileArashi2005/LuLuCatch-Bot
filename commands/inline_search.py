# ============================================================
# 📁 File: commands/inline_search.py
# 📍 Location: telegram_card_bot/commands/inline_search.py
# 📝 Description: Inline search - beautiful card display with owner count
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
from utils.rarity import rarity_to_text


# ============================================================
# 📊 Constants
# ============================================================

RESULTS_PER_PAGE = 50


# ============================================================
# 🎨 Caption Formatter
# ============================================================

def format_card_caption(
    card_id: int,
    character_name: str,
    anime: str,
    rarity: int,
    owner_count: int
) -> str:
    """
    Create a beautiful, engaging card caption.
    """
    rarity_name, _, rarity_emoji = rarity_to_text(rarity)
    
    # Owner text
    if owner_count == 0:
        owner_text = "👤 No owners yet — Be the first!"
    elif owner_count == 1:
        owner_text = "👤 1 collector owns this"
    else:
        owner_text = f"👥 {owner_count} collectors own this"
    
    caption = (
        f"┏━━━━━━━━━━━━━━━━━━━━┓\n"
        f"   🎴 *CARD DISCOVERED!*\n"
        f"┗━━━━━━━━━━━━━━━━━━━━┛\n\n"
        f"🆔 *Card:* `#{card_id}` — {character_name}\n"
        f"🎬 *Anime:* {anime}\n"
        f"✨ *Rarity:* {rarity_name} {rarity_emoji}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{owner_text}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    return caption


# ============================================================
# 🎯 Main Inline Query Handler
# ============================================================

async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle inline queries with pagination and owner count.
    """
    if not update.inline_query:
        return
    
    query = update.inline_query.query.strip()
    user = update.inline_query.from_user
    
    # Get offset for pagination
    offset_str = update.inline_query.offset
    offset = int(offset_str) if offset_str else 0
    
    app_logger.info(f"🔍 Inline: '{query}' offset={offset} from {user.id}")
    
    # Check database
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
        # Fetch cards with owner count
        if query:
            search_pattern = f"%{query}%"
            cards = await db.fetch(
                """
                SELECT 
                    c.card_id, 
                    c.character_name, 
                    c.anime, 
                    c.rarity, 
                    c.photo_file_id,
                    (
                        SELECT COUNT(DISTINCT user_id) 
                        FROM collections 
                        WHERE card_id = c.card_id AND quantity > 0
                    ) as owner_count
                FROM cards c
                WHERE c.is_active = TRUE
                  AND (
                    LOWER(c.character_name) LIKE LOWER($1)
                    OR LOWER(c.anime) LIKE LOWER($1)
                  )
                ORDER BY c.card_id ASC
                LIMIT $2 OFFSET $3
                """,
                search_pattern, RESULTS_PER_PAGE, offset
            )
        else:
            cards = await db.fetch(
                """
                SELECT 
                    c.card_id, 
                    c.character_name, 
                    c.anime, 
                    c.rarity, 
                    c.photo_file_id,
                    (
                        SELECT COUNT(DISTINCT user_id) 
                        FROM collections 
                        WHERE card_id = c.card_id AND quantity > 0
                    ) as owner_count
                FROM cards c
                WHERE c.is_active = TRUE
                ORDER BY c.card_id ASC
                LIMIT $1 OFFSET $2
                """,
                RESULTS_PER_PAGE, offset
            )
        
        # No cards on first page
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
            owner_count = card.get("owner_count", 0)
            
            # Get rarity emoji for preview
            _, _, rarity_emoji = rarity_to_text(rarity)
            
            # Beautiful caption
            caption = format_card_caption(
                card_id=card_id,
                character_name=character_name,
                anime=anime,
                rarity=rarity,
                owner_count=owner_count
            )
            
            result = InlineQueryResultCachedPhoto(
                id=str(uuid4()),
                photo_file_id=photo_file_id,
                title=f"{rarity_emoji} {character_name}",
                description=f"🎬 {anime} • #{card_id} • 👥 {owner_count}",
                caption=caption,
                parse_mode="Markdown"
            )
            results.append(result)
        
        # Pagination
        if len(cards) == RESULTS_PER_PAGE:
            next_offset = str(offset + RESULTS_PER_PAGE)
        else:
            next_offset = ""
        
        await update.inline_query.answer(
            results=results,
            cache_time=30,  # Shorter cache for owner count accuracy
            is_personal=False,
            next_offset=next_offset
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