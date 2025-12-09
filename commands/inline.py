# commands/inline.py
from telegram.ext import InlineQueryHandler
from telegram import InlineQueryResultArticle, InputTextMessageContent
from uuid import uuid4
from commands.utils import rarity_to_text
from db import get_all_cards

async def inline_query(update, context):
    q = update.inline_query.query.lower()
    results = []
    pool = context.application.bot_data.get("pool")
    all_cards = await get_all_cards(pool)
    for card in all_cards:
        name, pct, emoji = rarity_to_text(card["rarity"])
        if q in card['anime'].lower() or q in card['character'].lower() or q in name.lower():
            caption = f"{emoji} {card['character']} ({name})\n🎬 {card['anime']}\nID: {card['id']}"
            results.append(InlineQueryResultArticle(id=str(uuid4()), title=f"{emoji} {card['character']}", input_message_content=InputTextMessageContent(caption), description=card['anime']))
    await update.inline_query.answer(results[:50])

def register_inline_handlers(application):
    application.add_handler(InlineQueryHandler(inline_query))