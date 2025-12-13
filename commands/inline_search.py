# ============================================================
# 📁 File: commands/inline_search.py
# 📍 Location: telegram_card_bot/commands/inline_search.py
# 📝 Description: Clean inline search - image previews, detailed caption on send
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
from utils.rarity import rarity_to_text
from utils.constants import RARITY_EMOJIS, RARITY_NAMES


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
    owner_count: int = 0
) -> str:
    """Create detailed card caption for the sent message."""
    
    rarity_name, prob, rarity_emoji = rarity_to_text(rarity)
    
    if owner_count == 0:
        owner_text = "No owners yet"
    elif owner_count == 1:
        owner_text = "1 collector"
    else:
        owner_text = f"{owner_count} collectors"
    
    # Using simpler markdown to avoid parsing issues
    caption = (
        f"{rarity_emoji} {character_name}\n"
        f"\n"
        f"🎬 {anime}\n"
        f"{rarity_emoji} {rarity_name} ({prob}%)\n"
        f"🆔 #{card_id}\n"
        f"\n"
        f"👥 {owner_text}"
    )
    
    return caption


# ============================================================
# 🔍 Parse Search Query
# ============================================================

def parse_search_query(query: str) -> dict:
    """
    Parse search query for special filters.
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
    """
    if not update.inline_query:
        return
    
    query = update.inline_query.query.strip()
    user = update.inline_query.from_user
    
    # Skip collection queries
    if query.startswith("collection."):
        return
    
    offset_str = update.inline_query.offset
    offset = int(offset_str) if offset_str else 0
    
    app_logger.info(f"🔍 Inline search: '{query}' offset={offset} from {user.id}")
    
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
        parsed = parse_search_query(query)
        
        # Build query based on type
        if parsed["type"] == "card_id":
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
                WHERE c.is_active = TRUE AND c.card_id = $1
                LIMIT 1
                """,
                parsed["value"]
            )
        
        elif parsed["type"] == "rarity":
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
                WHERE c.is_active = TRUE AND c.rarity = $1
                ORDER BY c.card_id ASC
                LIMIT $2 OFFSET $3
                """,
                parsed["value"], RESULTS_PER_PAGE, offset
            )
        
        elif parsed["type"] == "text":
            search_pattern = f"%{parsed['value']}%"
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
        
        if not cards and offset == 0:
            await update.inline_query.answer(
                results=[],
                cache_time=30,
                is_personal=False
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
            rarity_emoji = RARITY_EMOJIS.get(rarity, "❓")
            
            # Build caption for sent message
            caption = format_card_caption(
                card_id=card_id,
                character_name=character_name,
                anime=anime,
                rarity=rarity,
                owner_count=owner_count
            )
            
            # Log for debugging
            app_logger.debug(f"Card {card_id} caption: {caption[:50]}...")
            
            result = InlineQueryResultCachedPhoto(
                id=f"card_{card_id}_{uuid4().hex[:6]}",
                photo_file_id=photo_file_id,
                title=f"{rarity_emoji} {character_name}",
                description=f"{anime} • #{card_id}",
                caption=caption,
                parse_mode=None  # No parse mode to avoid markdown issues
            )
            results.append(result)
        
        # Pagination
        next_offset = str(offset + RESULTS_PER_PAGE) if len(cards) >= RESULTS_PER_PAGE else ""
        
        await update.inline_query.answer(
            results=results,
            cache_time=300,
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
# 📊 Chosen Inline Result Handler
# ============================================================

async def chosen_inline_result_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Track which inline results users select."""
    
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
    """Register chosen inline result handler."""
    
    application.add_handler(
        ChosenInlineResultHandler(chosen_inline_result_handler)
    )
    
    app_logger.info("✅ Inline analytics handler registered")