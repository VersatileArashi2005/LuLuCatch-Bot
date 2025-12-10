# ============================================================
# 📁 File: handlers/__init__.py
# 📍 Location: telegram_card_bot/handlers/__init__.py
# 📝 Description: Handlers package initialization
# ============================================================

from .upload import (
    upload_conversation_handler,
    upload_rarity_callback_handler,  # NEW - separate callback handler
    quick_upload_handler,
    UPLOAD_ANIME,
    UPLOAD_CHARACTER,
    UPLOAD_PHOTO,
)
from .admin import (
    admin_command_handler,
    broadcast_conversation_handler,
    admin_callback_handler,
    stats_command_handler,
    ban_command_handler,
    unban_command_handler,
    is_admin,
    set_bot_start_time,
)
from .catch import (
    catch_command_handler,
    catch_callback_handler,
    force_spawn_handler,
    name_guess_message_handler,
    spawn_card_in_group,
)

__all__ = [
    # Upload exports
    "upload_conversation_handler",
    "upload_rarity_callback_handler",
    "quick_upload_handler",
    "UPLOAD_ANIME",
    "UPLOAD_CHARACTER",
    "UPLOAD_PHOTO",
    # Admin exports
    "admin_command_handler",
    "broadcast_conversation_handler",
    "admin_callback_handler",
    "stats_command_handler",
    "ban_command_handler",
    "unban_command_handler",
    "is_admin",
    "set_bot_start_time",
    # Catch exports
    "catch_command_handler",
    "catch_callback_handler",
    "force_spawn_handler",
    "name_guess_message_handler",
    "spawn_card_in_group",
]