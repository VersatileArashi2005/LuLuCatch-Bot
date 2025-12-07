from telegram import Update
from telegram.ext import ContextTypes
from db import get_user_by_id

async def info_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # reply-based
    if not update.message or not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user's message with /info to see their info.")
        return
    target = update.message.reply_to_message.from_user
    u = get_user_by_id(target.id)
    if not u:
        await update.message.reply_text("No record for that user.")
        return
    await update.message.reply_text(f"👤 {u.get('first_name')} ({u.get('user_id')})\nRole: {u.get('role')}\nLast catch: {u.get('last_catch')}")
