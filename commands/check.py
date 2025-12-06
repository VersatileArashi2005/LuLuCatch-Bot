from telegram import Update
from telegram.ext import ContextTypes
from db import get_card_by_id, get_rarity_info

async def check_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Usage: /check <card_id>")
        return
    card_id = int(args[0])
    card = get_card_by_id(card_id)
    if not card:
        await update.message.reply_text("Card not found!")
        return
    
    rarity_name, rarity_percent, rarity_emoji = get_rarity_info(card['rarity'])
    
    msg = f"🎴 Card Info\n\nName: {card['name']}\nID: {card['id']}\nAnime: {card['anime']}\nRarity: {rarity_name} {rarity_emoji} ({rarity_percent}%)"
    await update.message.reply_text(msg)
