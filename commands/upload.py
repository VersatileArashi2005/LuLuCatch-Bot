# upload.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext
from db import add_card

RARITY = {
    1: ("bronze", "100%", "🥉"),
    2: ("silver", "90%", "🥈"),
    3: ("rare", "80%", "🔹"),
    4: ("epic", "70%", "💥"),
    5: ("platinum", "40%", "💎"),
    6: ("emerald", "30%", "💚"),
    7: ("diamond", "10%", "💎"),
    8: ("mythical", "5%", "🌟"),
    9: ("legendary", "2%", "🏆"),
    10: ("supernatural", "1%", "👑"),
}

user_upload_state = {}  # temp storage: {user_id: {"anime": "", "character": "", "rarity": 0}}

def upload(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    keyboard = [[InlineKeyboardButton("Add Anime Name", callback_data="anime_add")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Step 1: Please choose Anime Name", reply_markup=reply_markup)
    user_upload_state[user_id] = {}

def upload_anime(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    # store anime name
    user_upload_state[user_id]["anime"] = query.data.replace("anime_", "")
    query.answer()
    query.edit_message_text(text="Step 2: Please enter Character Name")

def upload_character(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    character_name = update.message.text
    user_upload_state[user_id]["character"] = character_name
    # show Rarity buttons
    keyboard = [
        [InlineKeyboardButton(f"{v[2]} {v[0]} ({v[1]})", callback_data=f"rarity_{k}") ] for k,v in RARITY.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Step 3: Choose Rarity", reply_markup=reply_markup)

def upload_rarity(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    rarity_id = int(query.data.replace("rarity_", ""))
    user_upload_state[user_id]["rarity"] = rarity_id
    # finalize upload
    data = user_upload_state[user_id]
    add_card(name="TempCard", anime=data["anime"], character=data["character"], rarity=data["rarity"])
    query.answer()
    query.edit_message_text(text=f"Upload complete!\nAnime: {data['anime']}\nCharacter: {data['character']}\nRarity: {RARITY[rarity_id][0]}")
    del user_upload_state[user_id]

def upload_handlers(app):
    app.add_handler(CommandHandler("upload", upload))
    app.add_handler(CallbackQueryHandler(upload_anime, pattern="^anime_"))
    app.add_handler(MessageHandler(Filters.text & ~Filters.command, upload_character))
    app.add_handler(CallbackQueryHandler(upload_rarity, pattern="^rarity_"))
