import random
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from db import get_user_by_id, get_all_cards, get_user_cards, update_user_cards, update_last_catch

COOLDOWN_HOURS = 24

async def catch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user_by_id(user_id)
    if not user:
        await update.message.reply_text("You are not registered.")
        return

    import datetime
    now = datetime.datetime.now()
    last = user.get("last_catch")
    if last and (now - last).total_seconds() < COOLDOWN_HOURS*3600:
        await update.message.reply_text("⏳ You already caught a card today!")
        return

    all_cards = get_all_cards()
    card = random.choice(all_cards)

    user_cards = get_user_cards(user_id)
    existing = next((uc for uc in user_cards if uc["card_id"] == card["id"]), None)
    if existing:
        update_user_cards(user_id, card["id"], existing["quantity"]+1)
    else:
        update_user_cards(user_id, card["id"], 1)

    update_last_catch(user_id, now)

    await update.message.reply_text(f"🎉 You caught **{card['character']}** from **{card['anime']}**!", parse_mode="Markdown")

def register_catch_handlers(application):
    application.add_handler(CommandHandler("catch", catch_cmd))