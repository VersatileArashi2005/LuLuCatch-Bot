# commands/admin.py
from telegram.ext import CommandHandler
from config import OWNER_ID, DEFAULT_COOLDOWN_HOURS
from db import get_user_by_id
from telegram import Update

async def role_cmd(update: Update, context):
    pool = context.application.bot_data["pool"]
    caller = update.effective_user
    if caller.id != OWNER_ID:
        await update.message.reply_text("Only owner can set roles.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user and use: /role <role>")
        return
    role = context.args[0] if context.args else None
    if not role:
        await update.message.reply_text("Usage: reply to user then /role <owner|dev|admin|uploader|user>")
        return
    target = update.message.reply_to_message.from_user
    await pool.execute("INSERT INTO users (user_id, first_name) VALUES ($1,$2) ON CONFLICT (user_id) DO NOTHING", target.id, target.first_name or target.username or "User")
    await pool.execute("UPDATE users SET role=$1 WHERE user_id=$2", role, target.id)
    await update.message.reply_text(f"{target.first_name} is now {role}.")

async def setcooldown_cmd(update, context):
    caller = update.effective_user
    if caller.id != OWNER_ID:
        await update.message.reply_text("Only owner can change settings.")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /setcooldown <hours>")
        return
    hours = int(context.args[0])
    # store in DB / config; for simplicity we store in memory under bot_data
    update.effective_app.bot_data["cooldown_hours"] = hours
    await update.message.reply_text(f"Cooldown set to {hours} hours.")

async def broadcast_cmd(update, context):
    caller = update.effective_user
    if caller.id != OWNER_ID:
        await update.message.reply_text("Only owner can broadcast.")
        return
    pool = update.effective_app.bot_data["pool"]
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    rows = await pool.fetch("SELECT user_id FROM users")
    for r in rows:
        try:
            await update.effective_app.bot.send_message(chat_id=r["user_id"], text=text)
        except:
            pass
    await update.message.reply_text("Broadcast sent.")

def register_admin_handlers(app):
    app.add_handler(CommandHandler("role", role_cmd))
    app.add_handler(CommandHandler("setcooldown", setcooldown_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))