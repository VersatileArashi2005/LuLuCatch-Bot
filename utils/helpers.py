"""
Helper functions for formatting messages and common operations.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from .rarity import RARITIES, rarity_to_text


def format_card_preview(card_data: Dict[str, Any]) -> str:
    """
    Format card data for preview display.
    
    Args:
        card_data: Dictionary containing card information
        
    Returns:
        Formatted preview string
    """
    character = card_data.get('character', 'Unknown')
    anime = card_data.get('anime', 'Unknown')
    rarity_id = card_data.get('rarity_id', 1)
    
    name, prob, emoji = rarity_to_text(rarity_id)
    
    preview = f"""
🔎 **Preview**

💎 **Character:** {character}
🎬 **Anime:** {anime}
⭐ **Rarity:** {emoji} {name} ({prob}%)

━━━━━━━━━━━━━━━━━
"""
    return preview


def format_card_detail(card: Dict[str, Any], owner_count: int = 0) -> str:
    """
    Format detailed card information.
    
    Args:
        card: Card data dictionary
        owner_count: Number of users who own this card
        
    Returns:
        Formatted detail string
    """
    name, prob, emoji = rarity_to_text(card.get('rarity_id', 1))
    
    detail = f"""
🎴 **Card Information**

🆔 **ID:** `{card.get('id', 'N/A')}`
💎 **Character:** {card.get('character', 'Unknown')}
🎬 **Anime:** {card.get('anime', 'Unknown')}
⭐ **Rarity:** {emoji} {name} ({prob}%)
👥 **Owners:** {owner_count} user(s)
📅 **Added:** {card.get('created_at', 'Unknown')}

━━━━━━━━━━━━━━━━━
"""
    return detail


def format_catch_message(card: Dict[str, Any], user_name: str) -> str:
    """
    Format the catch success message.
    
    Args:
        card: Card data dictionary
        user_name: Name of the user who caught the card
        
    Returns:
        Formatted catch message
    """
    name, prob, emoji = rarity_to_text(card.get('rarity_id', 1))
    rarity = RARITIES.get(card.get('rarity_id', 1))
    
    # Special effects for rare cards
    if card.get('rarity_id', 1) >= 9:
        effect = "✨🌟💫"
    elif card.get('rarity_id', 1) >= 6:
        effect = "✨"
    else:
        effect = ""
    
    message = f"""
{effect}🎉 **CARD CAUGHT!** {effect}

👤 **{user_name}** caught:

💎 **{card.get('character', 'Unknown')}**
🎬 From: {card.get('anime', 'Unknown')}
⭐ Rarity: {emoji} {name}

🎴 Card ID: `{card.get('id', 'N/A')}`
━━━━━━━━━━━━━━━━━
"""
    return message


def format_cooldown_message(remaining: timedelta) -> str:
    """
    Format cooldown remaining message.
    
    Args:
        remaining: Remaining time as timedelta
        
    Returns:
        Formatted cooldown message
    """
    hours, remainder = divmod(int(remaining.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 and hours == 0:
        parts.append(f"{seconds}s")
    
    time_str = " ".join(parts) if parts else "a moment"
    
    return f"""
⏳ **Cooldown Active!**

You've already caught a card recently.
Please wait **{time_str}** before catching again.

💡 Tip: Use /harem to view your collection while waiting!
"""


def format_harem_page(cards: List[Dict[str, Any]], page: int, 
                       total_pages: int, total_cards: int) -> str:
    """
    Format a page of harem/collection.
    
    Args:
        cards: List of card dictionaries
        page: Current page number
        total_pages: Total pages
        total_cards: Total cards in collection
        
    Returns:
        Formatted harem page
    """
    header = f"""
🎒 **Your Collection**
📊 Total: {total_cards} cards | Page {page + 1}/{total_pages}

━━━━━━━━━━━━━━━━━
"""
    
    lines = [header]
    
    for card in cards:
        name, _, emoji = rarity_to_text(card.get('rarity_id', 1))
        lines.append(
            f"{emoji} `{card.get('id', '?')}` | "
            f"**{card.get('character', 'Unknown')[:20]}** "
            f"({card.get('anime', 'Unknown')[:15]})"
        )
    
    lines.append("\n━━━━━━━━━━━━━━━━━")
    
    return "\n".join(lines)


def format_stats(stats: Dict[str, Any]) -> str:
    """
    Format bot statistics.
    
    Args:
        stats: Statistics dictionary
        
    Returns:
        Formatted stats message
    """
    return f"""
📊 **Bot Statistics**

👥 **Users:**
   • Total: {stats.get('total_users', 0)}
   • Active Today: {stats.get('active_today', 0)}

🎴 **Cards:**
   • Total Cards: {stats.get('total_cards', 0)}
   • Total Anime: {stats.get('total_anime', 0)}
   • Total Characters: {stats.get('total_characters', 0)}

📈 **Activity:**
   • Catches Today: {stats.get('catches_today', 0)}
   • Total Catches: {stats.get('total_catches', 0)}

🏠 **Groups:**
   • Registered: {stats.get('total_groups', 0)}

━━━━━━━━━━━━━━━━━
🕐 Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""


def format_user_profile(user: Dict[str, Any], card_count: int) -> str:
    """
    Format user profile.
    
    Args:
        user: User data dictionary
        card_count: Number of cards owned
        
    Returns:
        Formatted profile message
    """
    role_emoji = {
        'user': '👤',
        'uploader': '📤',
        'admin': '🛡️',
        'dev': '💻',
        'owner': '👑'
    }
    
    role = user.get('role', 'user')
    emoji = role_emoji.get(role, '👤')
    
    return f"""
👤 **User Profile**

🆔 **ID:** `{user.get('user_id', 'N/A')}`
📛 **Name:** {user.get('name', 'Unknown')}
{emoji} **Role:** {role.title()}
🎴 **Cards:** {card_count}
📅 **Joined:** {user.get('created_at', 'Unknown')}

━━━━━━━━━━━━━━━━━
"""


def escape_markdown(text: str) -> str:
    """
    Escape markdown special characters.
    
    Args:
        text: Text to escape
        
    Returns:
        Escaped text
    """
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text