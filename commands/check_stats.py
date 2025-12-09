# commands/check.py
from telegram.ext import CommandHandler
from db import get_pool
from db import get_all_cards
from db import get_user_by_id

async def check_cmd(update, context):
    pool = context.application.bot_data["pool"]
    rows = await pool.fetch("SELECT count(*) as c FROM users")
    users = rows[0]['c']
    cards = len(await get_all_cards(pool))
    await update.message.reply_text(f"Users: {users}\nCards: {cards}")

async def stats_cmd(update, context):
    pool = context.application.bot_data["pool"]
    total_users = (await pool.fetchrow("SELECT count(*) as c FROM users"))['c']
    total_cards = (await pool.fetchrow("SELECT count(*) as c FROM cards"))['c']
    await update.message.reply_text(f"Total users: {total_users}\nTotal cards: {total_cards}")

def register_check_handlers(app):
    app.add_handler(CommandHandler("check", check_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))