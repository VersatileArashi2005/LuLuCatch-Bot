from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler, CallbackQueryHandler, MessageHandler, filters

ANIME, CHARACTER, RARITY, PHOTO = range(4)

def upload_start(update: Update, context: CallbackContext):
    # Step 1: Anime Name buttons
    keyboard = [[InlineKeyboardButton("One Piece", callback_data="anime_One Piece")]]
    keyboard.append([InlineKeyboardButton("Add Anime Name", callback_data="add_anime")])
    update.message.reply_text("Add Anime Name", reply_markup=InlineKeyboardMarkup(keyboard))
    return ANIME

def upload_anime(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    context.user_data['anime'] = query.data.replace("anime_", "")
    # Step 2: Character selection
    keyboard = [[InlineKeyboardButton("Luffy", callback_data="char_Luffy")]]
    keyboard.append([InlineKeyboardButton("Add Character", callback_data="add_char")])
    query.edit_message_text("Add Character", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHARACTER

def upload_character(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    context.user_data['character'] = query.data.replace("char_", "")
    # Step 3: Rarity selection
    rarities = {
        "bronze": "100%", "silver": "90%", "rare": "80%", "epic": "70%",
        "platinum": "40%", "emerald": "30%", "diamond": "10%",
        "mythical": "5%", "legendary": "2%", "supernatural": "1%"
    }
    keyboard = [[InlineKeyboardButton(f"{key} 💎 {val}", callback_data=f"rar_{key}") for key,val in rarities.items()]]
    query.edit_message_text("Select Rarity", reply_markup=InlineKeyboardMarkup(keyboard))
    return RARITY

def upload_rarity(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    context.user_data['rarity'] = query.data.replace("rar_", "")
    query.edit_message_text("Send Photo now")
    return PHOTO

def upload_photo(update: Update, context: CallbackContext):
    file_id = update.message.photo[-1].file_id
    from db import add_card
    card_id = add_card(context.user_data['anime'], context.user_data['character'], context.user_data['rarity'], file_id)
    update.message.reply_text(f"Card Added! ID: {card_id}, Anime: {context.user_data['anime']}, Character: {context.user_data['character']}")
    # TODO: Notify all groups
    return ConversationHandler.END
