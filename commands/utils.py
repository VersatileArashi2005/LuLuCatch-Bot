# rarity mapping as requested
RARITY = {
    1: ("Normal", 40.0, "🛞"),
    2: ("Common", 25.0, "🌀"),
    3: ("Uncommon", 15.0, "🥏"),
    4: ("Rare", 8.0, "☘️"),
    5: ("Epic", 5.0, "🫧"),
    6: ("Limited Edition", 3.0, "🎐"),
    7: ("Platinum", 1.5, "❄️"),
    8: ("Emerald", 1.0, "💎"),
    9: ("Crystal", 0.4, "🌸"),
    10: ("Mythical", 0.09, "🧿"),
    11: ("Legendary", 0.01, "⚡"),
}

def rarity_to_text(rid: int):
    """Return (name, pct, emoji). If unknown, returns placeholders."""
    return RARITY.get(rid, ("Unknown", 0.0, "❔"))

def format_telegram_name(user_dict):
    return user_dict.get("first_name") or user_dict.get("username") or "Unknown"