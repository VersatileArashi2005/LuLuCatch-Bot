# commands/admin.py
from telegram import Update
from telegram.ext import ContextTypes
from db import get_user_by_telegram, ensure_user, get_conn
import psycopg2

def set_role(target_telegram_id, role):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET role=%s WHERE telegram_id=%s", (role, target_telegram_id))
        conn.commit()

async def adddev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # reply-based: reply to user to promote
    caller = update.effective_user
    if caller.id != int(context.bot.owner_id) and caller.id != int(context.bot.owner_id):  # quick owner check; you can modify
        # Better: check caller's role via database
        await update.message.reply_text("Only owner can use this (or you must be admin in DB).")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user to promote them to dev.")
        return
    target = update.message.reply_to_message.from_user
    set_role(target.id, "dev")
    await update.message.reply_text(f"✅ {target.first_name} is now dev.")

async def rmdev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user to remove dev role.")
        return
    target = update.message.reply_to_message.from_user
    set_role(target.id, "user")
    await update.message.reply_text(f"✅ {target.first_name} role removed (now user).")

def register_admin_handlers(application):
    application.add_handler(CommandHandler("adddev", adddev))
    application.add_handler(CommandHandler("rmdev", rmdev))
