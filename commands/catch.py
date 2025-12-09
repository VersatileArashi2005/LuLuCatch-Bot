# commands/catch.py
import random
from telegram import Update
from telegram.ext import CommandHandler
from commands.utils import rarity_to_text
from db import get_all_cards, give_card_to_user, get_today_catch, update_last_catch, ensure_user, get_user_by_id

from config import DEFAULT_COOLDOWN_HOURS

async def lulucatch_cmd(update: Update, context):
    pool = context.application.bot_data["pool"]
    user = update.effective_user
    await ensure_user(pool, user.id, user.first_name or user.username or "User")
    u = await get_user_by_id(pool, user.id)

    # cooldown
    has = await get_today_catch(pool, user.id, update=False)
    if has:
        await update.message.reply_text("⏳ You already caught a card today! Come back tomorrow.")
        return

    cards = await get_all_cards(pool)
    if not cards:
        await update.message.reply_text("❌ No cards available yet.")
        return

    card = random.choice(cards)
    await give_card_to_user(pool, user.id, card['id'], qty=1)
    await update_last_catch(pool, user.id, __import__("datetime").datetime.utcnow())

    name,pct,emoji = rarity_to_text(card.get("rarity", 0))
    text = f"🎉 **Drop!**\nYou caught: {emoji} **{card['character']}**\n🎬 {card['anime']}\n🏷 {name} (ID: {card['id']})"
    # Inline actions (View / Add are implicit because add already happened)
    await update.message.reply_markdown(text)

def register_catch_handlers(application):
    application.add_handler(CommandHandler("lulucatch", lulucatch_cmd))