# commands/catch.py
import random
from telegram import Update
from telegram.ext import CommandHandler
from db import get_all_cards, get_user_by_id, get_today_catch, add_card_to_user

COOLDOWN_HOURS = 24

async def catch_cmd(update: Update, context):
    user = update.effective_user
    pool = context.application.bot_data.get("pool")
    if not pool:
        await update.message.reply_text("DB not ready.")
        return

    u = await get_user_by_id(pool, user.id)
    if not u:
        await update.message.reply_text("You are not registered. Use /start first.")
        return

    caught = await get_today_catch(pool, user.id, update=False)
    if caught:
        await update.message.reply_text("⏳ You already caught a card today!")
        return

    all_cards = await get_all_cards(pool)
    if not all_cards:
        await update.message.reply_text("No cards in database yet.")
        return

    card = random.choice(all_cards)
    await add_card_to_user(pool, user.id, card['id'])
    await update.message.reply_text(f"🎉 You caught **{card['character']}** from **{card['anime']}**!", parse_mode="Markdown")

def register_catch_handlers(application):
    application.add_handler(CommandHandler("catch", catch_cmd))