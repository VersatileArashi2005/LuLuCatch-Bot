from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from db import get_user_by_id, ensure_user

# -------------------------
# Async helper: Update role in DB
# -------------------------
async def set_role(pool, target_user_id, role):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET role=$1 WHERE user_id=$2", role, target_user_id)

# -------------------------
# /addadmin - Owner only
# -------------------------
async def addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool = context.application.bot_data['pool']
    caller = update.effective_user
    owner_id = int(context.application.bot.owner_id) if context.application.bot.owner_id else None

    if caller.id != owner_id:
        await update.message.reply_text("❌ Only owner can use this command.")
        return

    # Reply
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
        target_id = target.id
    elif context.args and context.args[0].isdigit():
        target_id = int(context.args[0])
        target = await get_user_by_id(pool, target_id)
        if not target:
            await update.message.reply_text("❌ User not found in DB.")
            return
    else:
        await update.message.reply_text("❌ Reply to a user or provide user ID.")
        return

    await set_role(pool, target_id, "admin")
    await update.message.reply_text(f"✅ {target['first_name'] if target else target_id} is now admin.")

# -------------------------
# /adddev - Owner only
# -------------------------
async def adddev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool = context.application.bot_data['pool']
    caller = update.effective_user
    owner_id = int(context.application.bot.owner_id) if context.application.bot.owner_id else None

    if caller.id != owner_id:
        await update.message.reply_text("❌ Only owner can use this command.")
        return

    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
        target_id = target.id
    elif context.args and context.args[0].isdigit():
        target_id = int(context.args[0])
        target = await get_user_by_id(pool, target_id)
        if not target:
            await update.message.reply_text("❌ User not found in DB.")
            return
    else:
        await update.message.reply_text("❌ Reply to a user or provide user ID.")
        return

    await set_role(pool, target_id, "dev")
    await update.message.reply_text(f"✅ {target['first_name'] if target else target_id} is now dev.")

# -------------------------
# /rmdev - Remove dev role
# -------------------------
async def rmdev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool = context.application.bot_data['pool']
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
        target_id = target.id
    elif context.args and context.args[0].isdigit():
        target_id = int(context.args[0])
        target = await get_user_by_id(pool, target_id)
        if not target:
            await update.message.reply_text("❌ User not found in DB.")
            return
    else:
        await update.message.reply_text("❌ Reply to a user or provide user ID.")
        return

    await set_role(pool, target_id, "user")
    await update.message.reply_text(f"✅ {target['first_name'] if target else target_id} role removed (now user).")

# -------------------------
# Register handlers
# -------------------------
def register_admin_handlers(application):
    application.add_handler(CommandHandler("addadmin", addadmin))
    application.add_handler(CommandHandler("adddev", adddev))
    application.add_handler(CommandHandler("rmdev", rmdev))