# commands/inline.py

from telegram import Update, InlineQueryResultPhoto
from telegram.ext import ContextTypes
from uuid import uuid4
from db import get_all_cards  # သင့် db.py မှ get_all_cards function ကိုသုံးမယ်
from commands.utils import rarity_to_text  # rarity_to_text helper function

# -------------------------
# Inline query handler
# -------------------------
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.inline_query.query.lower()
    results = []

    all_cards = get_all_cards()
    for card in all_cards:
        # search by anime or character
        if query_text in card['anime'].lower() or query_text in card['character'].lower():
            rarity_name, _, rarity_emote = rarity_to_text(card['rarity'])
            caption = (
                f"🆔 ID: {card['id']}\n"
                f"🎬 Anime: {card['anime']}\n"
                f"Character: {card['character']}\n"
                f"Rarity: {rarity_emote} {rarity_name}"
            )
            if card.get("file_id"):
                results.append(
                    InlineQueryResultPhoto(
                        id=str(uuid4()),
                        photo_url=card["file_id"],
                        thumb_url=card["file_id"],
                        caption=caption,
                        parse_mode="Markdown"
                    )
                )

    # Telegram allows max 50 results
    await update.inline_query.answer(results[:50])
