# ============================================================
# 📁 File: utils/rarity.py  
# 📍 Location: telegram_card_bot/utils/rarity.py
# 📝 Description: Rarity system with probability-based selection
# ============================================================

import random
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Rarity:
    """
    Represents a card rarity level.
    
    Attributes:
        id: Unique identifier for the rarity
        name: Display name
        emoji: Emoji representation
        probability: Chance of getting this rarity (percentage)
        color_hex: Hex color code for display purposes
    """
    id: int
    name: str
    emoji: str
    probability: float
    color_hex: str = "#FFFFFF"
    
    def __str__(self) -> str:
        return f"{self.emoji} {self.name}"
    
    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "name": self.name,
            "emoji": self.emoji,
            "probability": self.probability,
            "color_hex": self.color_hex
        }


# ============================================================
# 🎴 Complete Rarity Table
# ============================================================

RARITY_TABLE: dict[int, Rarity] = {
    1: Rarity(
        id=1,
        name="Normal",
        emoji="🛞",
        probability=50.0,
        color_hex="#808080"  # Gray
    ),
    2: Rarity(
        id=2,
        name="Common",
        emoji="🌀",
        probability=20.0,
        color_hex="#00BFFF"  # Deep Sky Blue
    ),
    3: Rarity(
        id=3,
        name="Uncommon",
        emoji="🥏",
        probability=10.0,
        color_hex="#32CD32"  # Lime Green
    ),
    4: Rarity(
        id=4,
        name="Rare",
        emoji="☘️",
        probability=7.0,
        color_hex="#228B22"  # Forest Green
    ),
    5: Rarity(
        id=5,
        name="Epic",
        emoji="🫧",
        probability=4.0,
        color_hex="#9932CC"  # Dark Orchid
    ),
    6: Rarity(
        id=6,
        name="Limited Edition",
        emoji="🎐",
        probability=2.0,
        color_hex="#FF69B4"  # Hot Pink
    ),
    7: Rarity(
        id=7,
        name="Platinum",
        emoji="❄️",
        probability=1.0,
        color_hex="#E5E4E2"  # Platinum
    ),
    8: Rarity(
        id=8,
        name="Emerald",
        emoji="💎",
        probability=0.5,
        color_hex="#50C878"  # Emerald
    ),
    9: Rarity(
        id=9,
        name="Crystal",
        emoji="🌸",
        probability=0.3,
        color_hex="#FFB7C5"  # Cherry Blossom Pink
    ),
    10: Rarity(
        id=10,
        name="Mythical",
        emoji="🧿",
        probability=0.15,
        color_hex="#4169E1"  # Royal Blue
    ),
    11: Rarity(
        id=11,
        name="Legendary",
        emoji="⚡",
        probability=0.05,
        color_hex="#FFD700"  # Gold
    ),
}


# ============================================================
# 🔧 Utility Functions
# ============================================================

def rarity_to_text(rarity_id: int) -> tuple[str, float, str]:
    """
    Convert a rarity ID to its text representation.
    
    Args:
        rarity_id: The rarity ID to look up
        
    Returns:
        Tuple of (name, probability, emoji)
        
    Raises:
        ValueError: If rarity_id is not valid
        
    Example:
        >>> name, prob, emoji = rarity_to_text(4)
        >>> print(f"{emoji} {name} ({prob}%)")
        ☘️ Rare (7.0%)
    """
    if rarity_id not in RARITY_TABLE:
        raise ValueError(f"Invalid rarity ID: {rarity_id}. Valid IDs: 1-{len(RARITY_TABLE)}")
    
    rarity = RARITY_TABLE[rarity_id]
    return rarity.name, rarity.probability, rarity.emoji


def get_random_rarity() -> int:
    """
    Get a random rarity ID based on probability weights.
    
    Uses weighted random selection where lower probability
    rarities are less likely to be selected.
    
    Returns:
        A rarity ID (1-11) selected based on probability
        
    Example:
        >>> rarity_id = get_random_rarity()
        >>> name, prob, emoji = rarity_to_text(rarity_id)
        >>> print(f"Got {emoji} {name}!")
    """
    # Extract IDs and probabilities
    rarity_ids = list(RARITY_TABLE.keys())
    probabilities = [RARITY_TABLE[rid].probability for rid in rarity_ids]
    
    # Normalize probabilities to sum to 100 (in case they don't)
    total_prob = sum(probabilities)
    if total_prob != 100:
        # Weights don't need to sum to 100 for random.choices
        pass
    
    # Use weighted random selection
    selected = random.choices(
        population=rarity_ids,
        weights=probabilities,
        k=1
    )[0]
    
    return selected


def get_rarity_emoji(rarity_id: int) -> str:
    """
    Get just the emoji for a rarity.
    
    Args:
        rarity_id: The rarity ID
        
    Returns:
        The emoji string
    """
    if rarity_id not in RARITY_TABLE:
        return "❓"
    return RARITY_TABLE[rarity_id].emoji


def get_rarity_name(rarity_id: int) -> str:
    """
    Get just the name for a rarity.
    
    Args:
        rarity_id: The rarity ID
        
    Returns:
        The rarity name
    """
    if rarity_id not in RARITY_TABLE:
        return "Unknown"
    return RARITY_TABLE[rarity_id].name


def get_rarity_by_name(name: str) -> Optional[Rarity]:
    """
    Find a rarity by its name (case-insensitive).
    
    Args:
        name: The rarity name to search for
        
    Returns:
        The Rarity object if found, None otherwise
    """
    name_lower = name.lower()
    for rarity in RARITY_TABLE.values():
        if rarity.name.lower() == name_lower:
            return rarity
    return None


def get_all_rarities() -> list[Rarity]:
    """
    Get all rarities sorted by ID.
    
    Returns:
        List of all Rarity objects
    """
    return [RARITY_TABLE[i] for i in sorted(RARITY_TABLE.keys())]


def format_rarity_display(rarity_id: int, include_probability: bool = False) -> str:
    """
    Format a rarity for display in messages.
    
    Args:
        rarity_id: The rarity ID
        include_probability: Whether to include the probability percentage
        
    Returns:
        Formatted string like "⚡ Legendary" or "⚡ Legendary (0.05%)"
    """
    if rarity_id not in RARITY_TABLE:
        return "❓ Unknown"
    
    rarity = RARITY_TABLE[rarity_id]
    base = f"{rarity.emoji} {rarity.name}"
    
    if include_probability:
        return f"{base} ({rarity.probability}%)"
    return base


def get_rarity_tier(rarity_id: int) -> str:
    """
    Get the tier classification for a rarity.
    
    Args:
        rarity_id: The rarity ID
        
    Returns:
        Tier string: "common", "rare", "epic", or "legendary"
    """
    if rarity_id <= 2:
        return "common"
    elif rarity_id <= 5:
        return "rare"
    elif rarity_id <= 8:
        return "epic"
    else:
        return "legendary"


def calculate_rarity_value(rarity_id: int, base_value: int = 100) -> int:
    """
    Calculate a value score based on rarity.
    
    Higher rarities have exponentially higher values.
    
    Args:
        rarity_id: The rarity ID
        base_value: Base value for Normal rarity
        
    Returns:
        Calculated value as integer
    """
    if rarity_id not in RARITY_TABLE:
        return base_value
    
    # Value increases exponentially with rarity
    # Normal (1) = 100, Legendary (11) ≈ 100,000
    multiplier = 2 ** (rarity_id - 1)
    return base_value * multiplier


# ============================================================
# 📊 Statistics Functions
# ============================================================

def get_rarity_statistics() -> dict:
    """
    Get statistics about the rarity system.
    
    Returns:
        Dictionary with stats about probabilities and tiers
    """
    total_probability = sum(r.probability for r in RARITY_TABLE.values())
    
    tier_stats = {
        "common": {"count": 0, "total_prob": 0.0},
        "rare": {"count": 0, "total_prob": 0.0},
        "epic": {"count": 0, "total_prob": 0.0},
        "legendary": {"count": 0, "total_prob": 0.0},
    }
    
    for rarity in RARITY_TABLE.values():
        tier = get_rarity_tier(rarity.id)
        tier_stats[tier]["count"] += 1
        tier_stats[tier]["total_prob"] += rarity.probability
    
    return {
        "total_rarities": len(RARITY_TABLE),
        "total_probability": total_probability,
        "tier_stats": tier_stats,
        "rarest": RARITY_TABLE[11].name,
        "most_common": RARITY_TABLE[1].name,
    }


def print_rarity_table() -> str:
    """
    Generate a formatted table of all rarities.
    
    Returns:
        Formatted string table for display
    """
    lines = [
        "╔════╦════════════════════╦═══════╦════════════╗",
        "║ ID ║ Rarity             ║ Emoji ║ Probability║",
        "╠════╬════════════════════╬═══════╬════════════╣",
    ]
    
    for rarity in get_all_rarities():
        lines.append(
            f"║ {rarity.id:2} ║ {rarity.name:<18} ║   {rarity.emoji}  ║ {rarity.probability:>9.2f}% ║"
        )
    
    lines.append("╚════╩════════════════════╩═══════╩════════════╝")
    
    return "\n".join(lines)


# ============================================================
# 🧪 Testing/Demo
# ============================================================

if __name__ == "__main__":
    # Demo the rarity system
    print("\n🎴 Rarity System Demo\n")
    print(print_rarity_table())
    
    print("\n📊 Simulating 10,000 pulls...\n")
    
    # Simulate pulls
    results: dict[int, int] = {i: 0 for i in range(1, 12)}
    num_simulations = 10000
    
    for _ in range(num_simulations):
        rarity_id = get_random_rarity()
        results[rarity_id] += 1
    
    print("Results:")
    print("-" * 50)
    for rarity_id, count in results.items():
        rarity = RARITY_TABLE[rarity_id]
        percentage = (count / num_simulations) * 100
        bar = "█" * int(percentage / 2)
        print(
            f"{rarity.emoji} {rarity.name:18} | "
            f"{count:5} ({percentage:5.2f}%) {bar}"
        )