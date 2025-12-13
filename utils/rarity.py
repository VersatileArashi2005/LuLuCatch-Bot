# ============================================================
# 📁 File: utils/rarity.py  
# 📍 Location: telegram_card_bot/utils/rarity.py
# 📝 Description: Rarity system with updated emojis
# ============================================================

import random
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Rarity:
    """Represents a card rarity level."""
    id: int
    name: str
    emoji: str
    probability: float
    color_hex: str = "#FFFFFF"
    
    def __str__(self) -> str:
        return f"{self.emoji} {self.name}"
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "emoji": self.emoji,
            "probability": self.probability,
            "color_hex": self.color_hex
        }


# ============================================================
# 🎴 Updated Rarity Table
# ============================================================

RARITY_TABLE: dict[int, Rarity] = {
    1: Rarity(
        id=1,
        name="Normal",
        emoji="☘️",
        probability=50.0,
        color_hex="#808080"
    ),
    2: Rarity(
        id=2,
        name="Common",
        emoji="⚡",
        probability=20.0,
        color_hex="#00BFFF"
    ),
    3: Rarity(
        id=3,
        name="Uncommon",
        emoji="⭐",
        probability=10.0,
        color_hex="#32CD32"
    ),
    4: Rarity(
        id=4,
        name="Rare",
        emoji="💠",
        probability=7.0,
        color_hex="#228B22"
    ),
    5: Rarity(
        id=5,
        name="Epic",
        emoji="🔮",
        probability=4.0,
        color_hex="#9932CC"
    ),
    6: Rarity(
        id=6,
        name="Limited Epic",
        emoji="🧿",
        probability=2.0,
        color_hex="#FF69B4"
    ),
    7: Rarity(
        id=7,
        name="Platinum",
        emoji="🪩",
        probability=1.0,
        color_hex="#E5E4E2"
    ),
    8: Rarity(
        id=8,
        name="Emerald",
        emoji="💠",
        probability=0.5,
        color_hex="#50C878"
    ),
    9: Rarity(
        id=9,
        name="Crystal",
        emoji="❄️",
        probability=0.3,
        color_hex="#A7D8DE"
    ),
    10: Rarity(
        id=10,
        name="Mythical",
        emoji="🏵️",
        probability=0.15,
        color_hex="#4169E1"
    ),
    11: Rarity(
        id=11,
        name="Legendary",
        emoji="🌸",
        probability=0.05,
        color_hex="#FFD700"
    ),
}


# ============================================================
# 🔧 Utility Functions
# ============================================================

def rarity_to_text(rarity_id: int) -> tuple[str, float, str]:
    """Convert rarity ID to (name, probability, emoji)."""
    if rarity_id not in RARITY_TABLE:
        raise ValueError(f"Invalid rarity ID: {rarity_id}")
    
    rarity = RARITY_TABLE[rarity_id]
    return rarity.name, rarity.probability, rarity.emoji


def get_random_rarity() -> int:
    """Get random rarity based on probability weights."""
    rarity_ids = list(RARITY_TABLE.keys())
    probabilities = [RARITY_TABLE[rid].probability for rid in rarity_ids]
    
    selected = random.choices(
        population=rarity_ids,
        weights=probabilities,
        k=1
    )[0]
    
    return selected


def get_rarity_emoji(rarity_id: int) -> str:
    """Get emoji for a rarity."""
    if rarity_id not in RARITY_TABLE:
        return "❓"
    return RARITY_TABLE[rarity_id].emoji


def get_rarity_name(rarity_id: int) -> str:
    """Get name for a rarity."""
    if rarity_id not in RARITY_TABLE:
        return "Unknown"
    return RARITY_TABLE[rarity_id].name


def get_rarity_by_name(name: str) -> Optional[Rarity]:
    """Find rarity by name (case-insensitive)."""
    name_lower = name.lower()
    for rarity in RARITY_TABLE.values():
        if rarity.name.lower() == name_lower:
            return rarity
    return None


def get_all_rarities() -> list[Rarity]:
    """Get all rarities sorted by ID."""
    return [RARITY_TABLE[i] for i in sorted(RARITY_TABLE.keys())]


def format_rarity_display(rarity_id: int, include_probability: bool = False) -> str:
    """Format rarity for display."""
    if rarity_id not in RARITY_TABLE:
        return "❓ Unknown"
    
    rarity = RARITY_TABLE[rarity_id]
    base = f"{rarity.emoji} {rarity.name}"
    
    if include_probability:
        return f"{base} ({rarity.probability}%)"
    return base


def get_rarity_tier(rarity_id: int) -> str:
    """Get tier classification for a rarity."""
    if rarity_id <= 2:
        return "common"
    elif rarity_id <= 5:
        return "rare"
    elif rarity_id <= 8:
        return "epic"
    else:
        return "legendary"


def calculate_rarity_value(rarity_id: int, base_value: int = 100) -> int:
    """Calculate value score based on rarity."""
    if rarity_id not in RARITY_TABLE:
        return base_value
    
    multiplier = 2 ** (rarity_id - 1)
    return base_value * multiplier


def get_rarity_statistics() -> dict:
    """Get statistics about the rarity system."""
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
    """Generate formatted table of all rarities."""
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