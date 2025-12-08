# commands/inline.py

from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ContextTypes
from uuid import uuid4
from db import get_all_cards
from commands.utils import rarity_to_text

# -------------------------
# Inline query handler
# -------------------------
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.inline_query.query.lower()
    results = []

    all_cards = get_all_cards()
    for card in all_cards:
        rarity_name, _, rarity_emoji = rarity_to_text(card.get("rarity", 0))

        # search by anime, character, or rarity name
        if (
            query_text in card['anime'].lower() or
            query_text in card['character'].lower() or
            query_text in rarity_name.lower()
        ):
            caption = (
                f"{rarity_emoji} {card.get('character', 'Unknown')} ({rarity_name})\n"
                f"🎬 Anime: {card.get('anime', 'Unknown Anime')}\n"
                f"🆔 ID: {card.get('id', 0)}"
            )

            # Use InlineQueryResultArticle if file_id / photo missing
            results.append(
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title=f"{rarity_emoji} {card.get('character', 'Unknown')} ({rarity_name})",
                    input_message_content=InputTextMessageContent(caption),
                    description=f"🎬 {card.get('anime', 'Unknown Anime')} — ID: {card.get('id', 0)}"
                )
            )

    # Telegram allows max 50 results
    await update.inline_query.answer(results[:50])