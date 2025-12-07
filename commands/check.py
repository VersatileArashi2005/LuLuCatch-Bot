# check.py
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from db import get_card

RARITY_EMOTE = {
    1: "🥉",
    2: "🥈",
    3: "🔹",
    4: "💥",
    5: "💎",
    6: "💚",
    7: "💎",
    8: "🌟",
    9: "🏆",
    10: "👑",
}

def check_card(update: Update, context: CallbackContext):
    if len(context.args) != 1:
        update.message.reply_text("Usage: /check <card_id>")
        return
    card_id = int(context.args[0])
    card = get_card(card_id)
    if not card:
        update.message.reply_text("Card not found!")
        return
    # card fields: id, name, anime, character, rarity
    text = f"Name: {card[1]}\nID: {card[0]}\nAnime: {card[2]}\nCharacter: {card[3]}\nRarity: {RARITY_EMOTE[card[4]]}"
    update.message.reply_photo(photo="https://via.placeholder.com/200", caption=text)
