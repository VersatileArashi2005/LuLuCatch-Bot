# ============================================================
# 📁 File: utils/rarity.py
# 📍 Location: telegram_card_bot/utils/rarity.py
# 📝 Description: Enhanced rarity system with reactions & celebrations
# ============================================================

import random
from dataclasses import dataclass
from typing import Optional, List, Tuple

from utils.constants import (
    RARITY_EMOJIS,
    RARITY_NAMES,
    PRIMARY_CATCH_REACTION,
    CATCH_REACTIONS,
)


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
    
    @property
    def display(self) -> str:
        """Clean display format."""
        return f"{self.emoji} {self.name}"
    
    @property
    def display_with_rate(self) -> str:
        """Display with drop rate."""
        return f"{self.emoji} {self.name} ({self.probability}%)"
    
    @property
    def tier(self) -> str:
        """Get tier classification."""
        if self.id <= 2:
            return "common"
        elif self.id <= 5:
            return "rare"
        elif self.id <= 8:
            return "epic"
        else:
            return "legendary"
    
    @property
    def is_rare(self) -> bool:
        """Check if this is a rare+ card."""
        return self.id >= 4
    
    @property
    def is_epic(self) -> bool:
        """Check if this is epic+ tier."""
        return self.id >= 5
    
    @property
    def is_legendary_tier(self) -> bool:
        """Check if this is legendary tier (9+)."""
        return self.id >= 9
    
    @property
    def catch_reaction(self) -> str:
        """Get Telegram reaction emoji for catching this rarity."""
        return PRIMARY_CATCH_REACTION.get(self.id, "👍")
    
    @property
    def celebration_reactions(self) -> List[str]:
        """Get all celebration reactions for this rarity."""
        return CATCH_REACTIONS.get(self.id, ["👍"])
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "emoji": self.emoji,
            "probability": self.probability,
            "color_hex": self.color_hex,
            "tier": self.tier,
        }


# ============================================================
# 🎴 Rarity Table
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
        emoji="🎐",
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
# 🔧 Core Utility Functions
# ============================================================

def get_rarity(rarity_id: int) -> Optional[Rarity]:
    """Get Rarity object by ID."""
    return RARITY_TABLE.get(rarity_id)


def rarity_to_text(rarity_id: int) -> Tuple[str, float, str]:
    """
    Convert rarity ID to (name, probability, emoji).
    Legacy function for compatibility.
    """
    rarity = RARITY_TABLE.get(rarity_id)
    if not rarity:
        return "Unknown", 0.0, "❓"
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
    return RARITY_EMOJIS.get(rarity_id, "❓")


def get_rarity_name(rarity_id: int) -> str:
    """Get name for a rarity."""
    return RARITY_NAMES.get(rarity_id, "Unknown")


def get_rarity_by_name(name: str) -> Optional[Rarity]:
    """Find rarity by name (case-insensitive)."""
    name_lower = name.lower()
    for rarity in RARITY_TABLE.values():
        if rarity.name.lower() == name_lower:
            return rarity
    return None


def get_all_rarities() -> List[Rarity]:
    """Get all rarities sorted by ID."""
    return [RARITY_TABLE[i] for i in sorted(RARITY_TABLE.keys())]


# ============================================================
# 🎨 Display Functions
# ============================================================

def format_rarity_display(rarity_id: int, include_probability: bool = False) -> str:
    """Format rarity for display."""
    rarity = RARITY_TABLE.get(rarity_id)
    if not rarity:
        return "❓ Unknown"
    
    if include_probability:
        return rarity.display_with_rate
    return rarity.display


def get_rarity_tier(rarity_id: int) -> str:
    """Get tier classification for a rarity."""
    rarity = RARITY_TABLE.get(rarity_id)
    if rarity:
        return rarity.tier
    return "common"


def is_rare_plus(rarity_id: int) -> bool:
    """Check if rarity is Rare or higher."""
    return rarity_id >= 4


def is_legendary_tier(rarity_id: int) -> bool:
    """Check if rarity is Crystal, Mythical, or Legendary."""
    return rarity_id >= 9


# ============================================================
# 🎉 Celebration & Reaction Functions
# ============================================================

def get_catch_reaction(rarity_id: int) -> str:
    """Get the primary Telegram reaction emoji for a catch."""
    return PRIMARY_CATCH_REACTION.get(rarity_id, "👍")


def get_celebration_reactions(rarity_id: int) -> List[str]:
    """Get all celebration reactions for a rarity."""
    return CATCH_REACTIONS.get(rarity_id, ["👍"])


def should_celebrate(rarity_id: int) -> bool:
    """Check if this rarity deserves extra celebration."""
    return rarity_id >= 7  # Platinum and above


def get_catch_celebration_text(rarity_id: int) -> str:
    """Get celebration prefix text based on rarity."""
    if rarity_id == 11:
        return "🎊 LEGENDARY CATCH! 🎊"
    elif rarity_id == 10:
        return "✨ MYTHICAL CATCH! ✨"
    elif rarity_id == 9:
        return "❄️ CRYSTAL CATCH! ❄️"
    elif rarity_id >= 7:
        return "✨ RARE CATCH! ✨"
    elif rarity_id >= 5:
        return "🔥 Nice Catch!"
    else:
        return ""


# ============================================================
# 💰 Value & Scoring Functions
# ============================================================

def calculate_rarity_value(rarity_id: int, base_value: int = 100) -> int:
    """Calculate value score based on rarity."""
    if rarity_id not in RARITY_TABLE:
        return base_value
    
    multiplier = 2 ** (rarity_id - 1)
    return base_value * multiplier


def get_xp_reward(rarity_id: int, base_xp: int = 10) -> int:
    """Calculate XP reward for catching a card."""
    multipliers = {
        1: 1, 2: 1, 3: 2, 4: 3, 5: 5,
        6: 7, 7: 10, 8: 15, 9: 25, 10: 50, 11: 100
    }
    return base_xp * multipliers.get(rarity_id, 1)


def get_coin_reward(rarity_id: int, base_coins: int = 5) -> int:
    """Calculate coin reward for catching a card."""
    multipliers = {
        1: 1, 2: 1, 3: 2, 4: 3, 5: 5,
        6: 8, 7: 12, 8: 20, 9: 35, 10: 60, 11: 150
    }
    return base_coins * multipliers.get(rarity_id, 1)


# ============================================================
# 📊 Statistics Functions
# ============================================================

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
        tier = rarity.tier
        tier_stats[tier]["count"] += 1
        tier_stats[tier]["total_prob"] += rarity.probability
    
    return {
        "total_rarities": len(RARITY_TABLE),
        "total_probability": total_probability,
        "tier_stats": tier_stats,
        "rarest": RARITY_TABLE[11].name,
        "most_common": RARITY_TABLE[1].name,
    }


def get_rarity_list_display() -> str:
    """Get a clean list of all rarities for display."""
    lines = ["*All Rarities:*\n"]
    
    for rarity in get_all_rarities():
        lines.append(f"{rarity.emoji} {rarity.name} — {rarity.probability}%")
    
    return "\n".join(lines)