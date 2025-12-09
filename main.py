# main.py
import uvicorn
import traceback
from fastapi import FastAPI, Request

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, InlineQueryHandler, filters

from config import BOT_TOKEN, WEBHOOK_URL, PORT
from db import get_pool, init_db

# Commands registration functions (we implement register_* in each file)
from commands.start import register_start_handlers
from commands.info import register_info_handlers
from commands.check import register_check_handlers
from commands.upload import register_upload_handlers
from commands.admin import register_admin_handlers
from commands.catch import register_catch_handlers
from commands.harem import register_harem_handlers
from commands.inline import register_inline_handlers

from utils.logger import app_logger, error_logger

app = FastAPI()

def log_error(e, where="Unknown"):
    error_logger.error(f"Error in {where}: {e}", exc_info=True)

application = Application.builder().token(BOT_TOKEN).build()

# register handlers into the application
register_start_handlers(application)
register_info_handlers(application)
register_check_handlers(application)
register_upload_handlers(application)
register_admin_handlers(application)
register_catch_handlers(application)
register_harem_handlers(application)
register_inline_handlers(application)

# startup/shutdown lifecycle
@app.on_event("startup")
async def on_startup():
    app_logger.info("Starting up... creating DB pool")
    pool = await get_pool()
    application.bot_data["pool"] = pool
    await init_db(pool)
    await application.initialize()
    if WEBHOOK_URL:
        await application.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    await application.start()
    app_logger.info("Bot started.")

@app.on_event("shutdown")
async def on_shutdown():
    app_logger.info("Shutting down bot...")
    try:
        await application.stop()
        await application.shutdown()
        pool = application.bot_data.get("pool")
        if pool:
            await pool.close()
    except Exception as e:
        log_error(e, "shutdown")

@app.post("/webhook")
async def webhook_receiver(request: Request):
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
    except Exception as e:
        log_error(e, "webhook_receiver")
    return {"ok": True}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)