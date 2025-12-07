# commands/inline.py
from telegram import InlineQueryResultPhoto, InlineQueryResultArticle, InputTextMessageContent, Update
from telegram.ext import ContextTypes, InlineQueryHandler
from commands.utils import format_card_for_inline
from db import search_cards_by_text  # DB function to search cards by anime/character

import uuid

# -------------------------
# Inline Query Handler
# -------------------------
async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.strip()
    results = []

    if not query:
        return  # Empty query, don't return anything

    # Search DB for matching cards (anime/character)
    cards = search_cards_by_text(query)  # Should return list of card dicts

    for card in cards[:50]:  # Telegram allows max 50 results
        formatted = format_card_for_inline(card)
        if not formatted or not formatted.get("photo_file_id"):
            continue

        results.append(
            InlineQueryResultPhoto(
                id=str(uuid.uuid4()),
                photo_file_id=formatted["photo_file_id"],
                thumb_url=formatted["photo_file_id"],
                title=formatted["title"],
                description=formatted["description"],
                caption=f"{formatted['title']}\n{formatted['description']}"
            )
        )

    await update.inline_query.answer(results, cache_time=10, is_personal=True)

# -------------------------
# Register Inline Handler
# -------------------------
def register_inline_handler(application):
    application.add_handler(InlineQueryHandler(inline_query_handler))