# ============================================================
# 📁 File: utils/ui.py
# 📍 Location: telegram_card_bot/utils/ui.py
# 📝 Description: Modern UI components using Telegram-native features
# ============================================================

"""
LuLuCatch UI Components
Clean, modern UI helpers without ASCII borders.
Uses inline keyboards and Telegram formatting.
"""

from typing import Optional, List, Tuple, Any
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReactionTypeEmoji

from utils.constants import (
    RARITY_EMOJIS,
    RARITY_NAMES,
    Templates,
    ButtonLabels,
    CallbackPrefixes,
    Pagination,
    get_medal,
    format_number,
)
from utils.rarity import (
    get_rarity,
    get_catch_reaction,
    get_catch_celebration_text,
    should_celebrate,
)


# ============================================================
# 🎴 Card Display Functions
# ============================================================

def format_card_caption(
    character: str,
    anime: str,
    rarity_id: int,
    card_id: int,
    probability: Optional[float] = None,
    owner_count: Optional[int] = None,
    quantity: Optional[int] = None,
    extra_info: Optional[str] = None,
) -> str:
    """
    Format a clean card caption for display.
    
    Args:
        character: Character name
        anime: Anime name
        rarity_id: Rarity ID (1-11)
        card_id: Card ID
        probability: Optional drop rate
        owner_count: Optional number of owners
        quantity: Optional quantity owned
        extra_info: Optional extra text to append
    
    Returns:
        Formatted caption string
    """
    emoji = RARITY_EMOJIS.get(rarity_id, "❓")
    name = RARITY_NAMES.get(rarity_id, "Unknown")
    
    lines = [
        f"{emoji} *{character}*",
        "",
        f"🎬 {anime}",
        f"{emoji} {name}",
        f"🆔 `#{card_id}`",
    ]
    
    if probability is not None:
        lines.append(f"📊 {probability}% drop rate")
    
    if owner_count is not None:
        lines.append(f"👥 {format_number(owner_count)} owners")
    
    if quantity is not None and quantity > 1:
        lines.insert(1, f"×{quantity} owned")
    
    if extra_info:
        lines.append("")
        lines.append(extra_info)
    
    return "\n".join(lines)


def format_catch_message(
    user_name: str,
    character: str,
    anime: str,
    rarity_id: int,
    card_id: int,
    is_new: bool = False,
) -> str:
    """
    Format catch success message based on rarity.
    
    Args:
        user_name: Name of user who caught
        character: Character name
        anime: Anime name
        rarity_id: Rarity ID
        card_id: Card ID
        is_new: Whether this is a new card for the user
    
    Returns:
        Formatted catch message
    """
    emoji = RARITY_EMOJIS.get(rarity_id, "❓")
    rarity_name = RARITY_NAMES.get(rarity_id, "Unknown")
    rarity = get_rarity(rarity_id)
    probability = rarity.probability if rarity else 0
    
    # Get celebration text for rare+ cards
    celebration = get_catch_celebration_text(rarity_id)
    
    if rarity_id == 11:
        # Legendary - maximum celebration
        return (
            f"🎊 {emoji} *LEGENDARY CATCH!* {emoji} 🎊\n"
            f"\n"
            f"*{user_name}* caught *{character}*!\n"
            f"\n"
            f"🎬 {anime}\n"
            f"{emoji} {rarity_name} ({probability}%)\n"
            f"🆔 `#{card_id}`\n"
            f"\n"
            f"🏆 *Congratulations!*"
        )
    elif rarity_id >= 9:
        # Mythical/Crystal - big celebration
        return (
            f"✨ {emoji} *{rarity_name.upper()} CATCH!* {emoji} ✨\n"
            f"\n"
            f"*{user_name}* caught *{character}*!\n"
            f"\n"
            f"🎬 {anime}\n"
            f"{emoji} {rarity_name} ({probability}%)\n"
            f"🆔 `#{card_id}`"
        )
    elif rarity_id >= 7:
        # Platinum/Emerald - celebration
        return (
            f"✨ *Rare Catch!* ✨\n"
            f"\n"
            f"*{user_name}* caught {emoji} *{character}*!\n"
            f"\n"
            f"🎬 {anime}\n"
            f"{emoji} {rarity_name}\n"
            f"🆔 `#{card_id}`"
        )
    elif is_new:
        # New card for user
        return (
            f"🆕 *New Card!*\n"
            f"\n"
            f"*{user_name}* caught {emoji} *{character}*!\n"
            f"\n"
            f"🎬 {anime}\n"
            f"{emoji} {rarity_name}\n"
            f"🆔 `#{card_id}`"
        )
    else:
        # Standard catch
        return (
            f"{emoji} *{user_name}* caught *{character}*!\n"
            f"\n"
            f"🎬 {anime}\n"
            f"{emoji} {rarity_name}\n"
            f"🆔 `#{card_id}`"
        )


def format_spawn_message(
    character: str,
    anime: str,
    rarity_id: int,
) -> str:
    """Format card spawn announcement."""
    emoji = RARITY_EMOJIS.get(rarity_id, "❓")
    
    return (
        f"{emoji} *A wild character appeared!*\n"
        f"\n"
        f"Quick! Type /catch to battle!"
    )


def format_drop_message(
    character: str,
    anime: str,
    rarity_id: int,
    card_id: int,
) -> str:
    """Format card drop announcement for drop system."""
    emoji = RARITY_EMOJIS.get(rarity_id, "❓")
    rarity_name = RARITY_NAMES.get(rarity_id, "Unknown")
    
    if rarity_id >= 9:
        # Rare drop announcement
        return (
            f"✨ *A rare character dropped!* ✨\n"
            f"\n"
            f"{emoji} *{character}*\n"
            f"🎬 {anime}\n"
            f"{emoji} {rarity_name}\n"
            f"\n"
            f"Type /lulucatch to claim!"
        )
    else:
        return (
            f"🎴 *A character dropped!*\n"
            f"\n"
            f"{emoji} *{character}*\n"
            f"🎬 {anime}\n"
            f"\n"
            f"Type /lulucatch to claim!"
        )


# ============================================================
# ⌨️ Inline Keyboard Builders
# ============================================================

def build_pagination_keyboard(
    current_page: int,
    total_pages: int,
    callback_prefix: str,
    extra_buttons: Optional[List[List[InlineKeyboardButton]]] = None,
) -> InlineKeyboardMarkup:
    """
    Build a pagination keyboard.
    
    Args:
        current_page: Current page number (1-indexed)
        total_pages: Total number of pages
        callback_prefix: Prefix for callback data (e.g., "harem_page:")
        extra_buttons: Optional extra button rows to add
    
    Returns:
        InlineKeyboardMarkup with pagination
    """
    buttons = []
    
    # Add extra buttons first if provided
    if extra_buttons:
        buttons.extend(extra_buttons)
    
    # Build pagination row
    if total_pages > 1:
        nav_row = []
        
        # Previous button
        if current_page > 1:
            nav_row.append(InlineKeyboardButton(
                ButtonLabels.PREV,
                callback_data=f"{callback_prefix}{current_page - 1}"
            ))
        
        # Page indicator
        nav_row.append(InlineKeyboardButton(
            f"{current_page}/{total_pages}",
            callback_data="noop"
        ))
        
        # Next button
        if current_page < total_pages:
            nav_row.append(InlineKeyboardButton(
                ButtonLabels.NEXT,
                callback_data=f"{callback_prefix}{current_page + 1}"
            ))
        
        buttons.append(nav_row)
    
    return InlineKeyboardMarkup(buttons)


def build_harem_keyboard(
    current_page: int,
    total_pages: int,
    cards: List[Any],
    user_id: int,
    rarity_filter: Optional[int] = None,
) -> InlineKeyboardMarkup:
    """
    Build keyboard for harem display.
    
    Args:
        current_page: Current page
        total_pages: Total pages
        cards: List of card records on current page
        user_id: User ID for callback validation
        rarity_filter: Optional active rarity filter
    
    Returns:
        InlineKeyboardMarkup for harem
    """
    buttons = []
    
    # Card buttons (2 per row)
    card_row = []
    for card in cards:
        emoji = RARITY_EMOJIS.get(card["rarity"], "❓")
        card_row.append(InlineKeyboardButton(
            f"{emoji} #{card['card_id']}",
            callback_data=f"{CallbackPrefixes.HAREM_CARD}{card['card_id']}"
        ))
        
        if len(card_row) == 3:
            buttons.append(card_row)
            card_row = []
    
    if card_row:
        buttons.append(card_row)
    
    # Filter row
    filter_row = [
        InlineKeyboardButton(
            "📋 All" if not rarity_filter else "📋",
            callback_data=f"{CallbackPrefixes.HAREM_FILTER}all"
        ),
        InlineKeyboardButton(
            "💎 Rare+" if rarity_filter != 4 else "💎 ✓",
            callback_data=f"{CallbackPrefixes.HAREM_FILTER}4"
        ),
        InlineKeyboardButton(
            "🌸 Legend" if rarity_filter != 11 else "🌸 ✓",
            callback_data=f"{CallbackPrefixes.HAREM_FILTER}11"
        ),
    ]
    buttons.append(filter_row)
    
    # Pagination row
    if total_pages > 1:
        nav_row = []
        
        if current_page > 1:
            nav_row.append(InlineKeyboardButton(
                ButtonLabels.PREV,
                callback_data=f"{CallbackPrefixes.HAREM_PAGE}{current_page - 1}"
            ))
        
        nav_row.append(InlineKeyboardButton(
            f"{current_page}/{total_pages}",
            callback_data="noop"
        ))
        
        if current_page < total_pages:
            nav_row.append(InlineKeyboardButton(
                ButtonLabels.NEXT,
                callback_data=f"{CallbackPrefixes.HAREM_PAGE}{current_page + 1}"
            ))
        
        buttons.append(nav_row)
    
    # Close button
    buttons.append([InlineKeyboardButton(
        ButtonLabels.CLOSE,
        callback_data="harem_close"
    )])
    
    return InlineKeyboardMarkup(buttons)


def build_card_detail_keyboard(
    card_id: int,
    is_favorite: bool = False,
    can_trade: bool = True,
    show_back: bool = True,
) -> InlineKeyboardMarkup:
    """Build keyboard for card detail view."""
    buttons = []
    
    # Action row
    action_row = []
    
    # Favorite toggle
    if is_favorite:
        action_row.append(InlineKeyboardButton(
            "💔 Unfavorite",
            callback_data=f"{CallbackPrefixes.CARD_FAV}{card_id}"
        ))
    else:
        action_row.append(InlineKeyboardButton(
            "❤️ Favorite",
            callback_data=f"{CallbackPrefixes.CARD_FAV}{card_id}"
        ))
    
    # Trade button
    if can_trade:
        action_row.append(InlineKeyboardButton(
            "🔄 Trade",
            callback_data=f"{CallbackPrefixes.CARD_TRADE}{card_id}"
        ))
    
    if action_row:
        buttons.append(action_row)
    
    # Back button
    if show_back:
        buttons.append([InlineKeyboardButton(
            ButtonLabels.BACK,
            callback_data=f"{CallbackPrefixes.HAREM_PAGE}1"
        )])
    
    return InlineKeyboardMarkup(buttons)


def build_battle_keyboard(
    card_id: int,
    user_id: int,
    session_id: str,
) -> InlineKeyboardMarkup:
    """Build keyboard for battle actions."""
    buttons = [
        [
            InlineKeyboardButton(
                ButtonLabels.ATTACK,
                callback_data=f"battle:attack:{session_id}"
            ),
            InlineKeyboardButton(
                ButtonLabels.DEFEND,
                callback_data=f"battle:defend:{session_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                ButtonLabels.SPECIAL,
                callback_data=f"battle:special:{session_id}"
            ),
        ],
    ]
    
    return InlineKeyboardMarkup(buttons)


def build_trade_keyboard(
    trade_id: int,
    for_recipient: bool = True,
) -> InlineKeyboardMarkup:
    """Build keyboard for trade actions."""
    if for_recipient:
        buttons = [
            [
                InlineKeyboardButton(
                    ButtonLabels.ACCEPT,
                    callback_data=f"{CallbackPrefixes.TRADE_ACCEPT}{trade_id}"
                ),
                InlineKeyboardButton(
                    ButtonLabels.REJECT,
                    callback_data=f"{CallbackPrefixes.TRADE_REJECT}{trade_id}"
                ),
            ],
        ]
    else:
        buttons = [
            [
                InlineKeyboardButton(
                    ButtonLabels.CANCEL,
                    callback_data=f"{CallbackPrefixes.TRADE_CANCEL}{trade_id}"
                ),
            ],
        ]
    
    return InlineKeyboardMarkup(buttons)


def build_confirm_keyboard(
    confirm_callback: str,
    cancel_callback: str,
) -> InlineKeyboardMarkup:
    """Build a simple confirm/cancel keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                ButtonLabels.CONFIRM,
                callback_data=confirm_callback
            ),
            InlineKeyboardButton(
                ButtonLabels.CANCEL,
                callback_data=cancel_callback
            ),
        ],
    ])


def build_leaderboard_keyboard(
    current_page: int,
    total_pages: int,
    current_type: str = "catches",
) -> InlineKeyboardMarkup:
    """Build keyboard for leaderboard navigation."""
    buttons = []
    
    # Type selector row
    type_row = [
        InlineKeyboardButton(
            "🎯 Catches" + (" ✓" if current_type == "catches" else ""),
            callback_data=f"{CallbackPrefixes.LB_TYPE}catches"
        ),
        InlineKeyboardButton(
            "💰 Coins" + (" ✓" if current_type == "coins" else ""),
            callback_data=f"{CallbackPrefixes.LB_TYPE}coins"
        ),
        InlineKeyboardButton(
            "🎴 Cards" + (" ✓" if current_type == "cards" else ""),
            callback_data=f"{CallbackPrefixes.LB_TYPE}cards"
        ),
    ]
    buttons.append(type_row)
    
    # Pagination
    if total_pages > 1:
        nav_row = []
        
        if current_page > 1:
            nav_row.append(InlineKeyboardButton(
                ButtonLabels.PREV,
                callback_data=f"{CallbackPrefixes.LB_PAGE}{current_page - 1}"
            ))
        
        nav_row.append(InlineKeyboardButton(
            f"{current_page}/{total_pages}",
            callback_data="noop"
        ))
        
        if current_page < total_pages:
            nav_row.append(InlineKeyboardButton(
                ButtonLabels.NEXT,
                callback_data=f"{CallbackPrefixes.LB_PAGE}{current_page + 1}"
            ))
        
        buttons.append(nav_row)
    
    return InlineKeyboardMarkup(buttons)


# ============================================================
# 🎉 Reaction Helpers
# ============================================================

def get_catch_reactions(rarity_id: int) -> List[ReactionTypeEmoji]:
    """
    Get Telegram reaction objects for a catch.
    
    Args:
        rarity_id: Rarity of the caught card
    
    Returns:
        List of ReactionTypeEmoji objects
    """
    reaction_emoji = get_catch_reaction(rarity_id)
    return [ReactionTypeEmoji(emoji=reaction_emoji)]


async def send_catch_reaction(message, rarity_id: int) -> bool:
    """
    Send a reaction to a message based on catch rarity.
    
    Args:
        message: Telegram message object
        rarity_id: Rarity of caught card
    
    Returns:
        True if reaction was sent successfully
    """
    try:
        reactions = get_catch_reactions(rarity_id)
        await message.set_reaction(reactions)
        return True
    except Exception:
        # Reactions might not be supported in all chats
        return False


# ============================================================
# 📝 List Formatting
# ============================================================

def format_harem_list(
    cards: List[Any],
    page: int,
    total_pages: int,
    total_cards: int,
    unique_cards: int,
    user_name: str,
) -> str:
    """
    Format harem list display.
    
    Args:
        cards: List of card records
        page: Current page
        total_pages: Total pages
        total_cards: Total cards owned
        unique_cards: Unique cards owned
        user_name: User's name
    
    Returns:
        Formatted harem text
    """
    lines = [
        f"🎴 *{user_name}'s Harem*",
        f"📊 {total_cards} cards ({unique_cards} unique)",
        "",
    ]
    
    if not cards:
        lines.append("_No cards found._")
    else:
        for card in cards:
            emoji = RARITY_EMOJIS.get(card["rarity"], "❓")
            qty = f" ×{card['quantity']}" if card.get("quantity", 1) > 1 else ""
            fav = " ❤️" if card.get("is_favorite") else ""
            
            lines.append(f"{emoji} *{card['character_name']}*{qty}{fav}")
            lines.append(f"└ {card['anime']} • `#{card['card_id']}`")
    
    return "\n".join(lines)


def format_leaderboard(
    users: List[Any],
    lb_type: str = "catches",
    page: int = 1,
) -> str:
    """
    Format leaderboard display.
    
    Args:
        users: List of user records
        lb_type: Type of leaderboard
        page: Current page
    
    Returns:
        Formatted leaderboard text
    """
    type_titles = {
        "catches": "🎯 Top Catchers",
        "coins": "💰 Richest Players",
        "cards": "🎴 Biggest Collections",
    }
    
    type_fields = {
        "catches": "total_catches",
        "coins": "coins",
        "cards": "total_catches",  # Will be replaced with collection count
    }
    
    title = type_titles.get(lb_type, "🏆 Leaderboard")
    field = type_fields.get(lb_type, "total_catches")
    
    lines = [f"*{title}*", ""]
    
    start_rank = (page - 1) * Pagination.LEADERBOARD_PER_PAGE + 1
    
    for i, user in enumerate(users):
        rank = start_rank + i
        medal = get_medal(rank)
        
        name = user.get("first_name") or user.get("username") or f"User {user['user_id']}"
        value = user.get(field, 0)
        
        lines.append(f"{medal} *{name}* — {format_number(value)}")
    
    if not users:
        lines.append("_No data yet._")
    
    return "\n".join(lines)


def format_trade_message(
    from_user_name: str,
    to_user_name: str,
    offered_card: dict,
    requested_card: Optional[dict] = None,
) -> str:
    """Format trade request message."""
    offer_emoji = RARITY_EMOJIS.get(offered_card.get("rarity", 1), "❓")
    
    lines = [
        "🔄 *Trade Request*",
        "",
        f"From: *{from_user_name}*",
        f"To: *{to_user_name}*",
        "",
        "📤 *Offering:*",
        f"{offer_emoji} {offered_card.get('character_name', 'Unknown')}",
        f"└ {offered_card.get('anime', 'Unknown')}",
    ]
    
    if requested_card:
        req_emoji = RARITY_EMOJIS.get(requested_card.get("rarity", 1), "❓")
        lines.extend([
            "",
            "📥 *Requesting:*",
            f"{req_emoji} {requested_card.get('character_name', 'Unknown')}",
            f"└ {requested_card.get('anime', 'Unknown')}",
        ])
    else:
        lines.extend([
            "",
            "📥 *Requesting:* Any card",
        ])
    
    return "\n".join(lines)


# ============================================================
# ℹ️ Info Display Functions
# ============================================================

def format_bot_stats(stats: dict) -> str:
    """Format bot statistics display."""
    return (
        f"📊 *LuLuCatch Statistics*\n"
        f"\n"
        f"👥 Users: {format_number(stats.get('total_users', 0))}\n"
        f"🎴 Cards: {format_number(stats.get('total_cards', 0))}\n"
        f"🎯 Catches: {format_number(stats.get('total_catches', 0))}\n"
        f"💬 Groups: {format_number(stats.get('active_groups', 0))}"
    )


def format_user_stats(
    user_name: str,
    total_cards: int,
    unique_cards: int,
    coins: int,
    level: int,
    xp: int,
) -> str:
    """Format user statistics display."""
    return (
        f"👤 *{user_name}'s Profile*\n"
        f"\n"
        f"🎴 Cards: {total_cards} ({unique_cards} unique)\n"
        f"💰 Coins: {format_number(coins)}\n"
        f"⭐ Level: {level}\n"
        f"✨ XP: {format_number(xp)}"
    )


def format_cooldown_message(seconds_left: int) -> str:
    """Format cooldown message."""
    if seconds_left >= 60:
        minutes = seconds_left // 60
        secs = seconds_left % 60
        time_str = f"{minutes}m {secs}s"
    else:
        time_str = f"{seconds_left}s"
    
    return f"⏳ Cooldown! Wait *{time_str}* before catching again."


def format_error(error_type: str = "generic") -> str:
    """Get formatted error message."""
    errors = {
        "generic": "❌ Something went wrong. Please try again.",
        "no_card": "❌ Card not found.",
        "no_permission": "🚫 You don't have permission for this.",
        "database": "🔌 Database unavailable. Try again later.",
        "cooldown": "⏳ Please wait before trying again.",
        "not_owner": "❌ You don't own this card.",
        "invalid_trade": "❌ Invalid trade request.",
    }
    return errors.get(error_type, errors["generic"])