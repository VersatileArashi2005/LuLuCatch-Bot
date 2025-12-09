# ============================================================
# 📁 File: main.py
# 📍 Location: telegram_card_bot/main.py
# 📝 Description: FastAPI app with Telegram bot integration
# ============================================================

import asyncio
import sys
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    InlineQueryHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    Defaults,
)

from config import Config
from db import db, init_db, get_global_stats, get_user_collection_stats
from utils.logger import (
    app_logger,
    error_logger,
    setup_logging,
    log_startup,
    log_shutdown,
    log_webhook,
)

# ============================================================
# 📦 Import Handlers
# ============================================================

from handlers.upload import (
    upload_conversation_handler,
    quick_upload_handler,
)
from handlers.admin import (
    admin_command_handler,
    broadcast_conversation_handler,
    admin_callback_handler,
    stats_command_handler,
    ban_command_handler,
    unban_command_handler,
    set_bot_start_time,
)
from handlers.catch import (
    catch_command_handler,
    catch_callback_handler,
    force_spawn_handler,
    name_guess_message_handler,
)


# ============================================================
# 🤖 Telegram Bot Application
# ============================================================

bot_app: Optional[Application] = None


async def setup_bot() -> Application:
    """Set up and configure the Telegram bot application."""
    log_startup("Setting up Telegram bot application...")
    
    application = (
        ApplicationBuilder()
        .token(Config.BOT_TOKEN)
        .build()
    )
    
    set_bot_start_time()
    
    # ========================================
    # Define Basic Command Handlers
    # ========================================
    
    async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /start command."""
        user = update.effective_user
        
        db_status = "✅ Connected" if db.is_connected else "⚠️ Offline"
        
        await update.message.reply_text(
            f"🎴 *Welcome to LuLuCatch, {user.first_name}!*\n\n"
            f"I'm a card collection bot. Catch cards when they spawn in groups!\n\n"
            f"📚 *Commands:*\n"
            f"• /start - Show this message\n"
            f"• /info - View bot information\n"
            f"• /harem - View your card collection\n"
            f"• /catch - Catch a spawned card\n\n"
            f"🗄️ Database: {db_status}\n\n"
            f"Add me to a group to start catching cards! 🚀",
            parse_mode="Markdown"
        )
        app_logger.info(f"📨 /start from user {user.id}")
    
    async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /info command."""
        if db.is_connected:
            stats = await get_global_stats(None)
            await update.message.reply_text(
                f"📊 *LuLuCatch Bot Info*\n\n"
                f"👥 Total Users: {stats['total_users']:,}\n"
                f"🎴 Total Cards: {stats['total_cards']:,}\n"
                f"🎯 Total Catches: {stats['total_catches']:,}\n"
                f"💬 Active Groups: {stats['active_groups']:,}\n\n"
                f"🗄️ Database: ✅ Connected\n"
                f"🔧 Version: 1.0.0",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"📊 *LuLuCatch Bot Info*\n\n"
                f"🗄️ Database: ⚠️ Not Connected\n\n"
                f"The bot is running but database is offline.\n"
                f"Some features may be unavailable.",
                parse_mode="Markdown"
            )
    
    async def harem_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /harem command."""
        if not db.is_connected:
            await update.message.reply_text(
                "⚠️ Database is currently offline. Please try again later.",
                parse_mode="Markdown"
            )
            return
        
        user_id = update.effective_user.id
        stats = await get_user_collection_stats(None, user_id)
        
        await update.message.reply_text(
            f"🎴 *Your Collection*\n\n"
            f"📦 Unique Cards: {stats['total_unique']}\n"
            f"🎴 Total Cards: {stats['total_cards']}\n"
            f"🧿 Mythical+: {stats['mythical_plus']}\n"
            f"⚡ Legendary: {stats['legendary_count']}\n\n"
            f"Use inline mode to browse your collection!",
            parse_mode="Markdown"
        )
    
    async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for inline queries."""
        await update.inline_query.answer(
            results=[],
            cache_time=10,
            switch_pm_text="🎴 View your collection",
            switch_pm_parameter="harem"
        )
    
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Global error handler for the bot."""
        error_logger.error(
            f"Exception while handling an update: {context.error}",
            exc_info=context.error
        )
        
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "❌ An error occurred. Please try again later."
                )
            except Exception:
                pass
    
    # ========================================
    # Register Handlers
    # ========================================
    
    # Conversation handlers first
    application.add_handler(upload_conversation_handler)
    application.add_handler(broadcast_conversation_handler)
    
    # Basic commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("info", info_command))
    application.add_handler(CommandHandler("help", start_command))
    application.add_handler(CommandHandler("harem", harem_command))
    
    # Catch commands
    application.add_handler(catch_command_handler)
    application.add_handler(force_spawn_handler)
    
    # Admin commands
    application.add_handler(admin_command_handler)
    application.add_handler(stats_command_handler)
    application.add_handler(ban_command_handler)
    application.add_handler(unban_command_handler)
    application.add_handler(quick_upload_handler)
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(admin_callback_handler, pattern=r"^admin_"))
    application.add_handler(CallbackQueryHandler(catch_callback_handler, pattern=r"^(catch_|skip_|expired)"))
    
    # Message handlers
    application.add_handler(name_guess_message_handler)
    
    # Inline handler
    if Config.ENABLE_INLINE_MODE:
        application.add_handler(InlineQueryHandler(inline_query_handler))
    
    # Error handler
    application.add_error_handler(error_handler)
    
    # Set commands
    commands = [
        BotCommand("start", "🚀 Start the bot"),
        BotCommand("info", "📊 Bot information"),
        BotCommand("catch", "🎯 Catch a card"),
        BotCommand("harem", "🎴 Your collection"),
    ]
    await application.bot.set_my_commands(commands)
    
    log_startup("✅ Bot application configured")
    
    return application


# ============================================================
# 🌐 FastAPI Application
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager."""
    global bot_app
    
    # ========================================
    # 🚀 Startup
    # ========================================
    log_startup("Starting LuLuCatch Bot...")
    
    # Validate configuration
    is_valid, errors = Config.validate()
    if not is_valid:
        for error in errors:
            error_logger.error(error)
        raise RuntimeError("Invalid configuration")
    
    app_logger.info(Config.display_config())
    
    # Try to connect to database (non-blocking)
    db_connected = await db.connect(max_retries=3, retry_delay=2)
    
    if db_connected:
        await init_db()
    else:
        app_logger.warning(
            "⚠️ Bot starting without database connection. "
            "Some features will be unavailable."
        )
    
    # Set up Telegram bot
    bot_app = await setup_bot()
    await bot_app.initialize()
    await bot_app.start()
    
    # Set up webhook or polling
    if Config.WEBHOOK_URL:
        webhook_url = Config.get_full_webhook_url()
        log_webhook(f"Setting webhook: {webhook_url}")
        
        await bot_app.bot.set_webhook(
            url=webhook_url,
            secret_token=Config.WEBHOOK_SECRET,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        log_webhook("✅ Webhook configured")
    else:
        log_startup("Using polling mode")
        asyncio.create_task(bot_app.updater.start_polling(drop_pending_updates=True))
    
    log_startup("🎴 LuLuCatch Bot is running!")
    
    yield
    
    # ========================================
    # 🛑 Shutdown
    # ========================================
    log_shutdown("Shutting down...")
    
    if bot_app:
        if Config.WEBHOOK_URL:
            await bot_app.bot.delete_webhook()
        else:
            await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()
    
    await db.disconnect()
    log_shutdown("✅ Shutdown complete")


app = FastAPI(
    title="LuLuCatch Card Bot",
    description="Telegram Card Collection Bot",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "status": "online",
        "bot": "LuLuCatch",
        "database": "connected" if db.is_connected else "disconnected",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    from db import health_check as db_health
    
    db_ok = await db_health(None) if db.is_connected else False
    
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "bot": "running" if bot_app else "stopped",
    }


@app.post(Config.WEBHOOK_PATH)
async def webhook_handler(request: Request) -> Response:
    """Webhook endpoint."""
    global bot_app
    
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret != Config.WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid token")
    
    if not bot_app:
        raise HTTPException(status_code=503, detail="Bot not ready")
    
    try:
        data = await request.json()
        update = Update.de_json(data, bot_app.bot)
        await bot_app.process_update(update)
        return Response(status_code=200)
    except Exception as e:
        error_logger.error(f"Webhook error: {e}", exc_info=True)
        return Response(status_code=200)


def main():
    """Main entry point."""
    setup_logging(debug=Config.DEBUG)
    log_startup("Initializing LuLuCatch Card Bot...")
    
    uvicorn.run(
        "main:app",
        host=Config.HOST,
        port=Config.PORT,
        reload=Config.DEBUG,
        log_level="info" if Config.DEBUG else "warning",
    )


if __name__ == "__main__":
    main()