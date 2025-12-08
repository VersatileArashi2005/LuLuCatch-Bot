# commands/inline.py

from telegram import Update, InlineQueryResultPhoto
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
        # rarity info (optional, ကိုသုံးချင်ရင်)
        rarity_name, _, rarity_emoji = rarity_to_text(card.get("rarity", 0))

        # Search by anime or character
        if query_text in card['anime'].lower() or query_text in card['character'].lower():
            # Only include if photo exists
            if card.get("file_id"):
                results.append(
                    InlineQueryResultPhoto(
                        id=str(uuid4()),
                        photo_url=card["file_id"],  # file_id သုံးမယ် Telegram မှာ
                        thumb_url=card["file_id"],  # same as photo
                        # caption optional, မသုံးလည်းရ
                        # caption=f"{rarity_emoji} {card['character']} ({rarity_name})",
                    )
                )

    # Telegram allows max 50 results
    await update.inline_query.answer(results[:50])