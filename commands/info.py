from telegram import Update
from telegram.ext import ContextTypes
from db import get_user_by_id

async def info_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool = context.application.bot_data['pool']

    # reply-based
    if not update.message or not update.message.reply_to_message:
        await update.message.reply_text("❌ Reply to a user's message with /info to see their info.")
        return

    target = update.message.reply_to_message.from_user
    u = await get_user_by_id(pool, target.id)
    if not u:
        await update.message.reply_text("❌ No record for that user.")
        return

    await update.message.reply_text(
        f"👤 {u.get('first_name')} ({u.get('user_id')})\n"
        f"Role: {u.get('role')}\n"
        f"Last catch: {u.get('last_catch')}"
    )