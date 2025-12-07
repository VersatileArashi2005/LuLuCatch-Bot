from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from db import get_user_by_id, ensure_user, get_conn

def set_role(target_user_id, role):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET role=%s WHERE user_id=%s", (role, target_user_id))
        conn.commit()

async def adddev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caller = update.effective_user
    owner_id = int(context.bot.owner_id) if context.bot.owner_id else None
    if caller.id != owner_id:
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
