# commands/harem.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler
from db import get_user_cards, get_cards_by_ids, get_user_by_id

ITEMS_PER_PAGE = 5

async def inventory_cmd(update, context):
    pool = context.application.bot_data["pool"]
    user = update.effective_user
    uc = await get_user_cards(pool, user.id)
    if not uc:
        await update.message.reply_text("Your inventory is empty.")
        return
    await show_page(update, context, uc, 0)

async def show_page(update, context, user_cards, page):
    pool = context.application.bot_data["pool"]
    start = page*ITEMS_PER_PAGE
    page_items = user_cards[start:start+ITEMS_PER_PAGE]
    ids = [c["card_id"] for c in page_items]
    cards = await get_cards_by_ids(pool, ids)
    msg = ""
    for c, info in zip(cards, page_items):
        msg += f"{c['id']}. {c['character']} — {c['anime']} (x{info['quantity']})\n"
    buttons = []
    if page>0:
        buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"harem_{page-1}"))
    if start+ITEMS_PER_PAGE < len(user_cards):
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"harem_{page+1}"))
    reply_markup = InlineKeyboardMarkup([buttons]) if buttons else None

    # If called from callback_query, edit; else send new
    if update.callback_query:
        await update.callback_query.edit_message_text(msg, reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg, reply_markup=reply_markup)

async def harem_callback(update, context):
    query = update.callback_query
    page = int(query.data.split("_")[1])
    pool = context.application.bot_data["pool"]
    user_cards = await get_user_cards(pool, query.from_user.id)
    await show_page(update, context, user_cards, page)

def register_harem_handlers(app):
    app.add_handler(CommandHandler("inventory", inventory_cmd))
    app.add_handler(CallbackQueryHandler(harem_callback, pattern=r"^harem_\d+$"))