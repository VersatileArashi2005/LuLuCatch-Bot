# ============================================================
# 📁 File: utils/__init__.py
# 📍 Location: telegram_card_bot/utils/__init__.py
# 📝 Description: Utils package exports
# ============================================================

"""
LuLuCatch Utilities Package
Exports all utility modules for easy importing.
"""

# Logger exports
from utils.logger import (
    app_logger,
    error_logger,
    setup_logging,
    log_startup,
    log_shutdown,
    log_database,
    log_webhook,
    log_command,
    log_card_catch,
    log_error_with_context,
)

# Rarity exports
from utils.rarity import (
    Rarity,
    RARITY_TABLE,
    get_rarity,
    rarity_to_text,
    get_random_rarity,
    get_rarity_emoji,
    get_rarity_name,
    get_rarity_by_name,
    get_all_rarities,
    format_rarity_display,
    get_rarity_tier,
    is_rare_plus,
    is_legendary_tier,
    get_catch_reaction,
    get_celebration_reactions,
    should_celebrate,
    get_catch_celebration_text,
    calculate_rarity_value,
    get_xp_reward,
    get_coin_reward,
)

# Constants exports
from utils.constants import (
    RARITY_EMOJIS,
    RARITY_NAMES,
    CATCH_REACTIONS,
    PRIMARY_CATCH_REACTION,
    Templates,
    ButtonLabels,
    CallbackPrefixes,
    Pagination,
    Timing,
    MEDALS,
    get_medal,
    get_rarity_display,
    get_catch_template,
    format_card_entry,
    format_number,
)

# UI exports
from utils.ui import (
    format_card_caption,
    format_catch_message,
    format_spawn_message,
    format_drop_message,
    build_pagination_keyboard,
    build_harem_keyboard,
    build_card_detail_keyboard,
    build_battle_keyboard,
    build_trade_keyboard,
    build_confirm_keyboard,
    build_leaderboard_keyboard,
    get_catch_reactions,
    send_catch_reaction,
    format_harem_list,
    format_leaderboard,
    format_trade_message,
    format_bot_stats,
    format_user_stats,
    format_cooldown_message,
    format_error,
)


__all__ = [
    # Logger
    "app_logger",
    "error_logger",
    "setup_logging",
    "log_startup",
    "log_shutdown",
    "log_database",
    "log_webhook",
    "log_command",
    "log_card_catch",
    "log_error_with_context",
    
    # Rarity
    "Rarity",
    "RARITY_TABLE",
    "get_rarity",
    "rarity_to_text",
    "get_random_rarity",
    "get_rarity_emoji",
    "get_rarity_name",
    "get_rarity_by_name",
    "get_all_rarities",
    "format_rarity_display",
    "get_rarity_tier",
    "is_rare_plus",
    "is_legendary_tier",
    "get_catch_reaction",
    "get_celebration_reactions",
    "should_celebrate",
    "get_catch_celebration_text",
    "calculate_rarity_value",
    "get_xp_reward",
    "get_coin_reward",
    
    # Constants
    "RARITY_EMOJIS",
    "RARITY_NAMES",
    "CATCH_REACTIONS",
    "PRIMARY_CATCH_REACTION",
    "Templates",
    "ButtonLabels",
    "CallbackPrefixes",
    "Pagination",
    "Timing",
    "MEDALS",
    "get_medal",
    "get_rarity_display",
    "get_catch_template",
    "format_card_entry",
    "format_number",
    
    # UI
    "format_card_caption",
    "format_catch_message",
    "format_spawn_message",
    "format_drop_message",
    "build_pagination_keyboard",
    "build_harem_keyboard",
    "build_card_detail_keyboard",
    "build_battle_keyboard",
    "build_trade_keyboard",
    "build_confirm_keyboard",
    "build_leaderboard_keyboard",
    "get_catch_reactions",
    "send_catch_reaction",
    "format_harem_list",
    "format_leaderboard",
    "format_trade_message",
    "format_bot_stats",
    "format_user_stats",
    "format_cooldown_message",
    "format_error",
]