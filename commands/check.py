# commands/check.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
from db import get_card_by_id, get_user_cards
from commands.utils import rarity_to_text

async def check_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Please provide card ID. Example: /check 5")
        return

    card_id = int(args[0])
    card = get_card_by_id(card_id)
    if not card:
        await update.message.reply_text(f"Card with ID {card_id} not found.")
        return

    # Rarity text + emote
    rarity_name, _, rarity_emote = rarity_to_text(card["rarity"])

    card_info_text = (
        f"Card Info:\n"
        f"🆔 : {card['id']}\n"
        f"🎬 Anime : {card['anime']}\n"
        f"Character : {card['character']}\n"
        f"Rarity : {rarity_emote} {rarity_name}\n"
    )

    # Top owners
    user_cards = get_user_cards(None)  # get all users with this card
    owners = []
    for uc in user_cards:
        if uc["card_id"] == card_id:
            owners.append((uc["user_id"], uc["quantity"]))

    if not owners:
        owners_text = "No one owns this card yet."
    else:
        # sort by quantity descending
        owners.sort(key=lambda x: x[1], reverse=True)
        owners_text = "Top Owners:\n"
        for i, (user_id, qty) in enumerate(owners[:5], start=1):
            owners_text += f"Top {i}: [{user_id}](tg://user?id={user_id}) — {qty} cards\n"

    # Button: How many I have
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("How Many I Have", callback_data=f"how_many_{card_id}")]
    ])

    await update.message.reply_text(card_info_text + "\n" + owners_text, reply_markup=keyboard, parse_mode="Markdown")