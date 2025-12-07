from telegram import InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import InlineQueryHandler
from db import search_cards_by_name  # DB မှာ search function သုံးမယ်

async def inline_query(update, context):
    query = update.inline_query.query
    results = []

    if not query:
        return

    # DB မှာ search
    cards = search_cards_by_name(query)  # return list of dicts: id, anime, character, rarity, file_id

    for card in cards[:50]:  # max 50 results
        title = f"{card['character']} ({card['anime']})"
        message_text = (
            f"🆔 ID: {card['id']}\n"
            f"🎬 Anime: {card['anime']}\n"
            f"Character: {card['character']}\n"
            f"Rarity: {card['rarity_emote']} {card['rarity_name']}"
        )

        results.append(
            InlineQueryResultArticle(
                id=str(card['id']),
                title=title,
                input_message_content=InputTextMessageContent(message_text),
            )
        )

    await update.inline_query.answer(results)