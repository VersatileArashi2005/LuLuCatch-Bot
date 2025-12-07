# commands/check.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from db import get_card_by_id, get_user_cards, get_user_by_id
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

    # Card Info Text
    card_info_text = (
        f"🆔 ID: {card['id']}\n"
        f"🎬 Anime: {card['anime']}\n"
        f"Character: {card['character']}\n"
        f"Rarity: {rarity_emote} {rarity_name}"
    )

    # Send Photo if exists
    if card.get("file_id"):
        await update.message.reply_photo(
            photo=card["file_id"],
            caption=card_info_text
        )
    else:
        await update.message.reply_text(card_info_text)

    # Top Owners
    all_users_cards = get_user_cards(None)  # get all users with any cards
    owners = []
    for uc in all_users_cards:
        if uc["card_id"] == card_id:
            user = get_user_by_id(uc["user_id"])
            if user:
                fullname = user.get("first_name", "")
                owners.append((fullname, uc["quantity"]))

    if not owners:
        owners_text = "No one owns this card yet."
    else:
        owners.sort(key=lambda x: x[1], reverse=True)
        owners_text = "Top Owners:\n"
        for i, (name, qty) in enumerate(owners[:5], start=1):
            owners_text += f"Top {i}: {name} — {qty} cards\n"

    # Button: How many I have
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("How Many I Have", callback_data=f"how_many_{card_id}")]
    ])

    await update.message.reply_text(owners_text, reply_markup=keyboard)
    

# Register handler
def register_check_handlers(application):
    application.add_handler(CommandHandler("check", check_cmd))