# commands/utils.py
# Rarity mapping (1-10) — Custom per user's list
RARITY = {
    1: ("Normal", 35.0, "🛞"),
    2: ("Common", 25.0, "🌀"),
    3: ("Uncommon", 15.0, "🥏"),
    4: ("Rare", 10.0, "☘️"),
    5: ("Epic", 7.0, "🫧"),
    6: ("Limited Edition", 5.0, "🎐"),
    7: ("Platinum", 3.0, "❄️"),
    8: ("Emerald", 2.0, "💎"),
    9: ("Crystal", 1.0, "🌸"),
    10: ("Legendary", 0.5, "⚡"),
}

def rarity_to_text(rid: int):
    return RARITY.get(rid, ("Unknown", 0.0, "❔"))

def format_telegram_name(user: dict):
    return user.get("first_name") or user.get("username") or "Unknown User"