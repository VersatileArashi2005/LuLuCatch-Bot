# commands/info.py
from telegram import Update
from telegram.ext import ContextTypes
from db import get_user_by_telegram

async def info_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # reply-based
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user's message with /info to see their info.")
        return
    target = update.message.reply_to_message.from_user
    u = get_user_by_telegram(target.id)
    if not u:
        await update.message.reply_text("No record for that user.")
        return
    await update.message.reply_text(f"👤 {u['first_name']} ({u['telegram_id']})\nRole: {u['role']}\nLast catch: {u.get('last_catch')}")
