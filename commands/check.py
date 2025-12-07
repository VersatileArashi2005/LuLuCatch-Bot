from telegram import Update
from telegram.ext import ContextTypes
from db import get_card_by_id
from commands.utils import rarity_to_text

async def check_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Usage: /check <card_id>")
        return
    card_id = int(args[0])
    card = get_card_by_id(card_id)
    if not card:
        await update.message.reply_text("Card not found.")
        return
    character = card.get('character') or card.get('name') or "Unknown"
    anime = card.get('anime', 'Unknown')
    rarity_id = card.get('rarity', 0)
    file_id = card.get('file_id')
    rarity_name, percent, emoji = rarity_to_text(rarity_id)
    caption = f"{emoji} {character}\n📌 ID: {card_id}\n🎬 Anime: {anime}\n🏷 Rarity: {rarity_name.capitalize()} ({percent}%)"
    # send photo (works with file_id or URL)
    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=file_id, caption=caption)
