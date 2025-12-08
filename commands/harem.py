from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler
from db import get_user_cards, get_cards_by_ids

ITEMS_PER_PAGE = 5

async def harem_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_cards = get_user_cards(user_id)
    if not user_cards:
        await update.message.reply_text("Your harem is empty.")
        return

    await show_harem_page(update, context, user_cards, 0)

async def show_harem_page(update, context, user_cards, page):
    start = page*ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    page_cards = user_cards[start:end]
    card_ids = [uc["card_id"] for uc in page_cards]
    cards = get_cards_by_ids(card_ids)

    media_group = []
    for card in cards:
        media_group.append({
            "type": "photo",
            "media": card["file_id"]
        })

    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Back", callback_data=f"harem_{page-1}"))
    if end < len(user_cards):
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"harem_{page+1}"))

    reply_markup = InlineKeyboardMarkup([buttons]) if buttons else None

    await update.message.reply_media_group(media_group)
    if reply_markup:
        await update.message.reply_text("Navigate your harem:", reply_markup=reply_markup)

async def harem_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    page = int(query.data.split("_")[1])
    user_id = query.from_user.id
    user_cards = get_user_cards(user_id)
    await show_harem_page(query, context, user_cards, page)

def register_harem_handlers(application):
    application.add_handler(CommandHandler("harem", harem_cmd))
    application.add_handler(CallbackQueryHandler(harem_callback, pattern=r"harem_\d+"))