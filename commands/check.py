# commands/check.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from db import get_card_by_id, get_user_cards, get_user_by_id
from commands.utils import rarity_to_text, format_telegram_name

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

    # Top owners
    all_users_cards = get_user_cards(None)  # get all users with any cards
    owners = []
    for uc in all_users_cards:
        if uc["card_id"] == card_id:
            user = get_user_by_id(uc["user_id"])
            if user:
                name = format_telegram_name(user)
                mention = f"[{name}](tg://user?id={uc['user_id']})"
                owners.append((mention, uc["quantity"]))

    if not owners:
        owners_text = "No one owns this card yet."
    else:
        owners.sort(key=lambda x: x[1], reverse=True)
        owners_text = "Top Owners:\n"
        for i, (mention, qty) in enumerate(owners[:5], start=1):
            owners_text += f"Top {i}: {mention} — {qty} cards\n"

    # Button: How many I have
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("How Many I Have", callback_data=f"how_many_{card_id}")]
    ])

    await update.message.reply_text(owners_text, reply_markup=keyboard, parse_mode="Markdown")

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