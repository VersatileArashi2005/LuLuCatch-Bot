# ============================================================
# 📁 File: main.py (Part 1 of 2)
# 📍 Location: telegram_card_bot/main.py
# 📝 Description: Modern bot with registration & flirty personality
# ============================================================

import asyncio
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, Request, Response, HTTPException, status
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode

from config import Config
from db import db, init_db, get_global_stats, ensure_user, get_user_by_id
from utils.logger import (
    app_logger,
    error_logger,
    setup_logging,
    log_startup,
    log_shutdown,
    log_webhook,
    log_command,
)
from utils.constants import format_number

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
    force_spawn_handler,
    clear_cheat_handler,
    view_cheaters_handler,
    battle_callback,
)
from commands.inline_search import (
    register_inline_handlers,
    register_inline_callback_handlers,
)
from commands.harem import register_harem_handlers
from commands.cardinfo import register_cardinfo_handlers
from commands.trade import register_trade_handlers
from commands.leaderboard import register_leaderboard_handlers
from handlers.drop import (
    setdrop_handler,
    droptime_handler,
    lulucatch_handler,
    forcedrop_handler,
    cleardrop_handler,
    dropstats_handler,
    message_counter,
)

# Try to import role handlers
try:
    from handlers.roles import register_role_handlers
    ROLES_AVAILABLE = True
except ImportError:
    ROLES_AVAILABLE = False
    def register_role_handlers(app):
        pass


# ============================================================
# 🔐 Registration Check
# ============================================================

async def is_user_registered(user_id: int) -> bool:
    """Check if user has registered via /start."""
    if not db.is_connected:
        return True  # Allow if DB offline
    
    user = await get_user_by_id(None, user_id)
    return user is not None


async def require_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Check if user is registered. Send prompt if not.
    Returns True if registered, False if not.
    """
    user = update.effective_user
    if not user:
        return False
    
    if await is_user_registered(user.id):
        return True
    
    # Not registered - send flirty prompt
    bot_username = context.bot.username or Config.BOT_USERNAME
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💋 Register Now", url=f"https://t.me/{bot_username}?start=register")]
    ])
    
    await update.effective_message.reply_text(
        f"Hey there, gorgeous~ 💕\n\n"
        f"I don't think we've met properly yet...\n"
        f"Why don't you come say hi first?\n\n"
        f"_Tap below to register with me~_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )
    
    return False


def registration_required(func):
    """Decorator to require registration for commands."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if await require_registration(update, context):
            return await func(update, context)
    return wrapper


# ============================================================
# 🤖 Bot Application
# ============================================================

bot_app: Optional[Application] = None


async def setup_bot() -> Application:
    """Set up the Telegram bot application."""
    log_startup("Setting up bot...")

    application = ApplicationBuilder().token(Config.BOT_TOKEN).build()
    set_bot_start_time()

    # ========================================
    # 💋 /start Command - Registration & Welcome
    # ========================================

    async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Welcome & registration handler."""
        if not update.message or not update.effective_user:
            return

        user = update.effective_user
        bot_username = context.bot.username or Config.BOT_USERNAME
        
        log_command(user.id, "start", update.effective_chat.id)

        # Register user
        await ensure_user(
            pool=None,
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )

        # Check for deep link parameters
        if context.args:
            param = context.args[0]

            # Card view from inline
            if param.startswith("card_"):
                try:
                    card_id = int(param.replace("card_", ""))
                    from db import get_card_by_id
                    from utils.rarity import rarity_to_text
                    from utils.constants import RARITY_EMOJIS
                    
                    card = await get_card_by_id(None, card_id)
                    if card:
                        rarity = card["rarity"]
                        rarity_name, prob, emoji = rarity_to_text(rarity)
                        
                        caption = (
                            f"{emoji} *{card['character_name']}*\n\n"
                            f"🎬 {card['anime']}\n"
                            f"{emoji} {rarity_name} ({prob}%)\n"
                            f"🆔 `#{card_id}`"
                        )
                        
                        keyboard = InlineKeyboardMarkup([[
                            InlineKeyboardButton("🔍 Search More", switch_inline_query_current_chat="")
                        ]])
                        
                        if card.get("photo_file_id"):
                            await update.message.reply_photo(
                                photo=card["photo_file_id"],
                                caption=caption,
                                parse_mode=ParseMode.MARKDOWN,
                                reply_markup=keyboard
                            )
                        else:
                            await update.message.reply_text(caption, parse_mode=ParseMode.MARKDOWN)
                        return
                except Exception as e:
                    error_logger.error(f"Card view error: {e}")

            # Inline help
            elif param in ["inline_help", "search"]:
                await update.message.reply_text(
                    f"🔍 *Searching for someone special?*\n\n"
                    f"Just type `@{bot_username} ` and whisper what you're looking for~\n\n"
                    f"_Try anime names, characters, or even_ `legendary` ✨",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            # Collection/harem
            elif param in ["collection", "harem"]:
                await update.message.reply_text(
                    f"🎴 *Your Harem awaits~*\n\n"
                    f"Use /harem to see all your beautiful catches 💕",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

        # === Main Welcome Message ===
        
        # Build welcome keyboard
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "➕ Add me to your group",
                    url=f"https://t.me/{bot_username}?startgroup=true"
                )
            ],
            [
                InlineKeyboardButton("📚 Help", callback_data="menu:help"),
                InlineKeyboardButton("💬 Support", url="https://t.me/lulucatch")
            ],
            [
                InlineKeyboardButton(
                    "🔍 Search Cards",
                    switch_inline_query_current_chat=""
                )
            ],
        ])

        welcome_text = (
            f"Hey there, {user.first_name}~ 💋\n\n"
            f"Welcome to *LuLuCatch*... I've been waiting for you.\n\n"
            f"I'm your personal card collector, and honey, "
            f"I've got quite the collection to show you~\n\n"
            f"✨ _Catch rare characters in groups_\n"
            f"💕 _Build your own harem_\n"
            f"🔥 _Trade with other collectors_\n\n"
            f"Ready to play with me? Add me to a group and "
            f"let's have some fun together~ 😘"
        )

        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        
        app_logger.info(f"💋 Welcome: {user.first_name} ({user.id})")

    # ========================================
    # 📚 /help Command
    # ========================================

    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Help command with all commands listed."""
        if not update.message:
            return
        
        if not await require_registration(update, context):
            return

        bot_username = context.bot.username or Config.BOT_USERNAME
        
        await update.message.reply_text(
            f"📚 *Let me teach you a few things~*\n\n"
            f"*🎯 Catching*\n"
            f"`/catch` — Battle for a wild card\n"
            f"`/lulucatch <name>` — Catch a dropped character\n"
            f"`/droptime` — When's the next drop?\n\n"
            f"*🎴 Collection*\n"
            f"`/harem` — Admire your collection\n"
            f"`/cardinfo <id>` — Card details\n\n"
            f"*🔄 Trading*\n"
            f"`/trades` — Your pending trades\n"
            f"`/offertrade` — Make someone an offer~\n\n"
            f"*🏆 Rankings*\n"
            f"`/leaderboard` — See who's on top\n"
            f"`/stats` — Bot statistics\n\n"
            f"*🔍 Inline Search*\n"
            f"Type `@{bot_username} naruto` anywhere!\n\n"
            f"_Need more help? Join our_ [support channel](https://t.me/lulucatch) 💕",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )

    # ========================================
    # 📊 /info Command
    # ========================================

    async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Bot info and statistics."""
        if not update.message:
            return
        
        if not await require_registration(update, context):
            return

        if db.is_connected:
            stats = await get_global_stats(None)
            
            await update.message.reply_text(
                f"📊 *A little about me~*\n\n"
                f"👥 Collectors: {format_number(stats.get('total_users', 0))}\n"
                f"🎴 Cards: {format_number(stats.get('total_cards', 0))}\n"
                f"🎯 Catches: {format_number(stats.get('total_catches', 0))}\n"
                f"💬 Groups: {format_number(stats.get('active_groups', 0))}\n\n"
                f"🔧 Version: `1.0.0`\n"
                f"🗄️ Status: _Online & ready for you~_",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                f"📊 *Something's not quite right...*\n\n"
                f"I'm having trouble connecting right now.\n"
                f"Give me a moment, darling~ 💕",
                parse_mode=ParseMode.MARKDOWN
            )

    # ========================================
    # 🔘 Menu Callbacks
    # ========================================

    async def menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle menu button callbacks."""
        query = update.callback_query
        if not query or not query.data:
            return
        
        await query.answer()
        data = query.data
        bot_username = context.bot.username or Config.BOT_USERNAME

        if data == "menu:help":
            await query.edit_message_text(
                f"📚 *Let me show you around~*\n\n"
                f"*🎯 Catching*\n"
                f"`/catch` — Battle for cards\n"
                f"`/lulucatch <name>` — Catch drops\n"
                f"`/droptime` — Next drop timer\n\n"
                f"*🎴 Collection*\n"
                f"`/harem` — Your collection\n"
                f"`/cardinfo <id>` — Card info\n\n"
                f"*🔄 Trading*\n"
                f"`/trades` — Pending trades\n"
                f"`/offertrade` — Offer a trade\n\n"
                f"*🏆 Rankings*\n"
                f"`/leaderboard` — Top collectors\n\n"
                f"*🔍 Inline*\n"
                f"Type `@{bot_username} ` anywhere!",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back", callback_data="menu:back")
                ]])
            )

        elif data == "menu:back":
            user = query.from_user
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "➕ Add to group",
                        url=f"https://t.me/{bot_username}?startgroup=true"
                    )
                ],
                [
                    InlineKeyboardButton("📚 Help", callback_data="menu:help"),
                    InlineKeyboardButton("💬 Support", url="https://t.me/lulucatch")
                ],
                [
                    InlineKeyboardButton("🔍 Search", switch_inline_query_current_chat="")
                ],
            ])

            await query.edit_message_text(
                f"Welcome back, {user.first_name}~ 💋\n\n"
                f"What would you like to do?",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )

    # ========================================
    # ❌ Error Handler
    # ========================================

    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Global error handler."""
        error_logger.error(f"Error: {context.error}", exc_info=context.error)

        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "Oops~ Something went wrong, darling.\n"
                    "Try again in a moment? 💕"
                )
            except Exception:
                pass



    # ========================================
    # 📝 Register Handlers
    # ========================================

    # === Conversation Handlers (MUST BE FIRST) ===
    application.add_handler(upload_conversation_handler)
    application.add_handler(broadcast_conversation_handler)
    application.add_handler(edit_conversation_handler)

    # === Basic Commands ===
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("info", info_command))

    # === Catch System ===
    application.add_handler(catch_command_handler)
    application.add_handler(force_spawn_handler)
    application.add_handler(clear_cheat_handler)
    application.add_handler(view_cheaters_handler)

    # === Admin Commands ===
    application.add_handler(admin_command_handler)
    application.add_handler(stats_command_handler)
    application.add_handler(ban_command_handler)
    application.add_handler(unban_command_handler)
    application.add_handler(quick_upload_handler)
    application.add_handler(delete_command_handler)
    application.add_handler(userinfo_command_handler)
    application.add_handler(give_card_command_handler)
    application.add_handler(give_coins_command_handler)

    # === Callback Handlers ===
    
    # Menu callbacks
    application.add_handler(CallbackQueryHandler(
        menu_callback_handler,
        pattern=r"^menu:"
    ))

    # Admin panel (new pattern)
    application.add_handler(CallbackQueryHandler(
        admin_callback_handler,
        pattern=r"^adm:"
    ))

    # Delete card
    application.add_handler(delete_card_callback_handler)

    # User management
    application.add_handler(user_management_callback_handler)

    # Battle/Catch
    application.add_handler(battle_callback)

    # === Module Registrations ===
    
    # Inline search
    register_inline_handlers(application)
    register_inline_callback_handlers(application)

    # Harem/Collection
    register_harem_handlers(application)

    # Card info
    register_cardinfo_handlers(application)

    # Trading
    register_trade_handlers(application)

    # Leaderboard
    register_leaderboard_handlers(application)

    # Roles
    if ROLES_AVAILABLE:
        register_role_handlers(application)

    # === Drop System ===
    application.add_handler(setdrop_handler)
    application.add_handler(droptime_handler)
    application.add_handler(lulucatch_handler)
    application.add_handler(forcedrop_handler)
    application.add_handler(cleardrop_handler)
    application.add_handler(dropstats_handler)
    
    # Message counter (MUST BE LAST)
    application.add_handler(message_counter)

    # === Error Handler ===
    application.add_error_handler(error_handler)

    # ========================================
    # 📋 Bot Commands Menu
    # ========================================

    commands = [
        BotCommand("start", "💋 Start & register"),
        BotCommand("help", "📚 All commands"),
        BotCommand("catch", "⚔️ Battle for a card"),
        BotCommand("lulucatch", "🎯 Catch a drop"),
        BotCommand("droptime", "⏱️ Next drop timer"),
        BotCommand("harem", "🎴 Your collection"),
        BotCommand("cardinfo", "🔍 Card details"),
        BotCommand("trades", "🔄 Your trades"),
        BotCommand("leaderboard", "🏆 Top collectors"),
        BotCommand("info", "📊 Bot stats"),
    ]

    try:
        await application.bot.set_my_commands(commands)
        app_logger.info("✅ Commands menu set")
    except Exception as e:
        error_logger.error(f"Commands menu error: {e}")

    log_startup("✅ Bot ready with registration system")
    return application


# ============================================================
# 🌐 FastAPI Application
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan manager."""
    global bot_app

    # === Startup ===
    log_startup("Starting LuLuCatch Bot v1.0...")

    # Validate config
    is_valid, errors = Config.validate()
    if not is_valid:
        for error in errors:
            error_logger.error(error)
        raise RuntimeError("Invalid configuration")

    app_logger.info(Config.display_config())

    # Connect database
    db_connected = await db.connect(max_retries=3, retry_delay=2)
    if db_connected:
        await init_db()
    else:
        app_logger.warning("⚠️ Starting without database")

    # Setup bot
    bot_app = await setup_bot()
    await bot_app.initialize()
    await bot_app.start()

    # Webhook or polling
    if Config.WEBHOOK_URL:
        webhook_url = Config.get_full_webhook_url()
        log_webhook(f"Setting webhook: {webhook_url}")

        try:
            await bot_app.bot.delete_webhook(drop_pending_updates=False)
            webhook_set = await bot_app.bot.set_webhook(
                url=webhook_url,
                secret_token=Config.WEBHOOK_SECRET,
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=False,
            )

            if webhook_set:
                log_webhook("✅ Webhook configured")
                webhook_info = await bot_app.bot.get_webhook_info()
                log_webhook(f"URL: {webhook_info.url}")
            else:
                error_logger.error("❌ Webhook failed")

        except Exception as e:
            error_logger.error(f"❌ Webhook error: {e}", exc_info=True)
    else:
        log_startup("⚠️ Using polling mode")
        asyncio.create_task(bot_app.updater.start_polling(drop_pending_updates=True))

    log_startup("🎴 LuLuCatch Bot v1.0 is live! 💋")

    yield

    # === Shutdown ===
    log_shutdown("Shutting down...")

    if bot_app:
        try:
            await bot_app.stop()
            await bot_app.shutdown()
        except Exception as e:
            error_logger.error(f"Shutdown error: {e}")

    await db.disconnect()
    log_shutdown("✅ Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="LuLuCatch Bot",
    description="Telegram Card Collection Bot",
    version="1.0.0",
    lifespan=lifespan,
)


# ============================================================
# 📡 API Endpoints
# ============================================================

@app.get("/")
async def root():
    """Health check."""
    return {
        "status": "online",
        "bot": "LuLuCatch",
        "version": "1.0.0",
        "database": "connected" if db.is_connected else "disconnected",
        "message": "💋 Ready to catch some hearts~"
    }


@app.get("/health")
async def health_check():
    """Detailed health check."""
    from db import health_check as db_health_check

    db_status = await db_health_check(None) if db.is_connected else False

    return {
        "status": "healthy" if db_status else "degraded",
        "database": "connected" if db_status else "disconnected",
        "bot": "running" if bot_app else "stopped",
    }


@app.post("/webhook")
async def webhook_handler(request: Request) -> Response:
    """Telegram webhook endpoint."""
    global bot_app

    # Verify secret
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret_token != Config.WEBHOOK_SECRET:
        error_logger.warning("Invalid webhook token")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token")

    if bot_app is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Bot not ready")

    try:
        update_data = await request.json()
        update = Update.de_json(update_data, bot_app.bot)
        await bot_app.process_update(update)
        return Response(status_code=status.HTTP_200_OK, content="OK")

    except Exception as e:
        error_logger.error(f"Webhook error: {e}", exc_info=True)
        return Response(status_code=status.HTTP_200_OK, content="Error logged")


@app.get("/webhook")
async def webhook_get():
    """Webhook verification."""
    return {"status": "active", "version": "1.0.0"}


# ============================================================
# 🚀 Run Application
# ============================================================

if __name__ == "__main__":
    setup_logging(debug=Config.DEBUG)

    uvicorn.run(
        "main:app",
        host=Config.HOST,
        port=Config.PORT,
        reload=Config.DEBUG,
        log_level="info"
    )