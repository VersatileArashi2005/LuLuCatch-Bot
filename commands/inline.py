from telegram import Update, InlineQueryResultCachedPhoto
from telegram.ext import ContextTypes
from uuid import uuid4
from db import get_all_cards
from commands.utils import rarity_to_text

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.inline_query.query.lower()
    results = []

    all_cards = get_all_cards()
    for card in all_cards:

        # search by anime or character name
        if query_text in card['anime'].lower() or query_text in card['character'].lower():

            rarity_name, _, rarity_emote = rarity_to_text(card['rarity'])
            caption = (
                f"🆔 ID: {card['id']}\n"
                f"🎬 Anime: {card['anime']}\n"
                f"Character: {card['character']}\n"
                f"Rarity: {rarity_emote} {rarity_name}"
            )

            # IMPORTANT: Use cached photo (file_id)
            if card.get("file_id"):
                results.append(
                    InlineQueryResultCachedPhoto(
                        id=str(uuid4()),
                        photo_file_id=card["file_id"],
                        caption=caption,
                        parse_mode="Markdown"
                    )
                )

    await update.inline_query.answer(results[:50])