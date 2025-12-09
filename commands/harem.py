# commands/harem.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler
from db import get_user_cards, get_cards_by_ids
from commands.utils import rarity_to_text

ITEMS_PER_PAGE = 5

async def harem_cmd(update: Update, context):
    user = update.effective_user
    pool = context.application.bot_data.get("pool")
    user_cards = await get_user_cards(pool, user.id)
    if not user_cards:
        await update.message.reply_text("Your harem is empty.")
        return
    await show_harem_page(update, context, user_cards, 0)

async def show_harem_page(update, context, user_cards, page):
    pool = context.application.bot_data.get("pool")
    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    page_cards = user_cards[start:end]
    ids = [uc["card_id"] for uc in page_cards]
    cards = await get_cards_by_ids(pool, ids)
    # send media group
    media = []
    # Use single messages: photo + caption then buttons
    for c, uc in zip(cards, page_cards):
        name, pct, emoji = rarity_to_text(c['rarity'])
        caption = f"{emoji} {c['character']} — {name}\n🎬 {c['anime']}\nQty: {uc['quantity']}\nID: {c['id']}"
        await update.message.reply_photo(photo=c['file_id'], caption=caption)
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Back", callback_data=f"harem_{page-1}"))
    if end < len(user_cards):
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"harem_{page+1}"))
    if buttons:
        await update.message.reply_text("Navigate:", reply_markup=InlineKeyboardMarkup([buttons]))

async def harem_callback(update: Update, context):
    query = update.callback_query
    page = int(query.data.split("_")[1])
    pool = context.application.bot_data.get("pool")
    user_id = query.from_user.id
    user_cards = await get_user_cards(pool, user_id)
    await show_harem_page(query, context, user_cards, page)

def register_harem_handlers(application):
    application.add_handler(CommandHandler("harem", harem_cmd))
    application.add_handler(CallbackQueryHandler(harem_callback, pattern=r"harem_\d+"))