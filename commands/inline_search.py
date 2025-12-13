# ============================================================
# 📁 File: commands/inline_search.py
# 📍 Location: telegram_card_bot/commands/inline_search.py
# 📝 Description: Enhanced inline search with modern UI
# ============================================================

from uuid import uuid4

from telegram import (
    Update,
    InlineQueryResultCachedPhoto,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
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
from utils.rarity import rarity_to_text, get_rarity, RARITY_TABLE
from utils.constants import (
    RARITY_EMOJIS,
    RARITY_NAMES,
    Pagination,
)


# ============================================================
# 📊 Constants
# ============================================================

RESULTS_PER_PAGE = Pagination.INLINE_RESULTS


# ============================================================
# 🎨 Caption Formatter
# ============================================================

def format_inline_caption(
    card_id: int,
    character_name: str,
    anime: str,
    rarity: int,
    owner_count: int = 0
) -> str:
    """Create clean card caption for inline results."""
    
    rarity_name, prob, rarity_emoji = rarity_to_text(rarity)
    
    # Owner text
    if owner_count == 0:
        owner_text = "_No owners yet_"
    elif owner_count == 1:
        owner_text = "_1 collector_"
    else:
        owner_text = f"_{owner_count} collectors_"
    
    caption = (
        f"{rarity_emoji} *{character_name}*\n\n"
        f"🎬 {anime}\n"
        f"{rarity_emoji} {rarity_name} ({prob}%)\n"
        f"🆔 `#{card_id}`\n\n"
        f"👥 {owner_text}"
    )
    
    return caption


def format_card_title(
    character_name: str,
    rarity: int
) -> str:
    """Format card title for inline result."""
    rarity_emoji = RARITY_EMOJIS.get(rarity, "☘️")
    return f"{rarity_emoji} {character_name}"


def format_card_description(
    anime: str,
    card_id: int,
    owner_count: int = 0
) -> str:
    """Format card description for inline result."""
    return f"{anime} • #{card_id} • 👥 {owner_count}"


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
    
    Supports:
    - Empty query: Show recent/popular cards
    - Text: Search by character or anime name
    - #ID: Search by card ID
    - Rarity name/emoji: Filter by rarity
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
        if parsed["type"] == "card_id":
            # Search by specific card ID
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
            # Filter by rarity
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
                ORDER BY c.character_name ASC
                LIMIT $2 OFFSET $3
                """,
                parsed["value"], RESULTS_PER_PAGE, offset
            )
        
        elif parsed["type"] == "text":
            # Text search
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
                ORDER BY c.rarity DESC, c.character_name ASC
                LIMIT $2 OFFSET $3
                """,
                search_pattern, RESULTS_PER_PAGE, offset
            )
        
        else:
            # All cards (empty query)
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
                ORDER BY c.rarity DESC, c.card_id DESC
                LIMIT $1 OFFSET $2
                """,
                RESULTS_PER_PAGE, offset
            )
        
        # No results on first page
        if not cards and offset == 0:
            hint_text = ""
            if parsed["type"] == "text":
                hint_text = f"No cards matching '{parsed['value']}'"
            elif parsed["type"] == "rarity":
                rarity_name = RARITY_NAMES.get(parsed["value"], "this rarity")
                hint_text = f"No {rarity_name} cards found"
            elif parsed["type"] == "card_id":
                hint_text = f"Card #{parsed['value']} not found"
            else:
                hint_text = "No cards in database"
            
            await update.inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        id=str(uuid4()),
                        title="📭 No cards found",
                        description=hint_text,
                        input_message_content=InputTextMessageContent(
                            message_text=f"📭 {hint_text}"
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
            
            # Format caption
            caption = format_inline_caption(
                card_id=card_id,
                character_name=character_name,
                anime=anime,
                rarity=rarity,
                owner_count=owner_count
            )
            
            result = InlineQueryResultCachedPhoto(
                id=f"card_{card_id}_{uuid4().hex[:8]}",
                photo_file_id=photo_file_id,
                title=format_card_title(character_name, rarity),
                description=format_card_description(anime, card_id, owner_count),
                caption=caption,
                parse_mode="Markdown"
            )
            results.append(result)
        
        # Pagination
        if len(cards) >= RESULTS_PER_PAGE:
            next_offset = str(offset + RESULTS_PER_PAGE)
        else:
            next_offset = ""
        
        # Add help hint on first page with empty query
        if offset == 0 and not query:
            results.insert(0, InlineQueryResultArticle(
                id="help_hint",
                title="💡 Search Tips",
                description="Type anime name, character, #ID, or rarity",
                input_message_content=InputTextMessageContent(
                    message_text=(
                        "🔍 *Inline Search Tips*\n\n"
                        "• Type character or anime name\n"
                        "• Use `#123` for specific card ID\n"
                        "• Type `legendary` or `🌸` for rarity filter\n"
                        "• Use `collection.YOUR_ID` to view your cards"
                    ),
                    parse_mode="Markdown"
                )
            ))
        
        await update.inline_query.answer(
            results=results,
            cache_time=60,
            is_personal=False,
            next_offset=next_offset
        )
        
        app_logger.info(f"✅ Inline: {len(results)} results, next_offset={next_offset}")
        
    except Exception as e:
        error_logger.error(f"Inline search error: {e}", exc_info=True)
        await update.inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="❌ Search Error",
                    description="Something went wrong",
                    input_message_content=InputTextMessageContent(
                        message_text="❌ An error occurred during search"
                    )
                )
            ],
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
    
    # Main inline query handler (lower priority than collection handler)
    application.add_handler(
        InlineQueryHandler(inline_query_handler),
        group=1  # Lower priority
    )
    
    app_logger.info("✅ Inline search handlers registered")


def register_inline_callback_handlers(application: Application) -> None:
    """Register chosen inline result handler for analytics."""
    
    application.add_handler(
        ChosenInlineResultHandler(chosen_inline_result_handler)
    )
    
    app_logger.info("✅ Inline analytics handler registered")