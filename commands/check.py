# commands/check.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultPhoto
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, InlineQueryHandler
from uuid import uuid4
from db import get_card_by_id, get_card_owners, get_user_cards, get_all_cards
from commands.utils import rarity_to_text, format_telegram_name

# -------------------------
# /check command
# -------------------------
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

    rarity_name, _, rarity_emote = rarity_to_text(card["rarity"])
    card_info_text = (
        f"🆔 ID: {card['id']}\n"
        f"🎬 Anime: {card['anime']}\n"
        f"Character: {card['character']}\n"
        f"Rarity: {rarity_emote} {rarity_name}"
    )

    # Send photo if exists
    if card.get("file_id"):
        await update.message.reply_photo(photo=card["file_id"], caption=card_info_text)
    else:
        await update.message.reply_text(card_info_text)

    # Top owners (optimized DB query)
    owners = get_card_owners(card_id)
    if not owners:
        owners_text = "No one owns this card yet."
    else:
        owners_text = "Top Owners:\n"
        for i, owner in enumerate(owners, start=1):
            fullname = format_telegram_name(owner)
            owners_text += f"Top {i}: {fullname} — {owner['quantity']} cards\n"

    # Button: How many I have
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("How Many I Have", callback_data=f"how_many_{card_id}")]
    ])

    await update.message.reply_text(owners_text, reply_markup=keyboard)

# -------------------------
# Callback query for "How Many I Have"
# -------------------------
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

# -------------------------
# Inline Query Handler
# -------------------------
async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.lower()
    results = []

    all_cards = get_all_cards()  # DB function to return all cards
    for card in all_cards:
        if query in card["anime"].lower() or query in card["character"].lower():
            rarity_name, _, rarity_emote = rarity_to_text(card["rarity"])
            caption = (
                f"🆔 ID: {card['id']}\n"
                f"🎬 Anime: {card['anime']}\n"
                f"Character: {card['character']}\n"
                f"Rarity: {rarity_emote} {rarity_name}"
            )
            if card.get("file_id"):
                results.append(
                    InlineQueryResultPhoto(
                        id=str(uuid4()),
                        photo_url=card["file_id"],  # works with Telegram file_id
                        thumb_url=card["file_id"],
                        caption=caption,
                        parse_mode="Markdown"
                    )
                )

    await update.inline_query.answer(results[:50])  # max 50 results

# -------------------------
# Register handlers
# -------------------------
def register_check_handlers(application):
    application.add_handler(CommandHandler("check", check_cmd))
    application.add_handler(CallbackQueryHandler(how_many_callback, pattern="how_many_"))
    application.add_handler(InlineQueryHandler(inline_query_handler))