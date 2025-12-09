# commands/inline.py
from telegram import InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import InlineQueryHandler
from uuid import uuid4
from db import search_cards_by_text
from commands.utils import rarity_to_text

async def inline_query(update, context):
    pool = context.application.bot_data["pool"]
    q = update.inline_query.query.strip()
    if not q:
        return
    rows = await search_cards_by_text(pool, q)
    results = []
    for r in rows:
        name,_,emoji = rarity_to_text(r.get("rarity",0))
        caption = f"{emoji} {r.get('character')} ({name}) — {r.get('anime')} — ID:{r.get('id')}"
        results.append(
            InlineQueryResultArticle(
                id=str(uuid4()),
                title=f"{r.get('character')} — {r.get('anime')}",
                input_message_content=InputTextMessageContent(caption),
                description=f"{name} — ID {r.get('id')}"
            )
        )
    await update.inline_query.answer(results[:50])

def register_inline_handlers(app):
    app.add_handler(InlineQueryHandler(inline_query))