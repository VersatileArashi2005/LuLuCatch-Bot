# ============================================================
# 📁 File: commands/__init__.py
# 📍 Location: telegram_card_bot/commands/__init__.py
# 📝 Description: Commands package initialization
# ============================================================

# Import all command handlers for easy access

from .harem import register_harem_handlers

# Backward compatibility alias
register_collection_handlers = register_harem_handlers

from .cardinfo import register_cardinfo_handlers
from .trade import register_trade_handlers
from .leaderboard import register_leaderboard_handlers
from .inline_search import (
    register_inline_handlers,
    register_inline_callback_handlers,
)

__all__ = [
    # Harem (replaces collection)
    "register_harem_handlers",
    "register_collection_handlers",  # Backward compatibility
    
    # Card info
    "register_cardinfo_handlers",
    
    # Trading
    "register_trade_handlers",
    
    # Leaderboard
    "register_leaderboard_handlers",
    
    # Inline search
    "register_inline_handlers",
    "register_inline_callback_handlers",
]