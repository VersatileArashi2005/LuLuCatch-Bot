"""
Rarity system for the Telegram Card Bot.
Defines all rarities with their properties and selection logic.
"""

import random
from typing import Tuple, Optional, Dict, List
from dataclasses import dataclass


@dataclass
class Rarity:
    """Rarity data class."""
    id: int
    name: str
    emoji: str
    probability: float  # Percentage
    color: str  # For visual representation


# ===== Full Rarity Table =====
RARITIES: Dict[int, Rarity] = {
    1: Rarity(1, "Normal", "🛞", 30.0, "⬜"),
    2: Rarity(2, "Common", "🌀", 25.0, "🟦"),
    3: Rarity(3, "Uncommon", "🥏", 20.0, "🟩"),
    4: Rarity(4, "Rare", "☘️", 15.0, "🟪"),
    5: Rarity(5, "Epic", "🫧", 10.0, "🟧"),
    6: Rarity(6, "Limited Edition", "🎐", 7.0, "🌸"),
    7: Rarity(7, "Platinum", "❄️", 5.0, "⬛"),
    8: Rarity(8, "Emerald", "💎", 3.0, "💚"),
    9: Rarity(9, "Crystal", "🌸", 2.0, "💗"),
    10: Rarity(10, "Mythical", "🧿", 1.5, "🔮"),
    11: Rarity(11, "Legendary", "⚡", 0.5, "⭐"),
}


def rarity_to_text(rarity_id: int) -> Tuple[str, float, str]:
    """
    Convert rarity ID to readable format.
    
    Args:
        rarity_id: The rarity ID (1-11)
        
    Returns:
        Tuple of (name, probability, emoji)
    """
    rarity = RARITIES.get(rarity_id)
    if rarity:
        return (rarity.name, rarity.probability, rarity.emoji)
    return ("Unknown", 0.0, "❓")


def get_rarity_display(rarity_id: int) -> str:
    """
    Get formatted rarity display string.
    
    Args:
        rarity_id: The rarity ID
        
    Returns:
        Formatted string like "⚡ Legendary (0.5%)"
    """
    name, prob, emoji = rarity_to_text(rarity_id)
    return f"{emoji} {name} ({prob}%)"


def get_random_rarity() -> int:
    """
    Get a random rarity based on probability weights.
    
    Returns:
        Rarity ID (1-11)
    """
    # Create weighted selection
    rarities = list(RARITIES.values())
    weights = [r.probability for r in rarities]
    
    selected = random.choices(rarities, weights=weights, k=1)[0]
    return selected.id


def get_rarity_by_name(name: str) -> Optional[Rarity]:
    """
    Find rarity by name (case-insensitive).
    
    Args:
        name: Rarity name to search
        
    Returns:
        Rarity object or None
    """
    name_lower = name.lower()
    for rarity in RARITIES.values():
        if rarity.name.lower() == name_lower:
            return rarity
    return None


def get_all_rarities_text() -> str:
    """
    Get formatted text of all rarities.
    
    Returns:
        Formatted string with all rarities
    """
    lines = ["🎴 **Rarity Tiers**\n"]
    for rarity in RARITIES.values():
        lines.append(f"{rarity.emoji} {rarity.name} - {rarity.probability}%")
    return "\n".join(lines)


def get_rarity_tier(rarity_id: int) -> str:
    """
    Get tier classification for a rarity.
    
    Args:
        rarity_id: The rarity ID
        
    Returns:
        Tier name (Common, Rare, Ultra Rare, etc.)
    """
    if rarity_id <= 3:
        return "Common Tier"
    elif rarity_id <= 5:
        return "Rare Tier"
    elif rarity_id <= 8:
        return "Ultra Rare Tier"
    else:
        return "Legendary Tier"