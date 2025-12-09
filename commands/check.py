# commands/check.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, InlineQueryHandler
from uuid import uuid4
from db import get_card_by_id, get_user_cards, get_user_by_id, get_all_cards, get_card_owners
from commands.utils import rarity_to_text, format_telegram_name

async def check_cmd(update: Update, context):
    args = context.args
    pool = context.application.bot_data.get("pool")
    if not args or not args[0].isdigit():
        await update.message.reply_text("Please provide card ID. Example: /check 5")
        return
    card_id = int(args[0])
    card = await get_card_by_id(pool, card_id)
    if not card:
        await update.message.reply_text(f"Card with ID {card_id} not found.")
        return
    name, pct, emoji = rarity_to_text(card["rarity"])
    card_info_text = f"🆔 ID: {card['id']}\n🎬 Anime: {card['anime']}\nCharacter: {card['character']}\nRarity: {emoji} {name}"
    if card.get("file_id"):
        await update.message.reply_photo(photo=card["file_id"], caption=card_info_text)
    else:
        await update.message.reply_text(card_info_text)
    owners = await get_card_owners(pool, card_id, limit=5)
    if not owners:
        owners_text = "No one owns this card yet."
    else:
        owners_text = "Top Owners:\n"
        for i, o in enumerate(owners, start=1):
            owners_text += f"Top {i}: {o['first_name']} — {o['quantity']} cards\n"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("How Many I Have", callback_data=f"how_many_{card_id}")]])
    await update.message.reply_text(owners_text, reply_markup=keyboard)

async def how_many_callback(update: Update, context):
    query = update.callback_query
    if not query or not query.data.startswith("how_many_"):
        return
    card_id = int(query.data.split("_")[-1])
    user_id = query.from_user.id
    pool = context.application.bot_data.get("pool")
    user_cards = await get_user_cards(pool, user_id)
    qty = 0
    for uc in user_cards:
        if uc["card_id"] == card_id:
            qty = uc["quantity"]
            break
    await query.answer(f"You have {qty} of this card.", show_alert=True)

async def inline_query_handler(update: Update, context):
    q = update.inline_query.query.lower()
    results = []
    pool = context.application.bot_data.get("pool")
    all_cards = await get_all_cards(pool)
    for card in all_cards:
        if q in card["anime"].lower() or q in card["character"].lower():
            name, pct, emoji = rarity_to_text(card["rarity"])
            caption = f"{emoji} {card['character']} ({name})\n🎬 {card['anime']}\n🆔 ID: {card['id']}"
            # return article if no photo or photo
            from telegram import InlineQueryResultArticle, InputTextMessageContent
            results.append(InlineQueryResultArticle(id=str(uuid4()), title=f"{emoji} {card['character']}", input_message_content=InputTextMessageContent(caption), description=card['anime']))
    await update.inline_query.answer(results[:50])

def register_check_handlers(application):
    application.add_handler(CommandHandler("check", check_cmd))
    application.add_handler(CallbackQueryHandler(how_many_callback, pattern="how_many_"))
    application.add_handler(InlineQueryHandler(inline_query_handler))