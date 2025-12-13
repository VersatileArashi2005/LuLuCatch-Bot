# ============================================================
# 📁 File: handlers/__init__.py
# 📍 Location: telegram_card_bot/handlers/__init__.py
# 📝 Description: Handlers package with all exports
# ============================================================

"""
LuLuCatch Handlers Package
All event handlers for the bot.
"""

# ============================================================
# 📤 Upload Handlers
# ============================================================

from handlers.upload import (
    upload_conversation_handler,
    upload_rarity_callback_handler,
    quick_upload_handler,
)

# ============================================================
# 👑 Admin Handlers
# ============================================================

from handlers.admin import (
    # Main admin
    admin_command_handler,
    admin_callback_handler,
    
    # Broadcast
    broadcast_conversation_handler,
    
    # Card management
    delete_command_handler,
    delete_card_callback_handler,
    edit_conversation_handler,
    
    # User management
    userinfo_command_handler,
    user_management_callback_handler,
    give_card_command_handler,
    give_coins_command_handler,
    
    # Quick commands
    stats_command_handler,
    ban_command_handler,
    unban_command_handler,
    
    # Helpers
    is_admin,
    set_bot_start_time,
    get_uptime,
)

# ============================================================
# ⚔️ Catch Handlers
# ============================================================

from handlers.catch import (
    catch_command_handler,
    battle_callback,
    force_spawn_handler,
    clear_cheat_handler,
    view_cheaters_handler,
    
    # Managers (for external use)
    catch_manager,
    anti_cheat,
)

# ============================================================
# 🎴 Drop Handlers
# ============================================================

from handlers.drop import (
    setdrop_handler,
    droptime_handler,
    lulucatch_handler,
    forcedrop_handler,
    cleardrop_handler,
    dropstats_handler,
    message_counter,
    
    # List of all drop handlers
    drop_handlers,
    
    # State (for external access if needed)
    active_drops,
)

# ============================================================
# 👤 Role Handlers
# ============================================================

try:
    from handlers.roles import (
        register_role_handlers,
        is_uploader,
        is_owner,
    )
    ROLES_AVAILABLE = True
except ImportError:
    ROLES_AVAILABLE = False
    
    # Fallback functions
    def register_role_handlers(app):
        pass
    
    async def is_uploader(user_id: int) -> bool:
        from config import Config
        return Config.is_admin(user_id)
    
    async def is_owner(user_id: int) -> bool:
        from config import Config
        return Config.is_owner(user_id)

# ============================================================
# 🔔 Notification Handlers
# ============================================================

try:
    from handlers.notifications import (
        send_upload_notifications,
    )
    NOTIFICATIONS_AVAILABLE = True
except ImportError:
    NOTIFICATIONS_AVAILABLE = False
    
    async def send_upload_notifications(*args, **kwargs):
        return {"channel_archived": False, "groups_notified": 0, "groups_total": 0}

# ============================================================
# 📦 All Exports
# ============================================================

__all__ = [
    # Upload
    "upload_conversation_handler",
    "upload_rarity_callback_handler",
    "quick_upload_handler",
    
    # Admin
    "admin_command_handler",
    "admin_callback_handler",
    "broadcast_conversation_handler",
    "delete_command_handler",
    "delete_card_callback_handler",
    "edit_conversation_handler",
    "userinfo_command_handler",
    "user_management_callback_handler",
    "give_card_command_handler",
    "give_coins_command_handler",
    "stats_command_handler",
    "ban_command_handler",
    "unban_command_handler",
    "is_admin",
    "set_bot_start_time",
    "get_uptime",
    
    # Catch
    "catch_command_handler",
    "battle_callback",
    "force_spawn_handler",
    "clear_cheat_handler",
    "view_cheaters_handler",
    "catch_manager",
    "anti_cheat",
    
    # Drop
    "setdrop_handler",
    "droptime_handler",
    "lulucatch_handler",
    "forcedrop_handler",
    "cleardrop_handler",
    "dropstats_handler",
    "message_counter",
    "drop_handlers",
    "active_drops",
    
    # Roles
    "register_role_handlers",
    "is_uploader",
    "is_owner",
    "ROLES_AVAILABLE",
    
    # Notifications
    "send_upload_notifications",
    "NOTIFICATIONS_AVAILABLE",
]


# ============================================================
# 🔧 Convenience Function
# ============================================================

def register_all_handlers(application) -> None:
    """
    Register all handlers at once.
    
    Args:
        application: Telegram bot Application instance
    """
    from telegram.ext import CallbackQueryHandler
    
    # === Conversation Handlers (MUST BE FIRST) ===
    application.add_handler(upload_conversation_handler)
    application.add_handler(broadcast_conversation_handler)
    application.add_handler(edit_conversation_handler)
    
    # === Command Handlers ===
    
    # Catch
    application.add_handler(catch_command_handler)
    application.add_handler(force_spawn_handler)
    application.add_handler(clear_cheat_handler)
    application.add_handler(view_cheaters_handler)
    
    # Admin
    application.add_handler(admin_command_handler)
    application.add_handler(stats_command_handler)
    application.add_handler(ban_command_handler)
    application.add_handler(unban_command_handler)
    application.add_handler(delete_command_handler)
    application.add_handler(userinfo_command_handler)
    application.add_handler(give_card_command_handler)
    application.add_handler(give_coins_command_handler)
    
    # Upload
    application.add_handler(quick_upload_handler)
    
    # Drop
    application.add_handler(setdrop_handler)
    application.add_handler(droptime_handler)
    application.add_handler(lulucatch_handler)
    application.add_handler(forcedrop_handler)
    application.add_handler(cleardrop_handler)
    application.add_handler(dropstats_handler)
    
    # === Callback Handlers ===
    
    # Admin panel
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
    
    # === Message Handlers ===
    
    # Message counter (MUST BE LAST)
    application.add_handler(message_counter)
    
    # === Role Handlers ===
    if ROLES_AVAILABLE:
        register_role_handlers(application)