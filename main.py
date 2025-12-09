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

# Global bot application instance
bot_app: Optional[Application] = None


async def setup_bot() -> Application:
    """
    Set up and configure the Telegram bot application.
    
    Returns:
        Configured Application instance
    """
    log_startup("Setting up Telegram bot application...")
    
    # Build the application with token
    application = (
        ApplicationBuilder()
        .token(Config.BOT_TOKEN)
        .build()
    )
    
    # Set bot start time for uptime tracking
    set_bot_start_time()
    
    # ========================================
    # Define Basic Command Handlers
    # ========================================
    
    async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /start command."""
        user = update.effective_user
        await update.message.reply_text(
            f"🎴 *Welcome to LuLuCatch, {user.first_name}!*\n\n"
            f"I'm a card collection bot. Catch cards when they spawn in groups!\n\n"
            f"📚 *Commands:*\n"
            f"• /start - Show this message\n"
            f"• /info - View bot information\n"
            f"• /harem - View your card collection\n"
            f"• /check [id] - Check card details\n"
            f"• /catch - Catch a spawned card\n\n"
            f"Add me to a group to start catching cards! 🚀",
            parse_mode="Markdown"
        )
        app_logger.info(f"📨 /start from user {user.id}")
    
    async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /info command."""
        stats = await get_global_stats(None)
        
        await update.message.reply_text(
            f"📊 *LuLuCatch Bot Info*\n\n"
            f"👥 Total Users: {stats['total_users']:,}\n"
            f"🎴 Total Cards: {stats['total_cards']:,}\n"
            f"🎯 Total Catches: {stats['total_catches']:,}\n"
            f"💬 Active Groups: {stats['active_groups']:,}\n\n"
            f"🔧 Version: 1.0.0",
            parse_mode="Markdown"
        )
    
    async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /check command - placeholder."""
        await update.message.reply_text(
            "🔍 *Check Command*\n\n"
            "Usage: `/check <card_id>`\n"
            "View details about a specific card.",
            parse_mode="Markdown"
        )
    
    async def harem_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /harem command - placeholder."""
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
        """Handler for inline queries - placeholder."""
        query = update.inline_query.query
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
                    "❌ An error occurred while processing your request. "
                    "Please try again later."
                )
            except Exception:
                pass
    
    # ========================================
    # Register Conversation Handlers (MUST BE FIRST)
    # ========================================
    
    application.add_handler(upload_conversation_handler)
    application.add_handler(broadcast_conversation_handler)
    
    # ========================================
    # Register Command Handlers
    # ========================================
    
    # Basic commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("info", info_command))
    application.add_handler(CommandHandler("help", start_command))
    application.add_handler(CommandHandler("check", check_command))
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
    
    # ========================================
    # Register Callback Query Handlers
    # ========================================
    
    application.add_handler(CallbackQueryHandler(
        admin_callback_handler,
        pattern=r"^admin_"
    ))
    
    application.add_handler(CallbackQueryHandler(
        catch_callback_handler,
        pattern=r"^(catch_|skip_|expired)"
    ))
    
    # ========================================
    # Register Message Handlers
    # ========================================
    
    application.add_handler(name_guess_message_handler)
    
    # ========================================
    # Inline Query Handler
    # ========================================
    
    if Config.ENABLE_INLINE_MODE:
        application.add_handler(InlineQueryHandler(inline_query_handler))
    
    # ========================================
    # Error Handler
    # ========================================
    
    application.add_error_handler(error_handler)
    
    # ========================================
    # Set Bot Commands Menu
    # ========================================
    
    commands = [
        BotCommand("start", "🚀 Start the bot"),
        BotCommand("info", "📊 Bot information"),
        BotCommand("catch", "🎯 Catch a card"),
        BotCommand("harem", "🎴 View your collection"),
        BotCommand("check", "🔍 Check card details"),
    ]
    
    await application.bot.set_my_commands(commands)
    
    log_startup("✅ Bot application configured with all handlers")
    
    return application


# ============================================================
# 🌐 FastAPI Application
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.
    Handles startup and shutdown events.
    """
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
        raise RuntimeError("Invalid configuration. Check the errors above.")
    
    # Display configuration
    app_logger.info(Config.display_config())
    
    # Connect to database
    await db.connect()
    await init_db()
    
    # Set up Telegram bot
    bot_app = await setup_bot()
    
    # Initialize the bot application
    await bot_app.initialize()
    await bot_app.start()
    
    # Set up webhook if URL is configured
    if Config.WEBHOOK_URL:
        webhook_url = Config.get_full_webhook_url()
        log_webhook(f"Setting webhook: {webhook_url}")
        
        await bot_app.bot.set_webhook(
            url=webhook_url,
            secret_token=Config.WEBHOOK_SECRET,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        log_webhook("✅ Webhook configured successfully")
    else:
        # Use polling mode (for local development)
        log_startup("⚠️ No webhook URL configured, using polling mode")
        asyncio.create_task(bot_app.updater.start_polling(drop_pending_updates=True))
    
    log_startup("🎴 LuLuCatch Bot is now running!")
    
    yield  # Application is running
    
    # ========================================
    # 🛑 Shutdown
    # ========================================
    log_shutdown("Shutting down LuLuCatch Bot...")
    
    if bot_app:
        if Config.WEBHOOK_URL:
            await bot_app.bot.delete_webhook()
        else:
            await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()
    
    await db.disconnect()
    
    log_shutdown("✅ LuLuCatch Bot shutdown complete")


# Create FastAPI app with lifespan
app = FastAPI(
    title="LuLuCatch Card Bot",
    description="Telegram Card Collection Bot API",
    version="1.0.0",
    lifespan=lifespan,
)


# ============================================================
# 📡 API Endpoints
# ============================================================

@app.get("/")
async def root():
    """Root endpoint - basic health check."""
    return {
        "status": "online",
        "bot": "LuLuCatch",
        "version": "1.0.0",
        "message": "🎴 Card collection bot is running!"
    }


@app.get("/health")
async def health_check():
    """Detailed health check endpoint."""
    from db import health_check as db_health_check
    
    db_status = await db_health_check(None)
    
    return {
        "status": "healthy" if db_status else "unhealthy",
        "database": "connected" if db_status else "disconnected",
        "bot": "running" if bot_app else "stopped",
    }


@app.post(Config.WEBHOOK_PATH)
async def webhook_handler(request: Request) -> Response:
    """
    Webhook endpoint for receiving Telegram updates.
    """
    global bot_app
    
    # Verify the webhook secret token
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    
    if secret_token != Config.WEBHOOK_SECRET:
        error_logger.warning(f"Invalid webhook secret token received")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid secret token"
        )
    
    if bot_app is None:
        error_logger.error("Bot application not initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bot not ready"
        )
    
    try:
        update_data = await request.json()
        update = Update.de_json(update_data, bot_app.bot)
        await bot_app.process_update(update)
        return Response(status_code=status.HTTP_200_OK)
        
    except Exception as e:
        error_logger.error(f"Error processing webhook update: {e}", exc_info=True)
        return Response(status_code=status.HTTP_200_OK)


@app.get("/stats")
async def get_stats():
    """Get bot statistics (public endpoint)."""
    stats = await get_global_stats(None)
    
    return {
        "users": stats["total_users"],
        "cards": stats["total_cards"],
        "catches": stats["total_catches"],
        "groups": stats["active_groups"],
    }


# ============================================================
# 🚀 Application Entry Point
# ============================================================

def main():
    """
    Main entry point for running the application.
    """
    setup_logging(debug=Config.DEBUG)
    
    log_startup("Initializing LuLuCatch Card Bot...")
    
    uvicorn.run(
        "main:app",
        host=Config.HOST,
        port=Config.PORT,
        reload=Config.DEBUG,
        log_level="info" if Config.DEBUG else "warning",
        access_log=Config.DEBUG,
    )


if __name__ == "__main__":
    main()