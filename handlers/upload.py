# ============================================================
# 📁 File: handlers/upload.py
# 📍 Location: telegram_card_bot/handlers/upload.py
# 📝 Description: Professional card upload system with notifications
# ============================================================

from datetime import datetime
from typing import Optional, Dict, Any, List

from telegram import (
    Update,
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
from telegram.error import TelegramError, BadRequest

from config import Config
from db import db, ensure_user, get_card_count
from utils.logger import app_logger, error_logger, log_command
from utils.rarity import get_random_rarity, rarity_to_text

# Role check imports
from handlers.roles import is_uploader
from handlers.notifications import send_upload_notifications


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
EDIT_MENU = 7


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
        'photo_unique_id': None,
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
    """Get list of characters for a specific anime."""
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


async def check_photo_exists(photo_unique_id: str) -> tuple[bool, Optional[int]]:
    """Check if a photo already exists using unique_id."""
    if not db.is_connected:
        return False, None
    
    try:
        query = """
            SELECT card_id, character_name, anime 
            FROM cards 
            WHERE photo_unique_id = $1 AND is_active = TRUE
            LIMIT 1
        """
        result = await db.fetchrow(query, photo_unique_id)
        
        if result:
            return True, result['card_id']
        return False, None
        
    except Exception as e:
        if "column" in str(e).lower() and "does not exist" in str(e).lower():
            return False, None
        error_logger.error(f"Error checking photo existence: {e}")
        return False, None


# ============================================================
# 🆕 Direct Card Insert
# ============================================================

async def insert_card_direct(
    anime: str,
    character: str,
    rarity: int,
    photo_file_id: str,
    photo_unique_id: str,
    uploader_id: int
) -> Optional[Dict[str, Any]]:
    """Insert a card directly into the database."""
    if not db.is_connected:
        raise Exception("Database not connected")
    
    if not 1 <= rarity <= 11:
        raise ValueError(f"Invalid rarity: {rarity}. Must be 1-11.")
    
    try:
        check_column = """
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'cards' AND column_name = 'photo_unique_id'
        """
        column_exists = await db.fetchrow(check_column)
        
        if column_exists:
            query = """
                INSERT INTO cards (
                    anime, character_name, rarity, photo_file_id,
                    photo_unique_id, uploader_id, description, tags,
                    created_at, is_active, total_caught
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), TRUE, 0)
                RETURNING *
            """
            tags = [anime.lower(), character.lower().split()[0] if character else ""]
            description = f"Uploaded by user {uploader_id}"
            
            result = await db.fetchrow(
                query, anime, character, rarity, photo_file_id,
                photo_unique_id, uploader_id, description, tags
            )
        else:
            query = """
                INSERT INTO cards (
                    anime, character_name, rarity, photo_file_id,
                    uploader_id, description, tags,
                    created_at, is_active, total_caught
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), TRUE, 0)
                RETURNING *
            """
            tags = [anime.lower(), character.lower().split()[0] if character else ""]
            description = f"Uploaded by user {uploader_id}"
            
            result = await db.fetchrow(
                query, anime, character, rarity, photo_file_id,
                uploader_id, description, tags
            )
        
        if result:
            app_logger.info(
                f"✅ Card inserted: ID={result['card_id']}, "
                f"{character} ({anime}), rarity={rarity}"
            )
            return dict(result)
        
        return None
        
    except Exception as e:
        error_msg = str(e).lower()
        
        if "unique" in error_msg or "duplicate" in error_msg:
            if "anime" in error_msg and "character" in error_msg:
                try:
                    query = """
                        INSERT INTO cards (
                            anime, character_name, rarity, photo_file_id,
                            uploader_id, created_at, is_active, total_caught
                        )
                        VALUES ($1, $2, $3, $4, $5, NOW(), TRUE, 0)
                        RETURNING *
                    """
                    result = await db.fetchrow(
                        query, anime, character, rarity, photo_file_id, uploader_id
                    )
                    if result:
                        return dict(result)
                except Exception:
                    pass
        
        error_logger.error(f"Card insert failed: {e}", exc_info=True)
        raise


async def ensure_no_unique_constraint() -> bool:
    """Remove the unique constraint on (anime, character_name) if it exists."""
    if not db.is_connected:
        return False
    
    try:
        query = """
            SELECT constraint_name 
            FROM information_schema.table_constraints 
            WHERE table_name = 'cards' 
            AND constraint_type = 'UNIQUE'
            AND constraint_name LIKE '%anime%character%'
        """
        result = await db.fetchrow(query)
        
        if result:
            constraint_name = result['constraint_name']
            drop_query = f"ALTER TABLE cards DROP CONSTRAINT IF EXISTS {constraint_name}"
            await db.execute(drop_query)
            app_logger.info(f"✅ Removed constraint: {constraint_name}")
            return True
        
        try:
            await db.execute(
                "ALTER TABLE cards DROP CONSTRAINT IF EXISTS cards_anime_character_unique"
            )
        except Exception:
            pass
        
        return True
        
    except Exception as e:
        error_logger.error(f"Error removing constraint: {e}")
        return False


async def add_photo_unique_id_column() -> bool:
    """Add photo_unique_id column if it doesn't exist."""
    if not db.is_connected:
        return False
    
    try:
        await db.execute("""
            ALTER TABLE cards 
            ADD COLUMN IF NOT EXISTS photo_unique_id TEXT
        """)
        
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_cards_photo_unique_id 
            ON cards(photo_unique_id)
        """)
        
        return True
    except Exception as e:
        error_logger.error(f"Error adding photo_unique_id column: {e}")
        return False


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
            "❌ *ᴜᴘʟᴏᴀᴅ ʀᴇꜱᴛʀɪᴄᴛᴇᴅ*\n\n"
            "Card uploads can only be done in private messages.\n"
            f"Please message me directly: @{Config.BOT_USERNAME}",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    # Check upload permissions (Owner, Dev, Admin, or Uploader)
    if not await is_uploader(user.id):
        await update.message.reply_text(
            "❌ *ᴘᴇʀᴍɪꜱꜱɪᴏɴ ᴅᴇɴɪᴇᴅ*\n\n"
            "Only authorized uploaders can add new cards.\n"
            "Contact an admin if you'd like to contribute!",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    # Check cooldown
    is_cooldown, remaining = check_upload_cooldown(user.id)
    if is_cooldown:
        await update.message.reply_text(
            f"⏳ *ᴛᴏᴏ ꜰᴀꜱᴛ!*\n\n"
            f"Please wait {remaining} seconds before uploading another card.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    # Ensure database is ready
    await ensure_no_unique_constraint()
    await add_photo_unique_id_column()

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
    
    anime_list = await get_existing_anime_list()
    
    keyboard = []
    
    for anime in anime_list[:10]:
        keyboard.append([
            InlineKeyboardButton(f"🎬 {anime}", callback_data=f"up_anime:{anime[:50]}")
        ])
    
    if len(anime_list) > 10:
        keyboard.append([
            InlineKeyboardButton(f"📄 More ({len(anime_list) - 10} more)...", callback_data="up_anime_more")
        ])
    
    keyboard.append([
        InlineKeyboardButton("➕ Add New Anime", callback_data="up_anime_new")
    ])
    
    keyboard.append([
        InlineKeyboardButton("❌ Cancel", callback_data="up_cancel")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "📤 *ᴄᴀʀᴅ ᴜᴘʟᴏᴀᴅ - ꜱᴛᴇᴘ 1/5*\n\n"
        "🎬 *Choose Anime:*\n\n"
        "Select an existing anime or add a new one."
    )
    
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text=text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                text=text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
    except (BadRequest, TelegramError):
        if update.effective_message:
            await update.effective_message.reply_text(
                text=text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
    
    return SELECT_ANIME


async def handle_anime_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle anime selection callback."""
    query = update.callback_query
    data = query.data
    
    try:
        await query.answer()
    except TelegramError:
        pass
    
    if data == "up_anime_new":
        try:
            await query.edit_message_text(
                "📤 *ᴄᴀʀᴅ ᴜᴘʟᴏᴀᴅ - ꜱᴛᴇᴘ 1/5*\n\n"
                "🎬 *Enter the new Anime name:*\n\n"
                "Type the anime/series name:",
                parse_mode="Markdown"
            )
        except TelegramError:
            await query.message.reply_text(
                "🎬 *Enter the new Anime name:*",
                parse_mode="Markdown"
            )
        return ADD_NEW_ANIME
    
    elif data == "up_anime_more":
        await query.answer("Use 'Add New Anime' for now!", show_alert=True)
        return SELECT_ANIME
    
    elif data.startswith("up_anime:"):
        anime = data.replace("up_anime:", "")
        update_upload_data(context, anime=anime)
        return await show_character_selection(update, context)
    
    return SELECT_ANIME


async def handle_anime_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle new anime name input."""
    anime_name = update.message.text.strip()
    
    if len(anime_name) < 2:
        await update.message.reply_text(
            "⚠️ Name must be at least 2 characters. Try again:",
            parse_mode="Markdown"
        )
        return ADD_NEW_ANIME
    
    if len(anime_name) > 100:
        await update.message.reply_text(
            "⚠️ Name must be under 100 characters. Try again:",
            parse_mode="Markdown"
        )
        return ADD_NEW_ANIME
    
    update_upload_data(context, anime=anime_name)
    app_logger.info(f"📤 New anime: {anime_name}")
    
    return await show_character_selection(update, context)


# ============================================================
# 🟪 Step 2: Select Character
# ============================================================

async def show_character_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show character selection menu."""
    
    upload_data = get_upload_data(context)
    anime = upload_data.get('anime', 'Unknown')
    
    character_list = await get_characters_for_anime(anime)
    
    keyboard = []
    
    for character in character_list[:10]:
        keyboard.append([
            InlineKeyboardButton(f"👤 {character}", callback_data=f"up_char:{character[:50]}")
        ])
    
    if len(character_list) > 10:
        keyboard.append([
            InlineKeyboardButton(f"📄 More...", callback_data="up_char_more")
        ])
    
    keyboard.append([
        InlineKeyboardButton("➕ Add New Character", callback_data="up_char_new")
    ])
    
    keyboard.append([
        InlineKeyboardButton("⬅️ Back", callback_data="up_back_anime"),
        InlineKeyboardButton("❌ Cancel", callback_data="up_cancel")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "📤 *ᴄᴀʀᴅ ᴜᴘʟᴏᴀᴅ - ꜱᴛᴇᴘ 2/5*\n\n"
        f"🎬 *Anime:* {anime}\n\n"
        "👤 *Choose Character:*\n\n"
        "💡 Same character can have multiple cards."
    )
    
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text=text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                text=text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
    except (BadRequest, TelegramError):
        if update.effective_message:
            await update.effective_message.reply_text(
                text=text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
    
    return SELECT_CHARACTER


async def handle_character_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle character selection callback."""
    query = update.callback_query
    data = query.data
    
    try:
        await query.answer()
    except TelegramError:
        pass
    
    if data == "up_char_new":
        upload_data = get_upload_data(context)
        anime = upload_data.get('anime', 'Unknown')
        
        try:
            await query.edit_message_text(
                f"📤 *ᴄᴀʀᴅ ᴜᴘʟᴏᴀᴅ - ꜱᴛᴇᴘ 2/5*\n\n"
                f"🎬 *Anime:* {anime}\n\n"
                f"👤 *Enter Character name:*",
                parse_mode="Markdown"
            )
        except TelegramError:
            await query.message.reply_text(
                "👤 *Enter Character name:*",
                parse_mode="Markdown"
            )
        return ADD_NEW_CHARACTER
    
    elif data == "up_char_more":
        await query.answer("Use 'Add New Character'!", show_alert=True)
        return SELECT_CHARACTER
    
    elif data.startswith("up_char:"):
        character = data.replace("up_char:", "")
        update_upload_data(context, character=character)
        return await show_rarity_selection(update, context)
    
    elif data == "up_back_anime":
        return await show_anime_selection(update, context)
    
    return SELECT_CHARACTER


async def handle_character_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle new character name input."""
    character_name = update.message.text.strip()
    
    if len(character_name) < 2:
        await update.message.reply_text("⚠️ Name must be at least 2 characters.")
        return ADD_NEW_CHARACTER
    
    if len(character_name) > 100:
        await update.message.reply_text("⚠️ Name must be under 100 characters.")
        return ADD_NEW_CHARACTER
    
    update_upload_data(context, character=character_name)
    app_logger.info(f"📤 Character: {character_name}")
    
    return await show_rarity_selection(update, context)


# ============================================================
# 🟫 Step 3: Select Rarity
# ============================================================

async def show_rarity_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show rarity selection menu."""
    
    upload_data = get_upload_data(context)
    anime = upload_data.get('anime', 'Unknown')
    character = upload_data.get('character', 'Unknown')
    
    keyboard = []
    rarity_buttons = []
    
    for rarity_id in range(1, 12):
        rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity_id)
        
        button = InlineKeyboardButton(
            f"{rarity_emoji} {rarity_name}",
            callback_data=f"up_rarity:{rarity_id}"
        )
        rarity_buttons.append(button)
        
        if len(rarity_buttons) == 2:
            keyboard.append(rarity_buttons)
            rarity_buttons = []
    
    if rarity_buttons:
        keyboard.append(rarity_buttons)
    
    keyboard.append([
        InlineKeyboardButton("🎲 Random", callback_data="up_rarity:random")
    ])
    
    keyboard.append([
        InlineKeyboardButton("⬅️ Back", callback_data="up_back_char"),
        InlineKeyboardButton("❌ Cancel", callback_data="up_cancel")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "📤 *ᴄᴀʀᴅ ᴜᴘʟᴏᴀᴅ - ꜱᴛᴇᴘ 3/5*\n\n"
        f"🎬 *Anime:* {anime}\n"
        f"👤 *Character:* {character}\n\n"
        "✨ *Choose Rarity:*"
    )
    
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text=text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                text=text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
    except (BadRequest, TelegramError):
        pass
    
    return SELECT_RARITY


async def handle_rarity_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle rarity selection callback."""
    query = update.callback_query
    data = query.data
    
    try:
        await query.answer()
    except TelegramError:
        pass
    
    if data.startswith("up_rarity:"):
        rarity_value = data.replace("up_rarity:", "")
        
        if rarity_value == "random":
            rarity_id = get_random_rarity()
        else:
            rarity_id = int(rarity_value)
        
        update_upload_data(context, rarity=rarity_id)
        
        rarity_name, _, rarity_emoji = rarity_to_text(rarity_id)
        app_logger.info(f"📤 Rarity: {rarity_id} ({rarity_name})")
        
        return await show_photo_upload(update, context)
    
    elif data == "up_back_char":
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
    
    rarity_name, _, rarity_emoji = rarity_to_text(rarity)
    
    keyboard = [
        [
            InlineKeyboardButton("⬅️ Back", callback_data="up_back_rarity"),
            InlineKeyboardButton("❌ Cancel", callback_data="up_cancel")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "📤 *ᴄᴀʀᴅ ᴜᴘʟᴏᴀᴅ - ꜱᴛᴇᴘ 4/5*\n\n"
        f"🎬 *Anime:* {anime}\n"
        f"👤 *Character:* {character}\n"
        f"✨ *Rarity:* {rarity_emoji} {rarity_name}\n\n"
        "🖼️ *Send the card photo now:*\n\n"
        "📷 Send as photo (not file)"
    )
    
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text=text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                text=text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
    except (BadRequest, TelegramError):
        pass
    
    return UPLOAD_PHOTO


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle photo upload."""
    message = update.message
    
    photo_file_id = None
    photo_unique_id = None
    
    if message.photo:
        photo = message.photo[-1]
        photo_file_id = photo.file_id
        photo_unique_id = photo.file_unique_id
    elif message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
        photo_file_id = message.document.file_id
        photo_unique_id = message.document.file_unique_id
    
    if not photo_file_id:
        await message.reply_text(
            "❌ Please send a photo (📷), not a file.",
            parse_mode="Markdown"
        )
        return UPLOAD_PHOTO
    
    update_upload_data(
        context, 
        photo_file_id=photo_file_id, 
        photo_unique_id=photo_unique_id
    )
    
    app_logger.info(f"📤 Photo received: {photo_unique_id}")
    
    return await show_preview(update, context)


async def handle_photo_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle back button in photo upload."""
    query = update.callback_query
    data = query.data
    
    try:
        await query.answer()
    except TelegramError:
        pass
    
    if data == "up_back_rarity":
        return await show_rarity_selection(update, context)
    
    return UPLOAD_PHOTO


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
        "🔎 *ᴘʀᴇᴠɪᴇᴡ - ꜱᴛᴇᴘ 5/5*\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🎬 *Anime:* {anime}\n"
        f"👤 *Character:* {character}\n"
        f"✨ *Rarity:* {rarity_emoji} {rarity_name}\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "✅ Press *Confirm* to save this card."
    )
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm & Save", callback_data="up_confirm"),
        ],
        [
            InlineKeyboardButton("✏️ Edit", callback_data="up_edit"),
            InlineKeyboardButton("❌ Cancel", callback_data="up_cancel")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        if update.callback_query:
            await update.callback_query.message.reply_photo(
                photo=photo_file_id,
                caption=caption,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_photo(
                photo=photo_file_id,
                caption=caption,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
    except TelegramError as e:
        error_logger.error(f"Preview error: {e}")
        await update.effective_message.reply_text(
            "❌ Error showing preview. Use /upload to restart."
        )
        return ConversationHandler.END
    
    return PREVIEW_CONFIRM


async def handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle upload confirmation."""
    query = update.callback_query
    user = query.from_user
    
    try:
        await query.answer("Processing...")
    except TelegramError:
        pass
    
    upload_data = get_upload_data(context)
    anime = upload_data.get('anime')
    character = upload_data.get('character')
    rarity = upload_data.get('rarity')
    photo_file_id = upload_data.get('photo_file_id')
    photo_unique_id = upload_data.get('photo_unique_id', '')
    
    if not all([anime, character, rarity, photo_file_id]):
        try:
            await query.edit_message_caption(
                caption="❌ Missing data. Use /upload to restart.",
                parse_mode="Markdown"
            )
        except TelegramError:
            pass
        clear_upload_data(context)
        return ConversationHandler.END
    
    # Show processing
    try:
        await query.edit_message_caption(
            caption="⏳ *ꜱᴀᴠɪɴɢ ᴄᴀʀᴅ...*",
            parse_mode="Markdown"
        )
    except TelegramError:
        pass
    
    try:
        # Check for duplicate photo
        if photo_unique_id:
            photo_exists, existing_id = await check_photo_exists(photo_unique_id)
            if photo_exists:
                keyboard = [
                    [InlineKeyboardButton("🖼️ New Photo", callback_data="up_edit_photo")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="up_cancel")]
                ]
                await query.edit_message_caption(
                    caption=(
                        f"⚠️ *ᴅᴜᴘʟɪᴄᴀᴛᴇ ᴘʜᴏᴛᴏ!*\n\n"
                        f"This image is already Card `#{existing_id}`.\n\n"
                        f"Please use a different image."
                    ),
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return PREVIEW_CONFIRM
        
        # Insert card
        card = await insert_card_direct(
            anime=anime,
            character=character,
            rarity=rarity,
            photo_file_id=photo_file_id,
            photo_unique_id=photo_unique_id or "",
            uploader_id=user.id
        )
        
        if not card:
            raise Exception("Insert returned None")
        
        card_id = card["card_id"]
        rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity)
        
        set_upload_cooldown(user.id)
        total_cards = await get_card_count(None)
        
        # Send notifications (channel + groups)
        notification_results = await send_upload_notifications(
            bot=context.bot,
            card=card,
            uploader_name=user.first_name,
            uploader_id=user.id
        )
        
        # Build success message
        channel_status = "✅" if notification_results["channel_archived"] else "❌"
        groups_notified = notification_results["groups_notified"]
        groups_total = notification_results["groups_total"]
        
        success_caption = (
            "🎉 *ᴜᴘʟᴏᴀᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟ!*\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 *Card ID:* `#{card_id}`\n"
            f"🎬 *Anime:* {anime}\n"
            f"👤 *Character:* {character}\n"
            f"✨ *Rarity:* {rarity_emoji} {rarity_name}\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 *Total cards:* {total_cards:,}\n\n"
            f"📺 *Channel:* {channel_status}\n"
            f"📢 *Groups:* {groups_notified}/{groups_total}\n\n"
            f"Use /upload to add more!"
        )
        
        await query.edit_message_caption(
            caption=success_caption,
            parse_mode="Markdown"
        )
        
        app_logger.info(f"✅ Card #{card_id} uploaded by {user.id}")
        
        clear_upload_data(context)
        return ConversationHandler.END
        
    except Exception as e:
        error_logger.error(f"Upload failed: {e}", exc_info=True)
        
        keyboard = [
            [InlineKeyboardButton("🔄 Retry", callback_data="up_confirm")],
            [InlineKeyboardButton("❌ Cancel", callback_data="up_cancel")]
        ]
        
        try:
            await query.edit_message_caption(
                caption=(
                    f"❌ *ᴜᴘʟᴏᴀᴅ ꜰᴀɪʟᴇᴅ*\n\n"
                    f"Error: {str(e)[:100]}\n\n"
                    f"Please try again or cancel."
                ),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except TelegramError:
            pass
        
        return PREVIEW_CONFIRM


# ============================================================
# ✏️ Edit Menu
# ============================================================

async def handle_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show edit menu."""
    query = update.callback_query
    
    try:
        await query.answer()
    except TelegramError:
        pass
    
    upload_data = get_upload_data(context)
    anime = upload_data.get('anime', 'Unknown')
    character = upload_data.get('character', 'Unknown')
    rarity = upload_data.get('rarity', 1)
    
    rarity_name, _, rarity_emoji = rarity_to_text(rarity)
    
    keyboard = [
        [InlineKeyboardButton("🎬 Edit Anime", callback_data="up_edit_anime")],
        [InlineKeyboardButton("👤 Edit Character", callback_data="up_edit_char")],
        [InlineKeyboardButton("✨ Edit Rarity", callback_data="up_edit_rarity")],
        [InlineKeyboardButton("🖼️ Edit Photo", callback_data="up_edit_photo")],
        [InlineKeyboardButton("⬅️ Back", callback_data="up_back_preview")],
        [InlineKeyboardButton("❌ Cancel", callback_data="up_cancel")],
    ]
    
    text = (
        "✏️ *ᴇᴅɪᴛ ᴜᴘʟᴏᴀᴅ*\n\n"
        f"🎬 Anime: {anime}\n"
        f"👤 Character: {character}\n"
        f"✨ Rarity: {rarity_emoji} {rarity_name}\n\n"
        "What do you want to edit?"
    )
    
    try:
        await query.edit_message_caption(
            caption=text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except (BadRequest, TelegramError):
        try:
            await query.message.reply_text(
                text=text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except TelegramError:
            pass
    
    return EDIT_MENU


async def handle_edit_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle edit selection."""
    query = update.callback_query
    data = query.data
    
    try:
        await query.answer()
    except TelegramError:
        pass
    
    if data == "up_edit_anime":
        return await show_anime_selection(update, context)
    elif data == "up_edit_char":
        return await show_character_selection(update, context)
    elif data == "up_edit_rarity":
        return await show_rarity_selection(update, context)
    elif data == "up_edit_photo":
        return await show_photo_upload(update, context)
    elif data == "up_back_preview":
        return await show_preview(update, context)
    
    return EDIT_MENU


# ============================================================
# ❌ Cancel Handler
# ============================================================

async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle cancel callback."""
    query = update.callback_query
    
    try:
        await query.answer("Cancelled")
    except TelegramError:
        pass
    
    clear_upload_data(context)
    
    try:
        await query.edit_message_caption(
            caption="❌ *ᴜᴘʟᴏᴀᴅ ᴄᴀɴᴄᴇʟʟᴇᴅ*\n\nUse /upload to start again.",
            parse_mode="Markdown"
        )
    except (BadRequest, TelegramError):
        try:
            await query.edit_message_text(
                text="❌ *ᴜᴘʟᴏᴀᴅ ᴄᴀɴᴄᴇʟʟᴇᴅ*\n\nUse /upload to start again.",
                parse_mode="Markdown"
            )
        except TelegramError:
            try:
                await query.message.reply_text(
                    "❌ *ᴜᴘʟᴏᴀᴅ ᴄᴀɴᴄᴇʟʟᴇᴅ*\n\nUse /upload to start again.",
                    parse_mode="Markdown"
                )
            except TelegramError:
                pass
    
    app_logger.info(f"📤 Upload cancelled by {query.from_user.id}")
    
    return ConversationHandler.END


async def handle_cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /cancel command."""
    clear_upload_data(context)
    
    await update.message.reply_text(
        "❌ *ᴜᴘʟᴏᴀᴅ ᴄᴀɴᴄᴇʟʟᴇᴅ*\n\nUse /upload to start again.",
        parse_mode="Markdown"
    )
    
    return ConversationHandler.END


# ============================================================
# 📤 Quick Upload
# ============================================================

async def quick_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Quick upload: /quickupload Anime | Character | Rarity"""
    user = update.effective_user
    message = update.message

    if not await is_uploader(user.id):
        await message.reply_text("❌ Uploaders only.")
        return

    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.reply_text(
            "📤 *ǫᴜɪᴄᴋ ᴜᴘʟᴏᴀᴅ*\n\n"
            "Reply to a photo with:\n"
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
        else:
            rarity_names = {
                "normal": 1, "common": 2, "uncommon": 3, "rare": 4,
                "epic": 5, "limited": 6, "platinum": 7, "emerald": 8,
                "crystal": 9, "mythical": 10, "legendary": 11
            }
            rarity_id = rarity_names.get(rarity_input)

    if rarity_id is None:
        rarity_id = get_random_rarity()

    photo = message.reply_to_message.photo[-1]
    photo_file_id = photo.file_id
    photo_unique_id = photo.file_unique_id

    await ensure_no_unique_constraint()

    try:
        card = await insert_card_direct(
            anime=anime,
            character=character,
            rarity=rarity_id,
            photo_file_id=photo_file_id,
            photo_unique_id=photo_unique_id,
            uploader_id=user.id
        )

        if card:
            rarity_name, _, rarity_emoji = rarity_to_text(rarity_id)
            
            # Send notifications
            notification_results = await send_upload_notifications(
                bot=context.bot,
                card=card,
                uploader_name=user.first_name,
                uploader_id=user.id
            )
            
            channel_status = "✅" if notification_results["channel_archived"] else "❌"
            groups_notified = notification_results["groups_notified"]
            
            await message.reply_text(
                f"✅ *ᴄᴀʀᴅ ᴜᴘʟᴏᴀᴅᴇᴅ!*\n\n"
                f"🆔 `#{card['card_id']}`\n"
                f"🎬 {anime}\n"
                f"👤 {character}\n"
                f"✨ {rarity_emoji} {rarity_name}\n\n"
                f"📺 Channel: {channel_status}\n"
                f"📢 Groups: {groups_notified} notified",
                parse_mode="Markdown"
            )
        else:
            await message.reply_text("❌ Failed to save card.")

    except Exception as e:
        error_logger.error(f"Quick upload failed: {e}", exc_info=True)
        await message.reply_text(f"❌ Error: {str(e)[:100]}")


# ============================================================
# 🔧 Conversation Handler Export
# ============================================================

cancel_pattern = r"^up_cancel$"

upload_conversation_handler = ConversationHandler(
    entry_points=[
        CommandHandler("upload", upload_start),
    ],
    states={
        SELECT_ANIME: [
            CallbackQueryHandler(handle_anime_callback, pattern=r"^up_anime"),
            CallbackQueryHandler(handle_cancel, pattern=cancel_pattern),
        ],
        ADD_NEW_ANIME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_anime_text),
            CommandHandler("cancel", handle_cancel_command),
        ],
        SELECT_CHARACTER: [
            CallbackQueryHandler(handle_character_callback, pattern=r"^up_char"),
            CallbackQueryHandler(handle_character_callback, pattern=r"^up_back_anime$"),
            CallbackQueryHandler(handle_cancel, pattern=cancel_pattern),
        ],
        ADD_NEW_CHARACTER: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_character_text),
            CommandHandler("cancel", handle_cancel_command),
        ],
        SELECT_RARITY: [
            CallbackQueryHandler(handle_rarity_callback, pattern=r"^up_rarity"),
            CallbackQueryHandler(handle_rarity_callback, pattern=r"^up_back_char$"),
            CallbackQueryHandler(handle_cancel, pattern=cancel_pattern),
        ],
        UPLOAD_PHOTO: [
            MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_photo),
            CallbackQueryHandler(handle_photo_back, pattern=r"^up_back_rarity$"),
            CallbackQueryHandler(handle_cancel, pattern=cancel_pattern),
        ],
        PREVIEW_CONFIRM: [
            CallbackQueryHandler(handle_confirm, pattern=r"^up_confirm$"),
            CallbackQueryHandler(handle_edit, pattern=r"^up_edit$"),
            CallbackQueryHandler(handle_edit_selection, pattern=r"^up_edit_"),
            CallbackQueryHandler(handle_edit_selection, pattern=r"^up_back_preview$"),
            CallbackQueryHandler(handle_cancel, pattern=cancel_pattern),
        ],
        EDIT_MENU: [
            CallbackQueryHandler(handle_edit_selection, pattern=r"^up_edit_"),
            CallbackQueryHandler(handle_edit_selection, pattern=r"^up_back_preview$"),
            CallbackQueryHandler(handle_cancel, pattern=cancel_pattern),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", handle_cancel_command),
        CallbackQueryHandler(handle_cancel, pattern=cancel_pattern),
    ],
    name="upload_conversation",
    persistent=False,
    conversation_timeout=300,
    per_message=False,
)

upload_rarity_callback_handler = CallbackQueryHandler(
    lambda u, c: None,
    pattern=r"^upload_rarity_never_match$"
)

quick_upload_handler = CommandHandler("quickupload", quick_upload)