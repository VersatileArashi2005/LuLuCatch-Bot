# ============================================================
# 📁 File: utils/constants.py
# 📍 Location: telegram_card_bot/utils/constants.py
# 📝 Description: Design system - emojis, reactions, templates
# ============================================================

"""
LuLuCatch Design System
Modern, clean UI constants without cluttered borders.
Uses Telegram-native features for premium experience.
"""

from typing import Dict, List, Optional
from enum import Enum


# ============================================================
# 🎨 Rarity Emojis (Updated Premium Set)
# ============================================================

RARITY_EMOJIS: Dict[int, str] = {
    1: "☘️",    # Normal
    2: "⚡",    # Common
    3: "⭐",    # Uncommon
    4: "💠",    # Rare
    5: "🔮",    # Epic
    6: "🧿",    # Limited Epic
    7: "🪩",    # Platinum
    8: "🎐",    # Emerald
    9: "❄️",    # Crystal
    10: "🏵️",   # Mythical
    11: "🌸",   # Legendary
}

RARITY_NAMES: Dict[int, str] = {
    1: "Normal",
    2: "Common",
    3: "Uncommon",
    4: "Rare",
    5: "Epic",
    6: "Limited Epic",
    7: "Platinum",
    8: "Emerald",
    9: "Crystal",
    10: "Mythical",
    11: "Legendary",
}


# ============================================================
# 🎉 Auto-Reactions for Card Catches
# ============================================================

# Telegram reaction emojis that will be sent when user catches a card
# Higher rarity = more celebratory reactions
CATCH_REACTIONS: Dict[int, List[str]] = {
    1: ["👍"],
    2: ["👍"],
    3: ["⭐"],
    4: ["🔥"],
    5: ["🔥", "💯"],
    6: ["🔥", "💯"],
    7: ["🎉", "🔥"],
    8: ["🎉", "💎"],
    9: ["🎉", "💎", "❄️"],
    10: ["🏆", "🎉", "💎"],
    11: ["🏆", "🎉", "💎", "❤️‍🔥"],
}

# Single reaction for quick response (Telegram limits reactions)
PRIMARY_CATCH_REACTION: Dict[int, str] = {
    1: "👍",
    2: "👍",
    3: "⭐",
    4: "🔥",
    5: "🔥",
    6: "💯",
    7: "🎉",
    8: "💎",
    9: "❄️",
    10: "🏆",
    11: "❤️‍🔥",
}


# ============================================================
# 📝 Message Templates (Clean & Modern)
# ============================================================

class Templates:
    """Clean message templates without ASCII borders."""
    
    # Card spawn in group
    CARD_SPAWN = (
        "{rarity_emoji} *A wild character appeared!*\n"
        "\n"
        "Quick! Type /catch to battle!"
    )
    
    # Successful catch
    CATCH_SUCCESS = (
        "{rarity_emoji} *{user_name} caught {character}!*\n"
        "\n"
        "🎬 {anime}\n"
        "{rarity_emoji} {rarity_name}\n"
        "🆔 `#{card_id}`"
    )
    
    # First time catch (new card)
    CATCH_SUCCESS_NEW = (
        "🆕 {rarity_emoji} *NEW CARD!*\n"
        "\n"
        "*{user_name}* caught *{character}*!\n"
        "\n"
        "🎬 {anime}\n"
        "{rarity_emoji} {rarity_name}\n"
        "🆔 `#{card_id}`"
    )
    
    # Rare+ catch celebration
    CATCH_RARE = (
        "✨ {rarity_emoji} *RARE CATCH!* {rarity_emoji} ✨\n"
        "\n"
        "*{user_name}* caught *{character}*!\n"
        "\n"
        "🎬 {anime}\n"
        "{rarity_emoji} {rarity_name} ({probability}%)\n"
        "🆔 `#{card_id}`"
    )
    
    # Legendary catch (max celebration)
    CATCH_LEGENDARY = (
        "🎊 {rarity_emoji} *LEGENDARY CATCH!* {rarity_emoji} 🎊\n"
        "\n"
        "*{user_name}* caught *{character}*!\n"
        "\n"
        "🎬 {anime}\n"
        "{rarity_emoji} {rarity_name} ({probability}%)\n"
        "🆔 `#{card_id}`\n"
        "\n"
        "🏆 *Congratulations!*"
    )
    
    # Battle start
    BATTLE_START = (
        "⚔️ *Battle Started!*\n"
        "\n"
        "{rarity_emoji} *{character}*\n"
        "🎬 {anime}\n"
        "\n"
        "Choose your move:"
    )
    
    # Battle won
    BATTLE_WON = (
        "🏆 *Victory!*\n"
        "\n"
        "You caught {rarity_emoji} *{character}*!\n"
        "Added to your harem."
    )
    
    # Battle lost
    BATTLE_LOST = (
        "💀 *Defeated!*\n"
        "\n"
        "{rarity_emoji} *{character}* escaped!\n"
        "Better luck next time."
    )
    
    # Card info display
    CARD_INFO = (
        "{rarity_emoji} *{character}*\n"
        "\n"
        "🎬 *Anime:* {anime}\n"
        "🆔 *ID:* `#{card_id}`\n"
        "{rarity_emoji} *Rarity:* {rarity_name}\n"
        "📊 *Drop Rate:* {probability}%\n"
        "👥 *Owners:* {owner_count}"
    )
    
    # Harem header
    HAREM_HEADER = (
        "🎴 *{user_name}'s Harem*\n"
        "\n"
        "📊 {total_cards} cards ({unique_cards} unique)"
    )
    
    # Harem card entry
    HAREM_CARD = "{rarity_emoji} *{character}* ×{quantity}\n└ {anime}"
    
    # Harem empty
    HAREM_EMPTY = (
        "🎴 *Your Harem*\n"
        "\n"
        "Your harem is empty!\n"
        "Catch cards in groups to build your collection."
    )
    
    # Trade offer
    TRADE_OFFER = (
        "🔄 *Trade Request*\n"
        "\n"
        "From: *{from_user}*\n"
        "To: *{to_user}*\n"
        "\n"
        "📤 *Offering:*\n"
        "{rarity_emoji} {offered_card}\n"
        "\n"
        "📥 *Requesting:*\n"
        "{req_rarity_emoji} {requested_card}"
    )
    
    # Leaderboard header
    LEADERBOARD_HEADER = "🏆 *Top Collectors*\n"
    
    # Leaderboard entry
    LEADERBOARD_ENTRY = "{medal} *{rank}.* {name} — {count} cards"
    
    # Cooldown message
    COOLDOWN = "⏳ Cooldown! Wait *{seconds}s* before catching again."
    
    # Error messages
    ERROR_GENERIC = "❌ Something went wrong. Please try again."
    ERROR_NO_CARD = "❌ Card not found."
    ERROR_NO_PERMISSION = "🚫 You don't have permission for this."
    ERROR_DATABASE = "🔌 Database unavailable. Try again later."
    
    # Success messages
    SUCCESS_GENERIC = "✅ Done!"
    SUCCESS_UPLOADED = "✅ Card uploaded successfully!"
    SUCCESS_DELETED = "✅ Card deleted."
    SUCCESS_TRADE_SENT = "✅ Trade request sent!"
    SUCCESS_TRADE_ACCEPTED = "✅ Trade completed!"


# ============================================================
# 🏅 Medal Emojis for Leaderboard
# ============================================================

MEDALS: Dict[int, str] = {
    1: "🥇",
    2: "🥈",
    3: "🥉",
}

def get_medal(rank: int) -> str:
    """Get medal emoji for rank, or number for 4+."""
    return MEDALS.get(rank, f"{rank}.")


# ============================================================
# 🎮 Button Labels
# ============================================================

class ButtonLabels:
    """Standard button text for inline keyboards."""
    
    # Navigation
    PREV = "◀️"
    NEXT = "▶️"
    BACK = "🔙 Back"
    CLOSE = "✖️ Close"
    REFRESH = "🔄"
    
    # Actions
    CATCH = "⚔️ Battle"
    VIEW = "👁️ View"
    TRADE = "🔄 Trade"
    FAVORITE = "❤️"
    UNFAVORITE = "💔"
    
    # Battle moves
    ATTACK = "⚔️ Attack"
    DEFEND = "🛡️ Defend"
    SPECIAL = "✨ Special"
    
    # Confirmations
    CONFIRM = "✅ Confirm"
    CANCEL = "❌ Cancel"
    ACCEPT = "✅ Accept"
    REJECT = "❌ Reject"
    
    # Filters
    ALL = "📋 All"
    RARE_ONLY = "💎 Rare+"
    LEGENDARY = "🌸 Legendary"


# ============================================================
# 📍 Callback Data Prefixes
# ============================================================

class CallbackPrefixes:
    """Standardized callback data prefixes."""
    
    # Harem/Collection
    HAREM_PAGE = "harem_page:"
    HAREM_CARD = "harem_card:"
    HAREM_FILTER = "harem_filter:"
    
    # Card actions
    CARD_VIEW = "card_view:"
    CARD_TRADE = "card_trade:"
    CARD_FAV = "card_fav:"
    
    # Battle
    BATTLE_ACTION = "battle:"
    
    # Trade
    TRADE_ACCEPT = "trade_accept:"
    TRADE_REJECT = "trade_reject:"
    TRADE_CANCEL = "trade_cancel:"
    
    # Admin
    ADMIN_ACTION = "admin:"
    DELETE_CARD = "delcard:"
    
    # Leaderboard
    LB_PAGE = "lb_page:"
    LB_TYPE = "lb_type:"


# ============================================================
# 🔢 Pagination Settings
# ============================================================

class Pagination:
    """Pagination constants."""
    
    HAREM_PER_PAGE = 6
    LEADERBOARD_PER_PAGE = 10
    TRADES_PER_PAGE = 5
    SEARCH_RESULTS = 20
    INLINE_RESULTS = 25


# ============================================================
# ⏱️ Timing Constants
# ============================================================

class Timing:
    """Timing-related constants."""
    
    BATTLE_TIMEOUT = 30  # seconds
    TRADE_EXPIRY = 3600  # 1 hour
    CACHE_TTL = 300  # 5 minutes
    

# ============================================================
# 🎯 Helper Functions
# ============================================================

def get_rarity_display(rarity_id: int) -> str:
    """Get 'emoji name' format for rarity."""
    emoji = RARITY_EMOJIS.get(rarity_id, "❓")
    name = RARITY_NAMES.get(rarity_id, "Unknown")
    return f"{emoji} {name}"


def get_catch_template(rarity_id: int, is_new: bool = False) -> str:
    """Get appropriate catch template based on rarity."""
    if rarity_id == 11:
        return Templates.CATCH_LEGENDARY
    elif rarity_id >= 7:
        return Templates.CATCH_RARE
    elif is_new:
        return Templates.CATCH_SUCCESS_NEW
    else:
        return Templates.CATCH_SUCCESS


def format_card_entry(
    character: str,
    anime: str,
    rarity_id: int,
    quantity: int = 1
) -> str:
    """Format a card entry for lists."""
    emoji = RARITY_EMOJIS.get(rarity_id, "❓")
    qty = f" ×{quantity}" if quantity > 1 else ""
    return f"{emoji} *{character}*{qty}\n└ {anime}"


def format_number(n: int) -> str:
    """Format number with commas."""
    return f"{n:,}"