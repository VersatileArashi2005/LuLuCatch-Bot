# commands/utils.py

# -------------------------
# Rarity mapping
# -------------------------
RARITY = {
    1: ("common", 35.0, "🟢"),
    2: ("common+", 25.0, "🟠"),
    3: ("common++", 15.0, "🟡"),
    4: ("rare", 10.0, "🔮"),
    5: ("super_rare", 5.0, "✨"),
    6: ("ultra_rare", 3.0, "👑"),
    7: ("legendary", 3.0, "⚜️"),
    8: ("epic", 2.0, "🔱"),
    9: ("mythic", 1.0, "💀"),
    10: ("ultimate", 0.5, "🔥"),
}

# -------------------------
# Helpers
# -------------------------
def rarity_to_text(rarity_id: int):
    """
    Return tuple: (name, percent, emoji)
    """
    return RARITY.get(rarity_id, ("unknown", 0.0, "❔"))

def format_telegram_name(user: dict):
    """
    Input: user dict from DB
    Output: first_name or fallback
    """
    return user.get("first_name") or user.get("username") or "Unknown User"

def format_card_for_inline(card: dict):
    """
    Format a card for inline query display.
    Returns dict with title, description, photo_file_id, and card_id
    """
    if not card:
        return None

    rarity_name, _, rarity_emoji = rarity_to_text(card.get("rarity", 0))
    title = f"{rarity_emoji} {card.get('character', 'Unknown')} ({rarity_name.capitalize()})"
    description = f"🎬 {card.get('anime', 'Unknown Anime')} — ID: {card.get('id', 0)}"
    return {
        "title": title,
        "description": description,
        "photo_file_id": card.get("file_id"),
        "card_id": card.get("id")
    }