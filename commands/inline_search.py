# ============================================================
# 📁 File: commands/inline_search.py
# 📍 Location: telegram_card_bot/commands/inline_search.py
# 📝 Description: Inline search - search characters and show card images
# ============================================================

from uuid import uuid4
from typing import List, Optional

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

from db import db, get_unique_characters
from utils.logger import app_logger, error_logger
from utils.rarity import get_rarity_emoji


# ============================================================
# 📊 Constants
# ============================================================

MAX_RESULTS = 50


# ============================================================
# 🎯 Main Inline Query Handler
# ============================================================

async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle inline queries.
    
    - Empty query: Show all available characters (as article suggestions)
    - With query: Search and show matching card images directly
    """
    if not update.inline_query:
        return
    
    query = update.inline_query.query.strip()
    user = update.inline_query.from_user
    
    app_logger.info(f"🔍 Inline: '{query}' from {user.id}")
    
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
    
    # ========================================
    # Empty query - show character list
    # ========================================
    if not query:
        await show_character_list(update)
        return
    
    # ========================================
    # Has query - show matching card images
    # ========================================
    await show_matching_cards(update, query)


# ============================================================
# 👤 Show Character List (Empty Query)
# ============================================================

async def show_character_list(update: Update) -> None:
    """
    Show list of all available character names.
    User can tap to see the name, then type it to search.
    """
    try:
        characters = await get_unique_characters(None, None, MAX_RESULTS)
        
        if not characters:
            await update.inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        id=str(uuid4()),
                        title="📭 No characters available",
                        description="No cards have been uploaded yet",
                        input_message_content=InputTextMessageContent(
                            message_text="No characters available"
                        )
                    )
                ],
                cache_time=60
            )
            return
        
        results = []
        
        for char in characters:
            character_name = char["character_name"]
            anime = char["anime"]
            card_count = char["card_count"]
            
            result = InlineQueryResultArticle(
                id=str(uuid4()),
                title=f"👤 {character_name}",
                description=f"🎬 {anime} • 🎴 {card_count} card(s) — Type name to see cards",
                input_message_content=InputTextMessageContent(
                    message_text=f"👤 *{character_name}*\n🎬 {anime}",
                    parse_mode="Markdown"
                )
            )
            results.append(result)
        
        await update.inline_query.answer(
            results=results,
            cache_time=120,
            is_personal=False,
            switch_pm_text="💡 Type a character name to see cards",
            switch_pm_parameter="inline_help"
        )
        
        app_logger.info(f"✅ Showed {len(results)} characters")
        
    except Exception as e:
        error_logger.error(f"Error showing character list: {e}", exc_info=True)


# ============================================================
# 🎴 Show Matching Cards (With Query)
# ============================================================

async def show_matching_cards(update: Update, query: str) -> None:
    """
    Search for cards matching the query and show images only.
    Searches both character names and anime names.
    """
    try:
        # Search in database
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
            ORDER BY rarity DESC, character_name ASC
            LIMIT $2
            """,
            search_pattern, MAX_RESULTS
        )
        
        if not cards:
            await update.inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        id=str(uuid4()),
                        title=f"🔍 No results for '{query}'",
                        description="Try a different search term",
                        input_message_content=InputTextMessageContent(
                            message_text=f"No cards found for: {query}"
                        )
                    )
                ],
                cache_time=30
            )
            return
        
        results = []
        
        for card in cards:
            photo_file_id = card.get("photo_file_id")
            
            if not photo_file_id:
                continue
            
            card_id = card["card_id"]
            character_name = card["character_name"]
            anime = card["anime"]
            rarity = card.get("rarity", 1)
            rarity_emoji = get_rarity_emoji(rarity)
            
            # Image only - empty caption
            result = InlineQueryResultCachedPhoto(
                id=str(uuid4()),
                photo_file_id=photo_file_id,
                title=f"{rarity_emoji} {character_name}",
                description=f"🎬 {anime} • #{card_id}",
                caption="",  # No caption = image only
            )
            results.append(result)
        
        if not results:
            await update.inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        id=str(uuid4()),
                        title=f"❌ No images for '{query}'",
                        description="Cards found but no images available",
                        input_message_content=InputTextMessageContent(
                            message_text=f"No card images for: {query}"
                        )
                    )
                ],
                cache_time=30
            )
            return
        
        await update.inline_query.answer(
            results=results,
            cache_time=60,
            is_personal=False
        )
        
        app_logger.info(f"✅ Showed {len(results)} cards for '{query}'")
        
    except Exception as e:
        error_logger.error(f"Error showing matching cards: {e}", exc_info=True)


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