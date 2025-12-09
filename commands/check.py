# commands/check.py (cardinfo)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler
from db import get_card_by_id, get_card_owners, get_pool

async def check_cmd(update, context):
    pool = context.application.bot_data["pool"]
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /cardinfo <id>")
        return
    cid = int(args[0])
    card = await get_card_by_id(pool, cid)
    if not card:
        await update.message.reply_text("Card not found.")
        return
    name = f"{card['character']} ({card['anime']})"
    text = f"🆔 {card['id']}\n🎬 {card['anime']}\n👤 {card['character']}\nRarity: {card['rarity']}"
    if card.get("file_id"):
        await update.message.reply_photo(card['file_id'], caption=text)
    else:
        await update.message.reply_text(text)

async def owners_callback(update, context):
    # example callback to show owners (if button attached)
    pool = context.application.bot_data["pool"]
    cid = int(update.callback_query.data.split("_")[1])
    owners = await get_card_owners(pool, cid)
    if not owners:
        await update.callback_query.answer("No owners yet", show_alert=True)
        return
    msg = "Top owners:\n"
    for o in owners:
        msg += f"{o['first_name']} — {o['quantity']}\n"
    await update.callback_query.answer(msg, show_alert=True)

def register_check_handlers(app):
    app.add_handler(CommandHandler("cardinfo", check_cmd))
    app.add_handler(CallbackQueryHandler(owners_callback, pattern=r"^owners_\d+$"))