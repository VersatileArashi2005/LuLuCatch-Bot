# ============================================================
# 📁 File: commands/inline_search.py
# 📍 Location: telegram_card_bot/commands/inline_search.py
# 📝 Description: Inline search - shows characters, then their cards (images only)
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

from db import db, get_unique_characters, get_cards_by_character
from utils.logger import app_logger, error_logger
from utils.rarity import get_rarity_emoji


# ============================================================
# 📊 Constants
# ============================================================

MAX_RESULTS = 50
MIN_QUERY_LENGTH = 1


# ============================================================
# 🎯 Main Inline Query Handler
# ============================================================

async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle inline queries.
    
    - Empty/short query: Show character name suggestions
    - "char:CharacterName": Show all cards for that character (images only)
    - Regular query: Search and show character suggestions
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
    # Check if user selected a character (show cards)
    # ========================================
    if query.startswith("char:"):
        character_name = query[5:].strip()
        await show_character_cards(update, character_name)
        return
    
    # ========================================
    # Show character suggestions
    # ========================================
    await show_character_suggestions(update, query)


# ============================================================
# 👤 Show Character Suggestions
# ============================================================

async def show_character_suggestions(update: Update, query: str) -> None:
    """
    Show list of character names matching the query.
    Tapping a character will trigger showing their cards.
    """
    try:
        # Get unique characters
        if query and len(query) >= MIN_QUERY_LENGTH:
            characters = await get_unique_characters(None, query, MAX_RESULTS)
        else:
            # Empty query - show all characters
            characters = await get_unique_characters(None, None, MAX_RESULTS)
        
        # No results
        if not characters:
            await update.inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        id=str(uuid4()),
                        title="🔍 No characters found",
                        description=f"No results for '{query}'" if query else "No characters available",
                        input_message_content=InputTextMessageContent(
                            message_text=f"No characters found for: {query}" if query else "No characters available"
                        )
                    )
                ],
                cache_time=30
            )
            return
        
        # Build character suggestions
        results = []
        
        for char in characters:
            character_name = char["character_name"]
            anime = char["anime"]
            card_count = char["card_count"]
            
            # Create article result that switches query to show cards
            result = InlineQueryResultArticle(
                id=str(uuid4()),
                title=f"👤 {character_name}",
                description=f"🎬 {anime} • 🎴 {card_count} card(s)",
                input_message_content=InputTextMessageContent(
                    message_text=f"👤 {character_name}\n🎬 {anime}"
                ),
                # This is the key: when user taps, it changes query to "char:Name"
                # But Telegram doesn't support this directly, so we use switch_inline_query
            )
            results.append(result)
        
        await update.inline_query.answer(
            results=results,
            cache_time=60,
            is_personal=False,
            switch_pm_text="💡 Tap a name, then add 'char:' prefix",
            switch_pm_parameter="inline_help"
        )
        
        app_logger.info(f"✅ Showed {len(results)} character suggestions")
        
    except Exception as e:
        error_logger.error(f"Error showing character suggestions: {e}", exc_info=True)


# ============================================================
# 🎴 Show Character Cards (Images Only)
# ============================================================

async def show_character_cards(update: Update, character_name: str) -> None:
    """
    Show all cards for a specific character.
    Displays images only, no text captions.
    """
    if not character_name:
        await update.inline_query.answer(results=[], cache_time=5)
        return
    
    try:
        # Get all cards for this character
        cards = await get_cards_by_character(None, character_name, MAX_RESULTS)
        
        if not cards:
            await update.inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        id=str(uuid4()),
                        title=f"❌ No cards for '{character_name}'",
                        description="Try a different character name",
                        input_message_content=InputTextMessageContent(
                            message_text=f"No cards found for: {character_name}"
                        )
                    )
                ],
                cache_time=30
            )
            return
        
        # Build image results (NO CAPTION - images only)
        results = []
        
        for card in cards:
            card_id = card["card_id"]
            photo_file_id = card.get("photo_file_id")
            rarity = card.get("rarity", 1)
            
            if not photo_file_id:
                continue
            
            # Get rarity emoji for title
            rarity_emoji = get_rarity_emoji(rarity)
            
            # Create photo result with NO caption (image only)
            result = InlineQueryResultCachedPhoto(
                id=str(uuid4()),
                photo_file_id=photo_file_id,
                title=f"{rarity_emoji} {character_name}",
                description=f"Card #{card_id}",
                caption="",  # Empty caption = image only
            )
            results.append(result)
        
        if not results:
            await update.inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        id=str(uuid4()),
                        title=f"❌ No images for '{character_name}'",
                        description="Cards exist but have no images",
                        input_message_content=InputTextMessageContent(
                            message_text=f"No card images found for: {character_name}"
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
        
        app_logger.info(f"✅ Showed {len(results)} cards for '{character_name}'")
        
    except Exception as e:
        error_logger.error(f"Error showing character cards: {e}", exc_info=True)


# ============================================================
# 📦 Handler Registration
# ============================================================

def register_inline_handlers(application: Application) -> None:
    """
    Register inline query handlers with the application.
    """
    application.add_handler(InlineQueryHandler(inline_query_handler))
    app_logger.info("✅ Inline search handlers registered")


def register_inline_callback_handlers(application: Application) -> None:
    """
    Placeholder for callback handlers (not needed for basic inline).
    """
    pass