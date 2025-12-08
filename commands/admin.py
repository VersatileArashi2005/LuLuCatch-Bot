# commands/admin.py

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from db import get_user_by_id, ensure_user, get_conn

# -------------------------
# Helper: Update role in DB
# -------------------------
def set_role(target_user_id, role):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET role=%s WHERE user_id=%s", (role, target_user_id))
        conn.commit()

# -------------------------
# /addadmin - Owner only
# -------------------------
async def addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caller = update.effective_user
    owner_id = int(context.bot.owner_id) if context.bot.owner_id else None

    if caller.id != owner_id:
        await update.message.reply_text("❌ Only owner can use this command.")
        return

    # Reply ကိုစစ်
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
        target_id = target.id
    # ID argument ကိုစစ်
    elif context.args and context.args[0].isdigit():
        target_id = int(context.args[0])
        target = get_user_by_id(target_id)
        if not target:
            await update.message.reply_text("❌ User not found in DB.")
            return
    else:
        await update.message.reply_text("❌ Reply to a user or provide user ID.")
        return

    set_role(target_id, "admin")
    await update.message.reply_text(f"✅ {target.first_name if target else target_id} is now admin.")

# -------------------------
# /adddev - Owner only
# -------------------------
async def adddev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caller = update.effective_user
    owner_id = int(context.bot.owner_id) if context.bot.owner_id else None

    if caller.id != owner_id:
        await update.message.reply_text("❌ Only owner can use this command.")
        return

    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
        target_id = target.id
    elif context.args and context.args[0].isdigit():
        target_id = int(context.args[0])
        target = get_user_by_id(target_id)
        if not target:
            await update.message.reply_text("❌ User not found in DB.")
            return
    else:
        await update.message.reply_text("❌ Reply to a user or provide user ID.")
        return

    set_role(target_id, "dev")
    await update.message.reply_text(f"✅ {target.first_name if target else target_id} is now dev.")

# -------------------------
# /rmdev - Remove dev role
# -------------------------
async def rmdev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
        target_id = target.id
    elif context.args and context.args[0].isdigit():
        target_id = int(context.args[0])
        target = get_user_by_id(target_id)
        if not target:
            await update.message.reply_text("❌ User not found in DB.")
            return
    else:
        await update.message.reply_text("❌ Reply to a user or provide user ID.")
        return

    set_role(target_id, "user")
    await update.message.reply_text(f"✅ {target.first_name if target else target_id} role removed (now user).")

# -------------------------
# Register handlers
# -------------------------
def register_admin_handlers(application):
    application.add_handler(CommandHandler("addadmin", addadmin))
    application.add_handler(CommandHandler("adddev", adddev))
    application.add_handler(CommandHandler("rmdev", rmdev))