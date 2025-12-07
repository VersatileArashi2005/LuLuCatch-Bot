# commands/check.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from db import get_card_by_id, get_user_cards, get_user_by_id
from commands.utils import rarity_to_text

# /check command
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
    user_cards_all = get_user_cards(None)  # get all users with this card
    owners = []
    for uc in user_cards_all:
        if uc["card_id"] == card_id:
            owners.append((uc["user_id"], uc["quantity"]))

    if not owners:
        owners_text = "No one owns this card yet."
    else:
        # sort by quantity descending
        owners.sort(key=lambda x: x[1], reverse=True)
        owners_text = "Top Owners:\n"
        for i, (user_id, qty) in enumerate(owners[:5], start=1):
            user = get_user_by_id(user_id)
            if user:
                name = user.get("first_name", str(user_id))
            else:
                name = str(user_id)
            owners_text += f"Top {i}: {name} — {qty} cards\n"

    # Button: How many I have
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("How Many I Have", callback_data=f"how_many_{card_id}")]
    ])

    await update.message.reply_text(
        card_info_text + "\n" + owners_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# Callback query handler for "How Many I Have" button
async def how_many_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data.startswith("how_many_"):
        return

    card_id = int(query.data.split("_")[-1])
    user_id = query.from_user.id

    user_cards = get_user_cards(user_id)
    qty = 0
    for uc in user_cards:
        if uc["card_id"] == card_id:
            qty = uc["quantity"]
            break

    await query.answer(f"You have {qty} of this card.", show_alert=True)

# Register handlers
def register_check_handlers(application):
    application.add_handler(CommandHandler("check", check_cmd))
    application.add_handler(CallbackQueryHandler(how_many_callback, pattern="how_many_"))