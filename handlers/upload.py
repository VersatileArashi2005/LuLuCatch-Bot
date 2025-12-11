# ============================================================
# 📁 File: handlers/upload.py
# 📍 Location: telegram_card_bot/handlers/upload.py
# 📝 Description: Enhanced card upload with image-hash duplicate detection
# ============================================================

from datetime import datetime
from typing import Optional, Dict, Any, List
import hashlib

from telegram import (
    Update,
    PhotoSize,
    Document,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.constants import ChatType

from config import Config
from db import db, add_card, ensure_user, get_card_count
from utils.logger import app_logger, error_logger, log_command
from utils.rarity import (
    get_random_rarity,
    rarity_to_text,
    RARITY_TABLE,
)


# ============================================================
# 📊 Conversation States
# ============================================================

SELECT_ANIME = 0
ADD_NEW_ANIME = 1
SELECT_CHARACTER = 2
ADD_NEW_CHARACTER = 3
SELECT_RARITY = 4
UPLOAD_PHOTO = 5
PREVIEW_CONFIRM = 6


# ============================================================
# ⏱️ Upload Cooldown Management
# ============================================================

_upload_cooldowns: Dict[int, datetime] = {}
UPLOAD_COOLDOWN_SECONDS = 5


def check_upload_cooldown(user_id: int) -> tuple[bool, int]:
    """Check if user is on upload cooldown."""
    if user_id not in _upload_cooldowns:
        return False, 0

    last_upload = _upload_cooldowns[user_id]
    elapsed = (datetime.now() - last_upload).total_seconds()

    if elapsed < UPLOAD_COOLDOWN_SECONDS:
        remaining = int(UPLOAD_COOLDOWN_SECONDS - elapsed)
        return True, remaining

    return False, 0


def set_upload_cooldown(user_id: int) -> None:
    """Set the upload cooldown for a user."""
    _upload_cooldowns[user_id] = datetime.now()


# ============================================================
# 📝 Session Data Management
# ============================================================

def init_upload_session(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Initialize upload session data."""
    context.user_data['upload'] = {
        'anime': None,
        'character': None,
        'rarity': None,
        'photo_file_id': None,
        'photo_hash': None,
        'started_at': datetime.now()
    }


def get_upload_data(context: ContextTypes.DEFAULT_TYPE) -> Dict[str, Any]:
    """Get current upload session data."""
    return context.user_data.get('upload', {})


def update_upload_data(context: ContextTypes.DEFAULT_TYPE, **kwargs) -> None:
    """Update upload session data."""
    if 'upload' not in context.user_data:
        init_upload_session(context)
    context.user_data['upload'].update(kwargs)


def clear_upload_data(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear upload session data."""
    context.user_data.pop('upload', None)


# ============================================================
# 🗄️ Database Helper Functions
# ============================================================

async def get_existing_anime_list() -> List[str]:
    """Get list of unique anime names from database."""
    if not db.is_connected:
        return []
    
    try:
        query = """
            SELECT DISTINCT anime FROM cards 
            WHERE is_active = TRUE 
            ORDER BY anime ASC
        """
        rows = await db.fetch(query)
        return [row['anime'] for row in rows]
    except Exception as e:
        error_logger.error(f"Error fetching anime list: {e}")
        return []


async def get_characters_for_anime(anime: str) -> List[str]:
    """
    Get list of characters for a specific anime.
    Note: Characters are NOT unique - same name can appear multiple times.
    This returns distinct names for selection purposes.
    """
    if not db.is_connected:
        return []
    
    try:
        query = """
            SELECT DISTINCT character_name FROM cards 
            WHERE anime = $1 AND is_active = TRUE 
            ORDER BY character_name ASC
        """
        rows = await db.fetch(query, anime)
        return [row['character_name'] for row in rows]
    except Exception as e:
        error_logger.error(f"Error fetching characters: {e}")
        return []


async def check_photo_exists(photo_file_id: str) -> tuple[bool, Optional[int]]:
    """
    Check if a photo (by file_id) already exists in the database.
    
    Args:
        photo_file_id: Telegram file ID
        
    Returns:
        Tuple of (exists: bool, existing_card_id: Optional[int])
    """
    if not db.is_connected:
        return False, None
    
    try:
        query = """
            SELECT card_id, character_name, anime 
            FROM cards 
            WHERE photo_file_id = $1 AND is_active = TRUE
            LIMIT 1
        """
        result = await db.fetchrow(query, photo_file_id)
        
        if result:
            return True, result['card_id']
        return False, None
        
    except Exception as e:
        error_logger.error(f"Error checking photo existence: {e}")
        return False, None


def generate_photo_hash(file_id: str) -> str:
    """
    Generate a hash from the file_id for duplicate detection.
    
    Args:
        file_id: Telegram file ID
        
    Returns:
        SHA256 hash of the file_id
    """
    return hashlib.sha256(file_id.encode()).hexdigest()


# ============================================================
# 🎴 Step 0: Upload Start
# ============================================================

async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /upload command - Start the upload flow."""
    user = update.effective_user
    chat = update.effective_chat

    log_command(user.id, "upload", chat.id)

    # Check if in private chat
    if chat.type != ChatType.PRIVATE:
        await update.message.reply_text(
            "❌ *Upload Restricted*\n\n"
            "Card uploads can only be done in private messages.\n"
            f"Please message me directly: @{Config.BOT_USERNAME}",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    # Check admin permissions
    if not Config.is_admin(user.id):
        await update.message.reply_text(
            "❌ *Permission Denied*\n\n"
            "Only authorized uploaders can add new cards.\n"
            "Contact an admin if you'd like to contribute!",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    # Check cooldown
    is_cooldown, remaining = check_upload_cooldown(user.id)
    if is_cooldown:
        await update.message.reply_text(
            f"⏳ *Too Fast!*\n\n"
            f"Please wait {remaining} seconds before uploading another card.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    # Ensure user exists in database
    await ensure_user(
        pool=None,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

    # Initialize session
    init_upload_session(context)

    app_logger.info(f"📤 Upload started by user {user.id} ({user.first_name})")

    # Show anime selection
    return await show_anime_selection(update, context)


# ============================================================
# 🟦 Step 1: Select Anime
# ============================================================

async def show_anime_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show anime selection menu."""
    
    # Get existing anime list
    anime_list = await get_existing_anime_list()
    
    # Build keyboard
    keyboard = []
    
    # Add existing anime (max 10 per page)
    for anime in anime_list[:10]:
        keyboard.append([
            InlineKeyboardButton(f"🎬 {anime}", callback_data=f"upload_anime_select:{anime}")
        ])
    
    # Show "More..." if there are more than 10
    if len(anime_list) > 10:
        keyboard.append([
            InlineKeyboardButton(f"📄 More ({len(anime_list) - 10} more)...", callback_data="upload_anime_more")
        ])
    
    # Add "New Anime" button
    keyboard.append([
        InlineKeyboardButton("➕ Add New Anime", callback_data="upload_anime_new")
    ])
    
    # Cancel button
    keyboard.append([
        InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "📤 *Card Upload - Step 1/5*\n\n"
        "🎬 *Choose Anime for this card:*\n\n"
        "Select an existing anime or add a new one.\n\n"
        "💡 Anime names must be unique."
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        await update.callback_query.answer()
    else:
        await update.message.reply_text(
            text=text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    
    return SELECT_ANIME


async def anime_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle anime selection callback."""
    query = update.callback_query
    data = query.data
    
    if data == "upload_anime_new":
        # Ask for new anime name
        await query.edit_message_text(
            "📤 *Card Upload - Step 1/5*\n\n"
            "🎬 *Enter the new Anime name:*\n\n"
            "Type the anime/series name or /cancel to abort.\n\n"
            "⚠️ Anime names must be unique in the database.",
            parse_mode="Markdown"
        )
        await query.answer()
        return ADD_NEW_ANIME
    
    elif data == "upload_anime_more":
        # TODO: Implement pagination for large anime lists
        await query.answer("Pagination coming soon! Use 'Add New Anime' for now.", show_alert=True)
        return SELECT_ANIME
    
    elif data.startswith("upload_anime_select:"):
        # Extract anime name
        anime = data.replace("upload_anime_select:", "")
        update_upload_data(context, anime=anime)
        
        app_logger.info(f"📤 User selected anime: {anime}")
        
        # Move to character selection
        return await show_character_selection(update, context)
    
    return SELECT_ANIME


async def anime_text_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle new anime name input."""
    anime_name = update.message.text.strip()
    
    # Validate
    if len(anime_name) < 2:
        await update.message.reply_text(
            "⚠️ *Invalid Name*\n\n"
            "Anime name must be at least 2 characters.\n"
            "Please try again:",
            parse_mode="Markdown"
        )
        return ADD_NEW_ANIME
    
    if len(anime_name) > 100:
        await update.message.reply_text(
            "⚠️ *Name Too Long*\n\n"
            "Anime name must be under 100 characters.\n"
            "Please try again:",
            parse_mode="Markdown"
        )
        return ADD_NEW_ANIME
    
    # Check if anime already exists (must be unique)
    existing_anime = await get_existing_anime_list()
    if anime_name in existing_anime:
        await update.message.reply_text(
            f"⚠️ *Anime Already Exists*\n\n"
            f"An anime named *{anime_name}* is already in the database.\n\n"
            f"Please select it from the list or enter a different name:",
            parse_mode="Markdown"
        )
        return ADD_NEW_ANIME
    
    # Save anime
    update_upload_data(context, anime=anime_name)
    
    app_logger.info(f"📤 User added new anime: {anime_name}")
    
    # Move to character selection
    return await show_character_selection(update, context)


# ============================================================
# 🟪 Step 2: Select Character
# ============================================================

async def show_character_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show character selection menu."""
    
    upload_data = get_upload_data(context)
    anime = upload_data.get('anime', 'Unknown')
    
    # Get existing characters for this anime
    character_list = await get_characters_for_anime(anime)
    
    # Build keyboard
    keyboard = []
    
    # Add existing characters (showing they can be reused)
    for character in character_list[:10]:
        keyboard.append([
            InlineKeyboardButton(f"👤 {character}", callback_data=f"upload_char_select:{character}")
        ])
    
    # Show more if needed
    if len(character_list) > 10:
        keyboard.append([
            InlineKeyboardButton(f"📄 More ({len(character_list) - 10} more)...", callback_data="upload_char_more")
        ])
    
    # Add "New Character" button
    keyboard.append([
        InlineKeyboardButton("➕ Add New Character", callback_data="upload_char_new")
    ])
    
    # Back and Cancel buttons
    keyboard.append([
        InlineKeyboardButton("⬅️ Back", callback_data="upload_back_anime"),
        InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "📤 *Card Upload - Step 2/5*\n\n"
        f"🎬 *Anime:* {anime}\n\n"
        "👤 *Choose Character for this card:*\n\n"
        "Select an existing character or add a new one.\n\n"
        "💡 Characters can be reused (different poses/rarities)."
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        await update.callback_query.answer()
    else:
        await update.message.reply_text(
            text=text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    
    return SELECT_CHARACTER


async def character_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle character selection callback."""
    query = update.callback_query
    data = query.data
    
    if data == "upload_char_new":
        upload_data = get_upload_data(context)
        anime = upload_data.get('anime', 'Unknown')
        
        await query.edit_message_text(
            "📤 *Card Upload - Step 2/5*\n\n"
            f"🎬 *Anime:* {anime}\n\n"
            "👤 *Enter the Character name:*\n\n"
            "Type the character name or /cancel to abort.\n\n"
            "💡 Same character can be used for multiple cards.",
            parse_mode="Markdown"
        )
        await query.answer()
        return ADD_NEW_CHARACTER
    
    elif data == "upload_char_more":
        await query.answer("Pagination coming soon!", show_alert=True)
        return SELECT_CHARACTER
    
    elif data.startswith("upload_char_select:"):
        # Extract character name
        character = data.replace("upload_char_select:", "")
        update_upload_data(context, character=character)
        
        app_logger.info(f"📤 User selected character: {character}")
        
        # Move to rarity selection (no duplicate check here)
        return await show_rarity_selection(update, context)
    
    elif data == "upload_back_anime":
        await query.answer()
        return await show_anime_selection(update, context)
    
    return SELECT_CHARACTER


async def character_text_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle new character name input."""
    character_name = update.message.text.strip()
    
    # Validate
    if len(character_name) < 2:
        await update.message.reply_text(
            "⚠️ *Invalid Name*\n\n"
            "Character name must be at least 2 characters.\n"
            "Please try again:",
            parse_mode="Markdown"
        )
        return ADD_NEW_CHARACTER
    
    if len(character_name) > 100:
        await update.message.reply_text(
            "⚠️ *Name Too Long*\n\n"
            "Character name must be under 100 characters.\n"
            "Please try again:",
            parse_mode="Markdown"
        )
        return ADD_NEW_CHARACTER
    
    # No duplicate check for characters - they can be reused!
    # Save character
    update_upload_data(context, character=character_name)
    
    app_logger.info(f"📤 User added character: {character_name}")
    
    # Move to rarity selection
    return await show_rarity_selection(update, context)


# ============================================================
# 🟫 Step 3: Select Rarity
# ============================================================

async def show_rarity_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show rarity selection menu."""
    
    upload_data = get_upload_data(context)
    anime = upload_data.get('anime', 'Unknown')
    character = upload_data.get('character', 'Unknown')
    
    # Build keyboard with all rarities
    keyboard = []
    
    # Add rarity buttons (2 per row)
    rarity_buttons = []
    for rarity_id in range(1, 12):  # 1-11
        rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity_id)
        
        button = InlineKeyboardButton(
            f"{rarity_emoji} {rarity_name} ({rarity_prob}%)",
            callback_data=f"upload_rarity:{rarity_id}"
        )
        
        rarity_buttons.append(button)
        
        # Add row after every 2 buttons
        if len(rarity_buttons) == 2:
            keyboard.append(rarity_buttons)
            rarity_buttons = []
    
    # Add remaining button if odd number
    if rarity_buttons:
        keyboard.append(rarity_buttons)
    
    # Random rarity button
    keyboard.append([
        InlineKeyboardButton("🎲 Random Rarity", callback_data="upload_rarity:random")
    ])
    
    # Back and Cancel buttons
    keyboard.append([
        InlineKeyboardButton("⬅️ Back", callback_data="upload_back_character"),
        InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "📤 *Card Upload - Step 3/5*\n\n"
        f"🎬 *Anime:* {anime}\n"
        f"👤 *Character:* {character}\n\n"
        "✨ *Choose Rarity for this card:*\n\n"
        "Select the rarity tier that fits this character."
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        await update.callback_query.answer()
    else:
        await update.message.reply_text(
            text=text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    
    return SELECT_RARITY


async def rarity_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle rarity selection callback."""
    query = update.callback_query
    data = query.data
    
    if data.startswith("upload_rarity:"):
        rarity_value = data.replace("upload_rarity:", "")
        
        # Determine rarity
        if rarity_value == "random":
            rarity_id = get_random_rarity()
        else:
            rarity_id = int(rarity_value)
        
        update_upload_data(context, rarity=rarity_id)
        
        rarity_name, _, rarity_emoji = rarity_to_text(rarity_id)
        app_logger.info(f"📤 User selected rarity: {rarity_id} ({rarity_name})")
        
        await query.answer(f"Selected: {rarity_emoji} {rarity_name}")
        
        # Move to photo upload
        return await show_photo_upload(update, context)
    
    elif data == "upload_back_character":
        await query.answer()
        return await show_character_selection(update, context)
    
    return SELECT_RARITY


# ============================================================
# 🟥 Step 4: Upload Photo
# ============================================================

async def show_photo_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show photo upload prompt."""
    
    upload_data = get_upload_data(context)
    anime = upload_data.get('anime', 'Unknown')
    character = upload_data.get('character', 'Unknown')
    rarity = upload_data.get('rarity', 1)
    
    rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity)
    
    # Build keyboard
    keyboard = [
        [
            InlineKeyboardButton("⬅️ Back", callback_data="upload_back_rarity"),
            InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "📤 *Card Upload - Step 4/5*\n\n"
        f"🎬 *Anime:* {anime}\n"
        f"👤 *Character:* {character}\n"
        f"✨ *Rarity:* {rarity_emoji} {rarity_name}\n\n"
        "🖼️ *Send the card photo:*\n\n"
        "Send an image (as photo, not document).\n"
        "💡 Best quality: PNG or JPG, under 5MB\n\n"
        "⚠️ Duplicate photos will be detected."
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        await update.callback_query.answer()
    else:
        await update.message.reply_text(
            text=text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    
    return UPLOAD_PHOTO


async def photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle photo upload."""
    message = update.message
    
    # Extract photo file ID
    photo_file_id: Optional[str] = None
    
    if message.photo:
        photo: PhotoSize = message.photo[-1]  # Get highest quality
        photo_file_id = photo.file_id
        app_logger.info(f"📤 Received photo from user {message.from_user.id}")
    
    elif message.document:
        doc: Document = message.document
        
        if doc.mime_type and doc.mime_type.startswith("image/"):
            photo_file_id = doc.file_id
            app_logger.info(f"📤 Received document image from user {message.from_user.id}")
        else:
            await message.reply_text(
                "❌ *Invalid File Type*\n\n"
                "Please send an image file (JPG, PNG, etc.)",
                parse_mode="Markdown"
            )
            return UPLOAD_PHOTO
    
    if not photo_file_id:
        await message.reply_text(
            "❌ *No Image Detected*\n\n"
            "Please send a photo (📷) or image file (📎).",
            parse_mode="Markdown"
        )
        return UPLOAD_PHOTO
    
    # Generate hash for this photo
    photo_hash = generate_photo_hash(photo_file_id)
    
    # Save photo file ID and hash
    update_upload_data(context, photo_file_id=photo_file_id, photo_hash=photo_hash)
    
    app_logger.info(f"📤 Photo saved with hash: {photo_hash[:16]}...")
    
    # Show preview (duplicate check happens on confirm)
    return await show_preview(update, context)


# ============================================================
# 🟩 Step 5: Preview & Confirmation
# ============================================================

async def show_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show preview with confirmation buttons."""
    
    upload_data = get_upload_data(context)
    anime = upload_data.get('anime', 'Unknown')
    character = upload_data.get('character', 'Unknown')
    rarity = upload_data.get('rarity', 1)
    photo_file_id = upload_data.get('photo_file_id')
    
    rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity)
    
    # Build caption
    caption = (
        "🔎 *Preview*\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🎬 *Anime:* {anime}\n"
        f"👤 *Character:* {character}\n"
        f"✨ *Rarity:* {rarity_emoji} {rarity_name} ({rarity_prob}%)\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Press *Confirm & Save* to add this card.\n\n"
        "⚠️ Duplicate check will run on confirmation."
    )
    
    # Build keyboard
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm & Save", callback_data="upload_confirm"),
        ],
        [
            InlineKeyboardButton("✏️ Edit", callback_data="upload_edit"),
            InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send preview with photo
    if update.callback_query:
        # Can't edit to photo, send new message
        await update.callback_query.message.reply_photo(
            photo=photo_file_id,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        await update.callback_query.answer("Preview generated!")
    else:
        await update.message.reply_photo(
            photo=photo_file_id,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    
    return PREVIEW_CONFIRM


# ============================================================
# 🟩 Step 6: Confirm & Save (with Duplicate Detection)
# ============================================================

async def confirm_upload_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle upload confirmation with photo duplicate detection."""
    query = update.callback_query
    user = query.from_user
    
    upload_data = get_upload_data(context)
    anime = upload_data.get('anime')
    character = upload_data.get('character')
    rarity = upload_data.get('rarity')
    photo_file_id = upload_data.get('photo_file_id')
    
    # ========================================
    # DUPLICATE CHECK: Photo-based only
    # ========================================
    
    await query.answer("Checking for duplicates...")
    
    photo_exists, existing_card_id = await check_photo_exists(photo_file_id)
    
    if photo_exists:
        # Photo already uploaded!
        await query.edit_message_caption(
            caption=(
                "⚠️ *Duplicate Photo Detected!*\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"This exact photo already exists as Card `#{existing_card_id}`.\n\n"
                "Please upload a different image or cancel.\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "💡 Tip: Same character is allowed, but not the same photo."
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Upload New Photo", callback_data="upload_edit_photo")],
                [InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")]
            ])
        )
        
        app_logger.warning(f"📤 Duplicate photo detected: {photo_file_id} (Card #{existing_card_id})")
        
        return PREVIEW_CONFIRM
    
    # ========================================
    # No duplicate - proceed with save
    # ========================================
    
    try:
        card = await add_card(
            pool=None,
            anime=anime,
            character=character,
            rarity=rarity,
            photo_file_id=photo_file_id,
            uploader_id=user.id,
            description=f"Uploaded by {user.first_name}",
            tags=[anime.lower(), character.lower().split()[0] if character else ""]
        )
        
        if card is None:
            # This shouldn't happen now (we removed anime+character uniqueness)
            # But keep as fallback
            await query.answer("⚠️ Failed to save card!", show_alert=True)
            clear_upload_data(context)
            return ConversationHandler.END
        
        card_id = card["card_id"]
        
        # Set cooldown
        set_upload_cooldown(user.id)
        
        # Get total card count
        total_cards = await get_card_count(None)
        
        rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity)
        
        # Success message
        await query.edit_message_caption(
            caption=(
                "🎉 *Card Uploaded Successfully!*\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"🆔 *ID:* `#{card_id}`\n"
                f"🎬 *Anime:* {anime}\n"
                f"👤 *Character:* {character}\n"
                f"✨ *Rarity:* {rarity_emoji} {rarity_name} ({rarity_prob}%)\n"
                f"👤 *Uploader:* {user.first_name}\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📦 Total cards in database: *{total_cards}*\n\n"
                "Use /upload to add more cards!"
            ),
            parse_mode="Markdown"
        )
        
        await query.answer("✅ Card saved!")
        
        app_logger.info(f"✅ Card #{card_id} uploaded: {character} ({anime}) by user {user.id}")
        
        # Clear session
        clear_upload_data(context)
        
        return ConversationHandler.END
        
    except Exception as e:
        error_logger.error(f"Failed to save card: {e}", exc_info=True)
        await query.answer("❌ Error saving card!", show_alert=True)
        return ConversationHandler.END


# ============================================================
# 🟨 Step 7: Edit Menu
# ============================================================

async def show_edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show edit menu."""
    query = update.callback_query
    
    upload_data = get_upload_data(context)
    anime = upload_data.get('anime', 'Unknown')
    character = upload_data.get('character', 'Unknown')
    rarity = upload_data.get('rarity', 1)
    
    rarity_name, _, rarity_emoji = rarity_to_text(rarity)
    
    keyboard = [
        [InlineKeyboardButton("🎬 Edit Anime", callback_data="upload_edit_anime")],
        [InlineKeyboardButton("👤 Edit Character", callback_data="upload_edit_character")],
        [InlineKeyboardButton("💠 Edit Rarity", callback_data="upload_edit_rarity")],
        [InlineKeyboardButton("🖼 Edit Photo", callback_data="upload_edit_photo")],
        [InlineKeyboardButton("⬅️ Back to Preview", callback_data="upload_back_preview")],
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "✏️ *Edit Upload*\n\n"
        "Current values:\n"
        f"🎬 Anime: {anime}\n"
        f"👤 Character: {character}\n"
        f"✨ Rarity: {rarity_emoji} {rarity_name}\n\n"
        "What do you want to edit?"
    )
    
    await query.edit_message_text(
        text=text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    await query.answer()
    
    return PREVIEW_CONFIRM


async def edit_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle edit selection."""
    query = update.callback_query
    data = query.data
    
    if data == "upload_edit_anime":
        await query.answer()
        return await show_anime_selection(update, context)
    
    elif data == "upload_edit_character":
        await query.answer()
        return await show_character_selection(update, context)
    
    elif data == "upload_edit_rarity":
        await query.answer()
        return await show_rarity_selection(update, context)
    
    elif data == "upload_edit_photo":
        await query.answer()
        return await show_photo_upload(update, context)
    
    elif data == "upload_back_preview":
        await query.answer()
        return await show_preview(update, context)
    
    return PREVIEW_CONFIRM


# ============================================================
# 🟥 Cancel Handler
# ============================================================

async def upload_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle upload cancellation."""
    query = update.callback_query
    
    clear_upload_data(context)
    
    await query.edit_message_text(
        "❌ *Upload Cancelled*\n\n"
        "Temporary data cleared.\n"
        "Use /upload to start again.",
        parse_mode="Markdown"
    )
    
    await query.answer("Upload cancelled")
    
    app_logger.info(f"📤 Upload cancelled by user {query.from_user.id}")
    
    return ConversationHandler.END


async def upload_cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /cancel command."""
    clear_upload_data(context)
    
    await update.message.reply_text(
        "❌ *Upload Cancelled*\n\n"
        "Use /upload to start again.",
        parse_mode="Markdown"
    )
    
    return ConversationHandler.END


# ============================================================
# 🔧 Back Navigation Callbacks
# ============================================================

async def back_navigation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle back navigation buttons."""
    query = update.callback_query
    data = query.data
    
    if data == "upload_back_rarity":
        await query.answer()
        return await show_rarity_selection(update, context)
    
    return UPLOAD_PHOTO


# ============================================================
# 📤 Quick Upload (Admin Shortcut)
# ============================================================

async def quick_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Quick upload by replying to a photo with:
    /quickupload Anime | Character | Rarity
    """
    user = update.effective_user
    message = update.message

    if not Config.is_admin(user.id):
        await message.reply_text("❌ Admin only command.")
        return

    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.reply_text(
            "📤 *Quick Upload*\n\n"
            "Reply to a photo with:\n"
            "`/quickupload Anime | Character | Rarity`\n\n"
            "Examples:\n"
            "`/quickupload Naruto | Naruto Uzumaki | 5`\n"
            "`/quickupload One Piece | Luffy | Legendary`\n\n"
            "💡 Characters can be duplicated (different poses).",
            parse_mode="Markdown"
        )
        return

    args_text = message.text.replace("/quickupload", "").strip()

    if not args_text:
        await message.reply_text("❌ Please provide: `Anime | Character | Rarity`", parse_mode="Markdown")
        return

    parts = [p.strip() for p in args_text.split("|")]

    if len(parts) < 2:
        await message.reply_text("❌ Format: `Anime | Character | Rarity`", parse_mode="Markdown")
        return

    anime = parts[0]
    character = parts[1]
    rarity_id = None

    if len(parts) >= 3:
        rarity_input = parts[2].strip().lower()

        if rarity_input.isdigit():
            rarity_id = int(rarity_input)
            if not 1 <= rarity_id <= 11:
                rarity_id = None
        elif rarity_input == "random":
            rarity_id = None
        else:
            rarity_names = {
                "normal": 1, "common": 2, "uncommon": 3, "rare": 4,
                "epic": 5, "limited": 6, "limited edition": 6,
                "platinum": 7, "emerald": 8, "crystal": 9,
                "mythical": 10, "legendary": 11
            }
            rarity_id = rarity_names.get(rarity_input)

    if rarity_id is None:
        rarity_id = get_random_rarity()

    photo_file_id = message.reply_to_message.photo[-1].file_id
    
    # Check for duplicate photo
    photo_exists, existing_card_id = await check_photo_exists(photo_file_id)
    
    if photo_exists:
        await message.reply_text(
            f"⚠️ *Duplicate Photo Detected!*\n\n"
            f"This photo already exists as Card `#{existing_card_id}`.\n\n"
            f"Please use a different image.",
            parse_mode="Markdown"
        )
        return

    try:
        card = await add_card(
            pool=None,
            anime=anime,
            character=character,
            rarity=rarity_id,
            photo_file_id=photo_file_id,
            uploader_id=user.id
        )

        if card:
            rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity_id)
            await message.reply_text(
                f"✅ *Quick Upload Success!*\n\n"
                f"🆔 ID: `#{card['card_id']}`\n"
                f"🎬 Anime: {anime}\n"
                f"👤 Character: {character}\n"
                f"✨ Rarity: {rarity_emoji} {rarity_name}",
                parse_mode="Markdown"
            )
        else:
            await message.reply_text("⚠️ Failed to save card!")

    except Exception as e:
        error_logger.error(f"Quick upload failed: {e}", exc_info=True)
        await message.reply_text(f"❌ Error: {e}")


# ============================================================
# 🔧 Handlers Export
# ============================================================

# Main upload conversation handler
upload_conversation_handler = ConversationHandler(
    entry_points=[
        CommandHandler("upload", upload_start),
    ],
    states={
        SELECT_ANIME: [
            CallbackQueryHandler(anime_selected_callback, pattern=r"^upload_anime_"),
            CallbackQueryHandler(upload_cancel_callback, pattern=r"^upload_cancel$"),
        ],
        ADD_NEW_ANIME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, anime_text_received),
        ],
        SELECT_CHARACTER: [
            CallbackQueryHandler(character_selected_callback, pattern=r"^upload_char_"),
            CallbackQueryHandler(character_selected_callback, pattern=r"^upload_back_anime$"),
            CallbackQueryHandler(upload_cancel_callback, pattern=r"^upload_cancel$"),
        ],
        ADD_NEW_CHARACTER: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, character_text_received),
        ],
        SELECT_RARITY: [
            CallbackQueryHandler(rarity_selected_callback, pattern=r"^upload_rarity:"),
            CallbackQueryHandler(rarity_selected_callback, pattern=r"^upload_back_character$"),
            CallbackQueryHandler(upload_cancel_callback, pattern=r"^upload_cancel$"),
        ],
        UPLOAD_PHOTO: [
            MessageHandler(filters.PHOTO | filters.Document.IMAGE, photo_received),
            CallbackQueryHandler(back_navigation_callback, pattern=r"^upload_back_rarity$"),
            CallbackQueryHandler(upload_cancel_callback, pattern=r"^upload_cancel$"),
        ],
        PREVIEW_CONFIRM: [
            CallbackQueryHandler(confirm_upload_callback, pattern=r"^upload_confirm$"),
            CallbackQueryHandler(show_edit_menu, pattern=r"^upload_edit$"),
            CallbackQueryHandler(edit_selection_callback, pattern=r"^upload_edit_"),
            CallbackQueryHandler(edit_selection_callback, pattern=r"^upload_back_preview$"),
            CallbackQueryHandler(upload_cancel_callback, pattern=r"^upload_cancel$"),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", upload_cancel_command),
    ],
    name="upload_conversation",
    persistent=False,
)

# Separate rarity callback handler (for compatibility)
upload_rarity_callback_handler = CallbackQueryHandler(
    lambda u, c: None,  # Not used in new flow
    pattern=r"^upload_rarity_"
)

# Quick upload command handler
quick_upload_handler = CommandHandler("quickupload", quick_upload)