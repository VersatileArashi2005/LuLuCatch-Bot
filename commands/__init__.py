# ============================================================
# 📁 File: commands/__init__.py
# 📍 Location: telegram_card_bot/commands/__init__.py
# 📝 Description: Commands package with all handler exports
# ============================================================

"""
LuLuCatch Commands Package
All command handlers for the bot.
"""

# Harem (collection viewing with inline support)
from commands.harem import (
    register_harem_handlers,
    harem_command,
    inline_collection_handler,
)

# Backward compatibility alias
register_collection_handlers = register_harem_handlers

# Card info
from commands.cardinfo import (
    register_cardinfo_handlers,
    cardinfo_command,
    show_card_info,
    quick_card_view,
)

# Leaderboard and stats
from commands.leaderboard import (
    register_leaderboard_handlers,
    leaderboard_command,
    stats_command,
    top_command,
)

# Trading system
from commands.trade import (
    register_trade_handlers,
    trades_command,
    offertrade_command,
    canceltrade_command,
)

# Inline search
from commands.inline_search import (
    register_inline_handlers,
    register_inline_callback_handlers,
    inline_query_handler,
)


# ============================================================
# 📦 All Exports
# ============================================================

__all__ = [
    # Harem/Collection
    "register_harem_handlers",
    "register_collection_handlers",  # Backward compatibility
    "harem_command",
    "inline_collection_handler",
    
    # Card Info
    "register_cardinfo_handlers",
    "cardinfo_command",
    "show_card_info",
    "quick_card_view",
    
    # Leaderboard
    "register_leaderboard_handlers",
    "leaderboard_command",
    "stats_command",
    "top_command",
    
    # Trading
    "register_trade_handlers",
    "trades_command",
    "offertrade_command",
    "canceltrade_command",
    
    # Inline Search
    "register_inline_handlers",
    "register_inline_callback_handlers",
    "inline_query_handler",
]


# ============================================================
# 🔧 Convenience Function
# ============================================================

def register_all_command_handlers(application) -> None:
    """
    Register all command handlers at once.
    
    Args:
        application: Telegram bot Application instance
    """
    register_harem_handlers(application)
    register_cardinfo_handlers(application)
    register_leaderboard_handlers(application)
    register_trade_handlers(application)
    register_inline_handlers(application)
    register_inline_callback_handlers(application)