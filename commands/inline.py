from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ContextTypes
from uuid import uuid4
from db import get_all_cards
from commands.utils import rarity_to_text

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool = context.application.bot_data['pool']
    query_text = update.inline_query.query.lower()
    results = []

    all_cards = await get_all_cards(pool)  # async version
    for card in all_cards:
        rarity_name, _, rarity_emoji = rarity_to_text(card.get("rarity", 0))

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

            results.append(
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title=f"{rarity_emoji} {card.get('character', 'Unknown')} ({rarity_name})",
                    input_message_content=InputTextMessageContent(caption),
                    description=f"🎬 {card.get('anime', 'Unknown Anime')} — ID: {card.get('id', 0)}"
                )
            )

    await update.inline_query.answer(results[:50])