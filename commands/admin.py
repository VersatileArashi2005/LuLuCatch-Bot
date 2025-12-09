# commands/admin.py
from telegram import Update
from telegram.ext import CommandHandler
from db import get_user_by_id, ensure_user, update_user_cards, get_pool
from config import OWNER_ID

# helper set role
async def set_role(pool, target_user_id, role):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET role=$1 WHERE user_id=$2", role, target_user_id)

async def addadmin(update: Update, context):
    caller = update.effective_user
    pool = context.application.bot_data.get("pool")
    if caller.id != OWNER_ID:
        await update.message.reply_text("Only owner can use this.")
        return
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
        target_id = target.id
    elif context.args and context.args[0].isdigit():
        target_id = int(context.args[0])
    else:
        await update.message.reply_text("Reply to a user or provide user ID.")
        return
    await ensure_user(pool, target_id, "User")
    await set_role(pool, target_id, "admin")
    await update.message.reply_text(f"✅ {target_id} is now admin.")

async def adddev(update: Update, context):
    caller = update.effective_user
    pool = context.application.bot_data.get("pool")
    if caller.id != OWNER_ID:
        await update.message.reply_text("Only owner can use this.")
        return
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
        target_id = target.id
    elif context.args and context.args[0].isdigit():
        target_id = int(context.args[0])
    else:
        await update.message.reply_text("Reply to a user or provide user ID.")
        return
    await ensure_user(pool, target_id, "User")
    await set_role(pool, target_id, "dev")
    await update.message.reply_text(f"✅ {target_id} is now dev.")

async def rmdev(update: Update, context):
    pool = context.application.bot_data.get("pool")
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
        target_id = target.id
    elif context.args and context.args[0].isdigit():
        target_id = int(context.args[0])
    else:
        await update.message.reply_text("Reply to a user or provide user ID.")
        return
    await set_role(pool, target_id, "user")
    await update.message.reply_text(f"✅ {target_id} role removed (now user).")

def register_admin_handlers(application):
    application.add_handler(CommandHandler("addadmin", addadmin))
    application.add_handler(CommandHandler("adddev", adddev))
    application.add_handler(CommandHandler("rmdev", rmdev))