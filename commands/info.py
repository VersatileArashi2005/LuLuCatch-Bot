# commands/info.py
from telegram import Update
from telegram.ext import CommandHandler
from db import get_user_by_id

async def info_cmd(update: Update, context):
    pool = context.application.bot_data["pool"]
    if not update.message or not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user's message with /info to see their info.")
        return
    target = update.message.reply_to_message.from_user
    u = await get_user_by_id(pool, target.id)
    if not u:
        await update.message.reply_text("No record for that user.")
        return
    await update.message.reply_text(f"👤 {u.get('first_name')} ({u.get('user_id')})\nRole: {u.get('role')}\nLast catch: {u.get('last_catch')}")

def register_info_handlers(app):
    app.add_handler(CommandHandler("info", info_cmd))