# commands/check.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from db import get_card_by_id, get_user_cards, get_user_by_id
from commands.utils import rarity_to_text

# Helper to get Telegram display name
def get_telegram_name(user_id):
    user = get_user_by_id(user_id)
    if user:
        return user.get("first_name", f"User {user_id}")
    return f"User {user_id}"

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

    # Top owners (skip creator/uploader)
    user_cards = get_user_cards(None)  # all user_cards
    owners = []
    for uc in user_cards:
        if uc["card_id"] == card_id and uc["user_id"] != card.get("uploader_user_id"):
            owners.append((uc["user_id"], uc["quantity"]))

    if not owners:
        owners_text = "No one owns this card yet."
    else:
        owners.sort(key=lambda x: x[1], reverse=True)
        owners_text = "Top Owners:\n"
        for i, (user_id, qty) in enumerate(owners[:5], start=1):
            # use mention
            owners_text += f"Top {i}: [{get_telegram_name(user_id)}](tg://user?id={user_id}) — {qty} cards\n"

    # Button: How many I have
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("How Many I Have", callback_data=f"how_many_{card_id}")]
    ])

    await update.message.reply_text(card_info_text + "\n" + owners_text, reply_markup=keyboard, parse_mode="Markdown")

# Callback for "How Many I Have" button
async def how_many_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    if data.startswith("how_many_"):
        card_id = int(data.split("_")[-1])
        user_cards = get_user_cards(user_id)
        qty = 0
        for uc in user_cards:
            if uc["card_id"] == card_id:
                qty = uc["quantity"]
                break
        await query.message.reply_text(f"You own {qty} of this card.")

def register_check_handlers(application):
    application.add_handler(CommandHandler("check", check_cmd))
    application.add_handler(CallbackQueryHandler(how_many_callback, pattern=r"^how_many_"))