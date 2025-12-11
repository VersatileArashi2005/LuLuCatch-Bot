# ============================================================
# 📁 File: main.py
# 📍 Location: telegram_card_bot/main.py
# 📝 Description: FastAPI app with Telegram bot integration
# ============================================================

import asyncio
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, Request, Response, HTTPException, status
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
    upload_rarity_callback_handler,
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
    # New admin handlers
    delete_command_handler,
    delete_card_callback_handler,
    edit_conversation_handler,
    userinfo_command_handler,
    user_management_callback_handler,
    give_card_command_handler,
    give_coins_command_handler,
)
from handlers.catch import (
    catch_command_handler,
    battle_callback,
    force_spawn_handler,
    name_guess_message_handler,
)

# Import inline search handlers
from commands.inline_search import (
    register_inline_handlers,
    register_inline_callback_handlers,
)

# Import Part 4 handlers
from commands.collection import register_collection_handlers
from commands.cardinfo import register_cardinfo_handlers
from commands.trade import register_trade_handlers
from commands.leaderboard import register_leaderboard_handlers


# ============================================================
# 🤖 Telegram Bot Application
# ============================================================

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
        if not update.message or not update.effective_user:
            return

        user = update.effective_user
        db_status = "✅ Connected" if db.is_connected else "⚠️ Offline"

        # Check for start parameters
        if context.args:
            param = context.args[0]

            # Handle card view from inline
            if param.startswith("card_"):
                try:
                    card_id = int(param.replace("card_", ""))
                    from db import get_card_by_id
                    card = await get_card_by_id(None, card_id)

                    if card:
                        from utils.rarity import rarity_to_text
                        rarity_name, rarity_prob, rarity_emoji = rarity_to_text(card["rarity"])

                        caption = (
                            f"{rarity_emoji} *{card['character_name']}*\n\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"🎬 *Anime:* {card['anime']}\n"
                            f"🆔 *ID:* `#{card['card_id']}`\n"
                            f"✨ *Rarity:* {rarity_emoji} {rarity_name} ({rarity_prob}%)\n"
                            f"📊 *Drop Rate:* {rarity_prob}%\n"
                            f"━━━━━━━━━━━━━━━━━━━━"
                        )

                        if card.get("photo_file_id"):
                            await update.message.reply_photo(
                                photo=card["photo_file_id"],
                                caption=caption,
                                parse_mode="Markdown"
                            )
                        else:
                            await update.message.reply_text(caption, parse_mode="Markdown")
                        return
                except Exception as e:
                    error_logger.error(f"Error handling card start param: {e}")

            # Handle inline help
            elif param == "inline_help" or param == "search":
                await update.message.reply_text(
                    "🔍 *Inline Search Help*\n\n"
                    "Type `@" + (context.bot.username or "bot") + " ` followed by:\n\n"
                    "• *Anime name:* `naruto`\n"
                    "• *Character:* `itachi`\n"
                    "• *Rarity:* `legendary` or `💎`\n"
                    "• *Card ID:* `#42` or `42`\n\n"
                    "Results will appear as you type!",
                    parse_mode="Markdown"
                )
                return

            # Handle harem from inline
            elif param == "harem":
                # Redirect to collection command
                pass  # Fall through to normal start

        await update.message.reply_text(
            f"🎴 *Welcome to LuLuCatch, {user.first_name}!*\n\n"
            f"I'm a card collection bot. Catch cards when they spawn in groups!\n\n"
            f"📚 *Commands:*\n"
            f"• /start - Show this message\n"
            f"• /info - View bot information\n"
            f"• /collection - View your card collection\n"
            f"• /catch - Catch a spawned card\n"
            f"• /cardinfo <id> - Check card details\n"
            f"• /trades - View pending trades\n"
            f"• /leaderboard - Top collectors\n\n"
            f"🔍 *Inline Search:*\n"
            f"Type `@{context.bot.username} ` in any chat to search cards!\n\n"
            f"🗄️ Database: {db_status}\n\n"
            f"Add me to a group to start catching cards! 🚀",
            parse_mode="Markdown"
        )
        app_logger.info(f"📨 /start from user {user.id}")

    async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /info command."""
        if not update.message:
            return

        if db.is_connected:
            stats = await get_global_stats(None)
            await update.message.reply_text(
                f"📊 *LuLuCatch Bot Info*\n\n"
                f"👥 Total Users: {stats['total_users']:,}\n"
                f"🎴 Total Cards: {stats['total_cards']:,}\n"
                f"🎯 Total Catches: {stats['total_catches']:,}\n"
                f"💬 Active Groups: {stats['active_groups']:,}\n\n"
                f"🗄️ Database: ✅ Connected\n"
                f"🔧 Version: 1.0.0 (Part 4)",
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

    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /help command."""
        if not update.message:
            return

        await update.message.reply_text(
            "📚 *LuLuCatch Bot Help*\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "*Basic Commands:*\n"
            "• /start - Welcome message\n"
            "• /info - Bot statistics\n"
            "• /help - This help message\n\n"
            "*Collection:*\n"
            "• /collection - View your cards\n"
            "• /cardinfo <id> - Card details\n\n"
            "*Catching:*\n"
            "• /catch - Battle for a card\n"
            "• Type character name to guess\n\n"
            "*Trading:*\n"
            "• /trades - View pending trades\n"
            "• /offertrade <card_id> <user_id> - Offer trade\n"
            "• /viewtrade <id> - View trade details\n\n"
            "*Leaderboard:*\n"
            "• /leaderboard - Top collectors\n\n"
            "*Inline Mode:*\n"
            "Type `@" + (context.bot.username or "bot") + " <query>` to search cards\n"
            "━━━━━━━━━━━━━━━━━━━━",
            parse_mode="Markdown"
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
    # Register Conversation Handlers (MUST BE FIRST)
    # ========================================

    application.add_handler(upload_conversation_handler)
    application.add_handler(broadcast_conversation_handler)
    application.add_handler(edit_conversation_handler)  # NEW: Edit card conversation

    # ========================================
    # Register Command Handlers
    # ========================================

    # Basic commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("info", info_command))
    application.add_handler(CommandHandler("help", help_command))

    # Catch commands
    application.add_handler(catch_command_handler)
    application.add_handler(force_spawn_handler)

    # Admin commands
    application.add_handler(admin_command_handler)
    application.add_handler(stats_command_handler)
    application.add_handler(ban_command_handler)
    application.add_handler(unban_command_handler)
    application.add_handler(quick_upload_handler)

    # NEW: Additional admin commands
    application.add_handler(delete_command_handler)
    application.add_handler(userinfo_command_handler)
    application.add_handler(give_card_command_handler)
    application.add_handler(give_coins_command_handler)

    # ========================================
    # Register Callback Query Handlers
    # ========================================

    # Upload rarity selection
    application.add_handler(upload_rarity_callback_handler)

    # Admin panel callbacks
    application.add_handler(CallbackQueryHandler(
        admin_callback_handler,
        pattern=r"^admin_(?!delcard_|user_|edit_)"  # Exclude new patterns
    ))

    # NEW: Delete card callbacks
    application.add_handler(delete_card_callback_handler)

    # NEW: User management callbacks
    application.add_handler(user_management_callback_handler)

    # Battle callbacks
    application.add_handler(battle_callback)

    # ========================================
    # Register Message Handlers
    # ========================================

    application.add_handler(name_guess_message_handler)

    # ========================================
    # Register Inline Search Handlers
    # ========================================

    register_inline_handlers(application)
    register_inline_callback_handlers(application)

    # ========================================
    # Register Part 4 Handlers
    # ========================================

    register_collection_handlers(application)
    register_cardinfo_handlers(application)
    register_trade_handlers(application)
    register_leaderboard_handlers(application)

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
        BotCommand("help", "📚 Help & commands"),
        BotCommand("catch", "⚔️ Battle for a card"),
        BotCommand("collection", "🎴 Your collection"),
        BotCommand("cardinfo", "🔍 Card details"),
        BotCommand("trades", "🔁 Pending trades"),
        BotCommand("leaderboard", "🏆 Top collectors"),
    ]

    try:
        await application.bot.set_my_commands(commands)
    except Exception as e:
        error_logger.error(f"Failed to set commands: {e}")

    log_startup("✅ Bot application configured with battle system and admin commands")

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

    # Try to connect to database
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

    # Initialize and start the bot
    await bot_app.initialize()
    await bot_app.start()

    # Set up webhook if URL is configured
    if Config.WEBHOOK_URL:
        webhook_url = Config.get_full_webhook_url()
        log_webhook(f"Setting webhook: {webhook_url}")

        try:
            # Delete any existing webhook first
            await bot_app.bot.delete_webhook(drop_pending_updates=False)

            # Set new webhook
            webhook_set = await bot_app.bot.set_webhook(
                url=webhook_url,
                secret_token=Config.WEBHOOK_SECRET,
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=False,
            )

            if webhook_set:
                log_webhook("✅ Webhook configured successfully")

                # Verify webhook was set
                webhook_info = await bot_app.bot.get_webhook_info()
                log_webhook(f"Webhook URL: {webhook_info.url}")
                log_webhook(f"Pending updates: {webhook_info.pending_update_count}")
            else:
                error_logger.error("❌ Failed to set webhook")

        except Exception as e:
            error_logger.error(f"❌ Webhook error: {e}", exc_info=True)
    else:
        # Use polling mode (for local development)
        log_startup("⚠️ No webhook URL configured, using polling mode")
        asyncio.create_task(bot_app.updater.start_polling(drop_pending_updates=True))

    log_startup("🎴 LuLuCatch Bot is running!")

    yield  # Application is running

    # ========================================
    # 🛑 Shutdown
    # ========================================
    log_shutdown("Shutting down LuLuCatch Bot...")

    if bot_app:
        try:
            await bot_app.stop()
            await bot_app.shutdown()
        except Exception as e:
            error_logger.error(f"Shutdown error: {e}")

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
        "database": "connected" if db.is_connected else "disconnected",
        "message": "🎴 Card collection bot is running!"
    }


@app.get("/health")
async def health_check():
    """Detailed health check endpoint."""
    from db import health_check as db_health_check

    db_status = await db_health_check(None) if db.is_connected else False

    return {
        "status": "healthy" if db_status else "degraded",
        "database": "connected" if db_status else "disconnected",
        "bot": "running" if bot_app else "stopped",
    }


@app.post("/webhook")
async def webhook_handler(request: Request) -> Response:
    """
    Webhook endpoint for receiving Telegram updates.
    """
    global bot_app

    # Verify the webhook secret token
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")

    if secret_token != Config.WEBHOOK_SECRET:
        error_logger.warning("Invalid webhook secret token received")
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
        # Parse the update from request body
        update_data = await request.json()

        # Log incoming update
        update_id = update_data.get("update_id", "unknown")
        app_logger.info(f"📥 Received update: {update_id}")

        # Convert to Update object
        update = Update.de_json(update_data, bot_app.bot)

        # Process the update
        await bot_app.process_update(update)

        return Response(status_code=status.HTTP_200_OK, content="OK")

    except Exception as e:
        error_logger.error(f"Error processing webhook update: {e}", exc_info=True)
        # Return 200 to prevent Telegram from retrying
        return Response(status_code=status.HTTP_200_OK, content="Error logged")


@app.get("/webhook")
async def webhook_get():
    """GET endpoint for webhook verification."""
    return {"status": "Webhook endpoint active"}


# ============================================================
# 🚀 Run the application
# ============================================================

if __name__ == "__main__":
    # Set up logging
    setup_logging(debug=Config.DEBUG)

    # Run FastAPI server
    uvicorn.run(
        "main:app",
        host=Config.HOST,
        port=Config.PORT,
        reload=Config.DEBUG,
        log_level="info"
    )