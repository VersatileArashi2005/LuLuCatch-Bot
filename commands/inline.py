from telegram import InlineQueryResultPhoto, InputTextMessageContent, Update
from telegram.ext import ContextTypes, InlineQueryHandler
from uuid import uuid4
from db import get_all_cards, get_user_by_id
from commands.utils import rarity_to_text, format_telegram_name

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.strip().lower()
    all_cards = get_all_cards()  # Returns list of dicts: id, anime, character, rarity, file_id

    results = []
    for card in all_cards:
        # Simple filter: match anime or character
        if query in card["anime"].lower() or query in card["character"].lower() or not query:
            name, pct, emoji = rarity_to_text(card["rarity"])
            caption = (
                f"🎴 {card['character']}\n"
                f"🎬 {card['anime']}\n"
                f"🏷 Rarity: {emoji} {name.capitalize()} ({pct}%)\n"
                f"🆔 ID: {card['id']}"
            )
            results.append(
                InlineQueryResultPhoto(
                    id=str(uuid4()),
                    photo_url=card["file_id"],  # use file_id or URL
                    thumb_url=card["file_id"],
                    caption=caption,
                    parse_mode="Markdown",
                    input_message_content=InputTextMessageContent(caption, parse_mode="Markdown")
                )
            )
        if len(results) >= 50:  # limit for Telegram
            break

    await update.inline_query.answer(results, cache_time=60, is_personal=True)