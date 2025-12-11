# ===========================================================
# 📁 File: handlers/upload.py
# 📍 Location: telegram_card_bot/handlers/upload.py
# 📝 Description: Enhanced card upload with photo-only duplicate detection
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
from db import db, ensure_user, get_card_count
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
    Returns distinct names for selection (characters can repeat).
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
    """Generate SHA256 hash from file_id for duplicate detection."""
    return hashlib.sha256(file_id.encode()).hexdigest()


# ============================================================
# 🆕 Direct Card Insert (bypasses add_card constraints)
# ============================================================

async def insert_card_direct(
    anime: str,
    character: str,
    rarity: int,
    photo_file_id: str,
    uploader_id: int
) -> Optional[Dict[str, Any]]:
    """
    Insert a card directly into the database.
    
    Bypasses add_card() to avoid (anime, character_name) UNIQUE constraint.
    Only photo_file_id uniqueness is enforced via application logic.
    
    Args:
        anime: Anime name
        character: Character name
        rarity: Rarity ID (1-11)
        photo_file_id: Telegram photo file ID
        uploader_id: User ID of uploader
        
    Returns:
        Card record if successful, None otherwise
    """
    if not db.is_connected:
        raise Exception("Database not connected")
    
    # Validate rarity
    if not 1 <= rarity <= 11:
        raise ValueError(f"Invalid rarity: {rarity}. Must be 1-11.")
    
    try:
        # Insert card directly
        query = """
            INSERT INTO cards (
                anime, 
                character_name, 
                rarity, 
                photo_file_id, 
                uploader_id, 
                description, 
                tags,
                created_at,
                is_active,
                total_caught
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), TRUE, 0)
            RETURNING *
        """
        
        # Generate tags
        tags = [anime.lower(), character.lower().split()[0] if character else ""]
        description = f"Uploaded by user {uploader_id}"
        
        # Execute insert
        result = await db.fetchrow(
            query,
            anime,
            character,
            rarity,
            photo_file_id,
            uploader_id,
            description,
            tags
        )
        
        if result:
            app_logger.info(
                f"✅ Card inserted: ID={result['card_id']}, "
                f"{character} ({anime}), rarity={rarity}"
            )
            return dict(result)
        
        return None
        
    except Exception as e:
        error_logger.error(
            f"Card insert failed: anime={anime}, character={character}, "
            f"rarity={rarity}, error={e}",
            exc_info=True
        )
        raise


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
        await query.answer("Pagination coming soon! Use 'Add New Anime' for now.", show_alert=True)
        return SELECT_ANIME
    
    elif data.startswith("upload_anime_select:"):
        anime = data.replace("upload_anime_select:", "")
        update_upload_data(context, anime=anime)
        
        app_logger.info(f"📤 User selected anime: {anime}")
        
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
    
    # Check if anime already exists
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
    
    # Add existing characters
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
        character = data.replace("upload_char_select:", "")
        update_upload_data(context, character=character)
        
        app_logger.info(f"📤 User selected character: {character}")
        
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
    
    # Save character (no duplicate check)
    update_upload_data(context, character=character_name)
    
    app_logger.info(f"📤 User added character: {character_name}")
    
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
    for rarity_id in range(1, 12):
        rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity_id)
        
        button = InlineKeyboardButton(
            f"{rarity_emoji} {rarity_name} ({rarity_prob}%)",
            callback_data=f"upload_rarity:{rarity_id}"
        )
        
        rarity_buttons.append(button)
        
        if len(rarity_buttons) == 2:
            keyboard.append(rarity_buttons)
            rarity_buttons = []
    
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
        
        if rarity_value == "random":
            rarity_id = get_random_rarity()
        else:
            rarity_id = int(rarity_value)
        
        update_upload_data(context, rarity=rarity_id)
        
        rarity_name, _, rarity_emoji = rarity_to_text(rarity_id)
        app_logger.info(f"📤 User selected rarity: {rarity_id} ({rarity_name})")
        
        await query.answer(f"Selected: {rarity_emoji} {rarity_name}")
        
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
    
    photo_file_id: Optional[str] = None
    
    if message.photo:
        photo: PhotoSize = message.photo[-1]
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
    
    # Generate hash
    photo_hash = generate_photo_hash(photo_file_id)
    
    # Save photo
    update_upload_data(context, photo_file_id=photo_file_id, photo_hash=photo_hash)
    
    app_logger.info(f"📤 Photo saved with hash: {photo_hash[:16]}...")
    
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
    
    if update.callback_query:
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
# 🟩 Step 6: Confirm & Save (FIXED - Production Ready)
# ============================================================

async def confirm_upload_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle upload confirmation with photo duplicate detection.
    
    Production-ready with:
    - Immediate callback answer
    - Photo-only duplicate check
    - Direct database insert
    - Comprehensive error handling
    """
    query = update.callback_query
    user = query.from_user
    
    # Answer immediately
    await query.answer()
    
    # Get upload data
    upload_data = get_upload_data(context)
    anime = upload_data.get('anime')
    character = upload_data.get('character')
    rarity = upload_data.get('rarity')
    photo_file_id = upload_data.get('photo_file_id')
    
    # Validate
    if not all([anime, character, rarity, photo_file_id]):
        await query.edit_message_caption(
            caption=(
                "❌ *Upload Error*\n\n"
                "Some data is missing. Please try again.\n\n"
                "Use /upload to restart."
            ),
            parse_mode="Markdown"
        )
        clear_upload_data(context)
        return ConversationHandler.END
    
    # Show processing
    try:
        await query.edit_message_caption(
            caption=(
                "⏳ *Processing...*\n\n"
                "🔍 Checking for duplicate photos...\n"
                "💾 Saving card to database...\n\n"
                "Please wait."
            ),
            parse_mode="Markdown"
        )
    except Exception:
        pass
    
    try:
        # Check for duplicate photo
        photo_exists, existing_card_id = await check_photo_exists(photo_file_id)
        
        if photo_exists:
            # Duplicate found
            app_logger.warning(
                f"📤 Duplicate photo for user {user.id}: "
                f"file_id={photo_file_id[:20]}... (Card #{existing_card_id})"
            )
            
            # Get existing card info
            try:
                from db import get_card_by_id
                existing_card = await get_card_by_id(None, existing_card_id)
                
                if existing_card:
                    existing_char = existing_card.get('character_name', 'Unknown')
                    existing_anime = existing_card.get('anime', 'Unknown')
                    existing_rarity = existing_card.get('rarity', 1)
                    
                    _, _, existing_rarity_emoji = rarity_to_text(existing_rarity)
                    
                    duplicate_msg = (
                        f"This image is already used for:\n\n"
                        f"🎬 *Anime:* {existing_anime}\n"
                        f"👤 *Character:* {existing_char}\n"
                        f"✨ *Rarity:* {existing_rarity_emoji}\n"
                        f"🆔 *Card ID:* `#{existing_card_id}`"
                    )
                else:
                    duplicate_msg = f"This image exists as Card `#{existing_card_id}`"
            except Exception as e:
                error_logger.error(f"Error getting existing card: {e}")
                duplicate_msg = "This image already exists"
            
            # Build options
            keyboard = [
                [InlineKeyboardButton("🖼 Different Photo", callback_data="upload_edit_photo")],
                [InlineKeyboardButton("✏️ Edit Fields", callback_data="upload_edit")],
                [InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_caption(
                caption=(
                    "⚠️ *Duplicate Photo Detected!*\n\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"{duplicate_msg}\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    "🚫 *Why this matters:*\n"
                    "Each card must have a unique image.\n\n"
                    "✅ *What's allowed:*\n"
                    "• Same character, different image ✓\n"
                    "• Same anime, different character ✓\n\n"
                    "❌ *Not allowed:*\n"
                    "• Same exact image ✗\n\n"
                    "💡 Please upload a different photo."
                ),
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
            
            return PREVIEW_CONFIRM
        
        # No duplicate - insert card
        rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity)
        
        app_logger.info(
            f"📤 Inserting card: {character} ({anime}) - "
            f"{rarity_emoji} {rarity_name} by user {user.id}"
        )
        
        # Insert directly into database
        card = await insert_card_direct(
            anime=anime,
            character=character,
            rarity=rarity,
            photo_file_id=photo_file_id,
            uploader_id=user.id
        )
        
        if card is None:
            raise Exception("Failed to insert card")
        
        card_id = card["card_id"]
        
        # Success!
        set_upload_cooldown(user.id)
        total_cards = await get_card_count(None)
        
        app_logger.info(
            f"✅ Card #{card_id} saved: {character} ({anime}) - "
            f"{rarity_emoji} {rarity_name}"
        )
        
        # Success message
        success_caption = (
            "🎉 *Card Uploaded Successfully!*\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 *Card ID:* `#{card_id}`\n"
            f"🎬 *Anime:* {anime}\n"
            f"👤 *Character:* {character}\n"
            f"✨ *Rarity:* {rarity_emoji} {rarity_name} ({rarity_prob}%)\n"
            f"👤 *Uploaded by:* {user.first_name}\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 *Total cards:* {total_cards:,}\n"
            f"🎯 *Now available for catching!*\n\n"
            f"Use /cardinfo {card_id} to view.\n"
            f"Use /upload to add another."
        )
        
        await query.edit_message_caption(
            caption=success_caption,
            parse_mode="Markdown"
        )
        
        clear_upload_data(context)
        
        return ConversationHandler.END
        
    except Exception as e:
        # Error handling
        error_logger.error(
            f"Upload error for user {user.id}: {type(e).__name__}: {e}",
            exc_info=True
        )
        
        # Determine error type
        error_type = type(e).__name__
        error_msg = str(e)
        
        # User-friendly messages
        if "duplicate key" in error_msg.lower():
            friendly_msg = "This card already exists.\nTry a different image."
        elif "constraint" in error_msg.lower():
            friendly_msg = "Database constraint error.\nTry a different combination."
        elif "connection" in error_msg.lower():
            friendly_msg = "Database connection error.\nPlease try again."
        else:
            friendly_msg = f"Error: {error_msg[:100]}"
        
        # Retry keyboard
        keyboard = [
            [InlineKeyboardButton("🔄 Try Again", callback_data="upload_confirm")],
            [InlineKeyboardButton("✏️ Edit", callback_data="upload_edit")],
            [InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await query.edit_message_caption(
                caption=(
                    "❌ *Upload Failed*\n\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"**Type:** {error_type}\n\n"
                    f"{friendly_msg}\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    "💡 *Options:*\n"
                    "• Try again (temporary error)\n"
                    "• Edit your data\n"
                    "• Cancel and restart"
                ),
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        except Exception:
            try:
                await query.message.reply_text(
                    f"❌ Upload failed: {friendly_msg}\n\n"
                    "Use /upload to try again.",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        
        return PREVIEW_CONFIRM


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
# 🟥 Cancel Handlers
# ============================================================

async def upload_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle upload cancellation via callback."""
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
# 🔧 Back Navigation
# ============================================================

async def back_navigation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle back navigation."""
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
    """Quick upload: /quickupload Anime | Character | Rarity"""
    user = update.effective_user
    message = update.message

    if not Config.is_admin(user.id):
        await message.reply_text("❌ Admin only.")
        return

    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.reply_text(
            "📤 *Quick Upload*\n\n"
            "Reply to a photo:\n"
            "`/quickupload Anime | Character | Rarity`\n\n"
            "Example:\n"
            "`/quickupload Naruto | Itachi | 8`",
            parse_mode="Markdown"
        )
        return

    args_text = message.text.replace("/quickupload", "").strip()

    if not args_text:
        await message.reply_text("❌ Format: `Anime | Character | Rarity`", parse_mode="Markdown")
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
                "epic": 5, "limited": 6, "platinum": 7, "emerald": 8,
                "crystal": 9, "mythical": 10, "legendary": 11
            }
            rarity_id = rarity_names.get(rarity_input)

    if rarity_id is None:
        rarity_id = get_random_rarity()

    photo_file_id = message.reply_to_message.photo[-1].file_id
    
    # Check duplicate
    photo_exists, existing_card_id = await check_photo_exists(photo_file_id)
    
    if photo_exists:
        await message.reply_text(
            f"⚠️ Duplicate photo!\n"
            f"Already exists as Card `#{existing_card_id}`.",
            parse_mode="Markdown"
        )
        return

    try:
        card = await insert_card_direct(
            anime=anime,
            character=character,
            rarity=rarity_id,
            photo_file_id=photo_file_id,
            uploader_id=user.id
        )

        if card:
            rarity_name, _, rarity_emoji = rarity_to_text(rarity_id)
            await message.reply_text(
                f"✅ *Quick Upload Success!*\n\n"
                f"🆔 ID: `#{card['card_id']}`\n"
                f"🎬 {anime}\n"
                f"👤 {character}\n"
                f"✨ {rarity_emoji} {rarity_name}",
                parse_mode="Markdown"
            )
        else:
            await message.reply_text("⚠️ Failed to save!")

    except Exception as e:
        error_logger.error(f"Quick upload failed: {e}", exc_info=True)
        await message.reply_text(f"❌ Error: {str(e)[:100]}")


# ============================================================
# 🔧 Handlers Export
# ============================================================

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
    conversation_timeout=300,
)

upload_rarity_callback_handler = CallbackQueryHandler(
    lambda u, c: None,
    pattern=r"^upload_rarity_"
)

quick_upload_handler = CommandHandler("quickupload", quick_upload)