# commands/utils.py
RARITY = {
    1: ("bronze", 100, "🥉"),
    2: ("silver", 90, "🥈"),
    3: ("rare", 80, "🔹"),
    4: ("epic", 70, "💥"),
    5: ("platinum", 40, "💎"),
    6: ("emerald", 30, "💚"),
    7: ("diamond", 10, "💎"),
    8: ("mythical", 5, "🌟"),
    9: ("legendary", 2, "🏆"),
    10: ("supernatural", 1, "👑"),
}

def rarity_to_text(rarity_id):
    r = RARITY.get(rarity_id, ("unknown", 0, "❔"))
    return r  # (name, percent, emoji)
