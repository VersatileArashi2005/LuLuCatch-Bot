from telegram import Update
from telegram.ext import CallbackContext
from db import get_card

def check_card(update: Update, context: CallbackContext):
    card_id = context.args[0]
    card = get_card(card_id)
    if card:
        rarity_emotes = {
            "bronze":"🥉", "silver":"🥈", "rare":"🔹", "epic":"✨", "platinum":"🏆",
            "emerald":"💚", "diamond":"💎", "mythical":"🌟", "legendary":"🦄", "supernatural":"🛸"
        }
        emote = rarity_emotes.get(card['rarity'], "")
        text = f"Name: {card['character']}\nID: {card['id']}\nAnime: {card['anime']}\nRarity: {card['rarity']} {emote}"
        update.message.reply_photo(card['file_id'], caption=text)
