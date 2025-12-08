# commands/utils.py

# -------------------------
# Rarity mapping (1-10) — Custom
# -------------------------
RARITY = {
    1: ("Common", 35.0, "🌀"),
    2: ("Uncommon", 25.0, "🥏"),
    3: ("Bronze", 15.0, "🟤"),
    4: ("Silver", 10.0, "🪩"),
    5: ("Gold", 7.0, "🪙"),
    6: ("Limited Edition", 5.0, "🎐"),
    7: ("Emerald", 3.0, "💎"),
    8: ("Legendary", 2.0, "☘️"),
    9: ("Mythical", 1.0, "❄️"),
    10: ("Ultimate", 0.5, "🏵️"),
}

# -------------------------
# Helpers
# -------------------------
def rarity_to_text(rarity_id: int):
    """
    Return tuple: (name, percent, emoji)
    """
    return RARITY.get(rarity_id, ("Unknown", 0.0, "❔"))

def format_telegram_name(user: dict):
    return user.get("first_name") or user.get("username") or "Unknown User"

def format_card_for_inline(card: dict):
    if not card:
        return None

    rarity_name, _, rarity_emoji = rarity_to_text(card.get("rarity", 0))
    title = f"{rarity_emoji} {card.get('character', 'Unknown')} ({rarity_name})"
    description = f"🎬 {card.get('anime', 'Unknown Anime')} — ID: {card.get('id', 0)}"
    return {
        "title": title,
        "description": description,
        "photo_file_id": card.get("file_id"),
        "card_id": card.get("id")
    }