from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db import get_anime_list, get_characters, add_anime, add_character, add_card

async def upload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    anime_list = get_anime_list()
    
    keyboard = []
    for anime in anime_list:
        keyboard.append([InlineKeyboardButton(anime, callback_data=f"anime_{anime}")])
    
    # Add button to add new anime
    keyboard.append([InlineKeyboardButton("Add Anime Name", callback_data="anime_add")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("Step 1: Select Anime Name or Add New", reply_markup=reply_markup)


async def upload_anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "anime_add":
        await query.edit_message_text("Send the new Anime Name in reply to this message.")
        return
    else:
        context.user_data['anime'] = data.replace("anime_", "")
        characters = get_characters(context.user_data['anime'])
        keyboard = []
        for char in characters:
            keyboard.append([InlineKeyboardButton(char, callback_data=f"character_{char}")])
        keyboard.append([InlineKeyboardButton("Add Character", callback_data="character_add")])
        await query.edit_message_text("Step 2: Select Character or Add New", reply_markup=InlineKeyboardMarkup(keyboard))


async def upload_character(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "character_add":
        await query.edit_message_text("Send the new Character Name in reply to this message.")
        return
    else:
        context.user_data['character'] = data.replace("character_", "")
        # Step 3: Rarity selection
        keyboard = [
            [InlineKeyboardButton("Bronze 💰", callback_data="rarity_1")],
            [InlineKeyboardButton("Silver ⚪", callback_data="rarity_2")],
            [InlineKeyboardButton("Rare 🔹", callback_data="rarity_3")],
            [InlineKeyboardButton("Epic 🔥", callback_data="rarity_4")],
            [InlineKeyboardButton("Platinum 💎", callback_data="rarity_5")],
            [InlineKeyboardButton("Emerald 💚", callback_data="rarity_6")],
            [InlineKeyboardButton("Diamond 💎", callback_data="rarity_7")],
            [InlineKeyboardButton("Mythical 🌟", callback_data="rarity_8")],
            [InlineKeyboardButton("Legendary 🏆", callback_data="rarity_9")],
            [InlineKeyboardButton("Supernatural 👑", callback_data="rarity_10")],
        ]
        await query.edit_message_text("Step 3: Select Rarity", reply_markup=InlineKeyboardMarkup(keyboard))


async def upload_rarity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rarity_id = int(query.data.replace("rarity_", ""))
    context.user_data['rarity'] = rarity_id
    
    # Save card in DB
    add_card(
        name=context.user_data.get('character'),
        anime=context.user_data.get('anime'),
        rarity=rarity_id,
        uploader_id=query.from_user.id
    )
    
    await query.edit_message_text(f"✅ Card uploaded:\nAnime: {context.user_data.get('anime')}\nCharacter: {context.user_data.get('character')}\nRarity ID: {rarity_id}")
    
    # TODO: Notify groups
