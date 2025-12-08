import random
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from db import get_user_by_id, get_all_cards, get_today_catch, add_card_to_user

async def catch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Check user registration
    user = get_user_by_id(user_id)
    if not user:
        await update.message.reply_text("You are not registered.")
        return

    # Check cooldown
    already_caught = get_today_catch(user_id, update=False)
    if already_caught:
        await update.message.reply_text("⏳ You already caught a card today!")
        return

    # Pick a random card
    all_cards = get_all_cards()
    if not all_cards:
        await update.message.reply_text("❌ No cards available in the database.")
        return

    card = random.choice(all_cards)

    # Give card + update today's catch
    add_card_to_user(user_id, card["id"])

    # Reply
    await update.message.reply_text(
        f"🎉 You caught **{card['character']}** from **{card['anime']}**!",
        parse_mode="Markdown"
    )

def register_catch_handlers(application):
    application.add_handler(CommandHandler("catch", catch_cmd))