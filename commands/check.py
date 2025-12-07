from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from db import get_card_by_id, get_top_owners, get_user_card_count

# -------------------------
# /check command handler
# -------------------------
async def check_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /check <card_id>")
        return

    try:
        card_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Card ID must be a number.")
        return

    card = get_card_by_id(card_id)
    if not card:
        await update.message.reply_text(f"No card found with ID {card_id}.")
        return

    # Top 5 owners
    top_users = get_top_owners(card_id)
    top_text = ""
    for i, owner in enumerate(top_users, start=1):
        top_text += f"Top {i}: User {owner['user_id']} — {owner['total']} cards\n"

    # Message text
    msg_text = (
        f"**Card Info:**\n"
        f"ID: {card['id']}\n"
        f"Anime: {card['anime']}\n"
        f"Character: {card['character']}\n"
        f"Rarity: {card['rarity']}\n\n"
        f"**Top Owners:**\n{top_text}"
    )

    # Inline button
    keyboard = [
        [InlineKeyboardButton("How Many I Have", callback_data=f"mycount_{card_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send message with card photo + caption
    if card.get("file_id"):
        await update.message.reply_photo(
            photo=card["file_id"],
            caption=msg_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(msg_text, parse_mode="Markdown", reply_markup=reply_markup)


# -------------------------
# Button handler
# -------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # acknowledge button press

    data = query.data
    if data.startswith("mycount_"):
        card_id = int(data.split("_")[1])
        user_id = query.from_user.id
        qty = get_user_card_count(user_id, card_id)
        await query.answer(f"You have {qty} of this card.", show_alert=True)


# -------------------------
# Register handlers
# -------------------------
def register_check_handlers(application):
    application.add_handler(CommandHandler("check", check_cmd))
    application.add_handler(CallbackQueryHandler(button_handler))