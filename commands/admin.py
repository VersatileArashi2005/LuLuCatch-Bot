# commands/admin.py
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from db import get_conn

# Update user role using user_id
def set_role(user_id, role):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET role=%s WHERE user_id=%s", (role, user_id))
        conn.commit()

async def adddev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caller = update.effective_user
    bot_owner = int(context.bot.owner_id)

    # Only bot owner can add devs
    if caller.id != bot_owner:
        await update.message.reply_text("❌ Only the bot owner can use this command.")
        return

    # Must reply to a user to promote
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user to promote them to dev.")
        return

    target = update.message.reply_to_message.from_user
    set_role(target.id, "dev")

    await update.message.reply_text(f"✅ {target.first_name} is now a developer.")

async def rmdev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Must reply to remove
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user to remove developer role.")
        return

    target = update.message.reply_to_message.from_user
    set_role(target.id, "user")

    await update.message.reply_text(f"✅ {target.first_name} is now removed from dev role.")

def register_admin_handlers(application):
    application.add_handler(CommandHandler("adddev", adddev))
    application.add_handler(CommandHandler("rmdev", rmdev))
