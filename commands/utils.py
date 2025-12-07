# commands/utils.py

# Updated rarity mapping
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

def rarity_to_text(rarity_id):
    """
    Return tuple: (name, percent, emoji)
    """
    return RARITY.get(rarity_id, ("unknown", 0.0, "❔"))

def format_telegram_name(user):
    """
    Input: user dict from DB
    Output: first_name or fallback
    """
    return user.get("first_name", "Unknown User")

def format_card_for_inline(card):
    """
    Input: card dict from DB
    Output: dict with title, description, and optional image for inline query
    """
    if not card:
        return None

    name, pct, emoji = rarity_to_text(card.get("rarity", 0))
    title = f"{emoji} {card.get('character', 'Unknown')} ({name.capitalize()})"
    description = f"🎬 {card.get('anime', 'Unknown Anime')} — ID: {card.get('id', 0)}"
    return {
        "title": title,
        "description": description,
        "photo_file_id": card.get("file_id"),
        "card_id": card.get("id")
    }