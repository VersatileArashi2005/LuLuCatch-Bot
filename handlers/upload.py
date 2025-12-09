# ============================================================
# 📁 File: handlers/upload.py
# 📍 Location: telegram_card_bot/handlers/upload.py
# 📝 Description: Card upload system with conversation flow
# ============================================================

import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from io import BytesIO

from telegram import (
    Update,
    Message,
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
    format_rarity_display,
    RARITY_TABLE,
)


# ============================================================
# 📊 Conversation States
# ============================================================

UPLOAD_ANIME = 0      # Waiting for anime name
UPLOAD_CHARACTER = 1  # Waiting for character name
UPLOAD_PHOTO = 2      # Waiting for photo
UPLOAD_CONFIRM = 3    # Waiting for confirmation
UPLOAD_RARITY = 4     # Optional: manual rarity selection


# ============================================================
# ⏱️ Upload Cooldown Management
# ============================================================

# Store last upload time per user: {user_id: datetime}
_upload_cooldowns: Dict[int, datetime] = {}

# Cooldown duration in seconds
UPLOAD_COOLDOWN_SECONDS = 5


def check_upload_cooldown(user_id: int) -> tuple[bool, int]:
    """
    Check if user is on upload cooldown.
    
    Args:
        user_id: Telegram user ID
        
    Returns:
        Tuple of (is_on_cooldown: bool, seconds_remaining: int)
    """
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


def clear_upload_cooldown(user_id: int) -> None:
    """Clear the upload cooldown for a user."""
    _upload_cooldowns.pop(user_id, None)


# ============================================================
# 📝 Temporary Upload Data Storage
# ============================================================

# Store upload data during conversation: {user_id: {...}}
_upload_data: Dict[int, Dict[str, Any]] = {}


def get_upload_data(user_id: int) -> Dict[str, Any]:
    """Get or create upload data for a user."""
    if user_id not in _upload_data:
        _upload_data[user_id] = {}
    return _upload_data[user_id]


def clear_upload_data(user_id: int) -> None:
    """Clear upload data for a user."""
    _upload_data.pop(user_id, None)


# ============================================================
# 🎴 Upload Command Handlers
# ============================================================

async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle /upload command - Start the upload conversation.
    
    Only works in private messages. Admins/uploaders only.
    """
    user = update.effective_user
    chat = update.effective_chat
    
    # Log the command
    log_command(user.id, "upload", chat.id)
    
    # ========================================
    # Check if in private chat
    # ========================================
    if chat.type != ChatType.PRIVATE:
        await update.message.reply_text(
            "❌ *Upload Restricted*\n\n"
            "Card uploads can only be done in private messages.\n"
            "Please message me directly: @" + Config.BOT_USERNAME,
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    
    # ========================================
    # Check admin permissions
    # ========================================
    if not Config.is_admin(user.id):
        await update.message.reply_text(
            "❌ *Permission Denied*\n\n"
            "Only authorized uploaders can add new cards.\n"
            "Contact an admin if you'd like to contribute!",
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    
    # ========================================
    # Check cooldown
    # ========================================
    is_cooldown, remaining = check_upload_cooldown(user.id)
    if is_cooldown:
        await update.message.reply_text(
            f"⏳ *Too Fast!*\n\n"
            f"Please wait {remaining} seconds before uploading another card.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    
    # ========================================
    # Ensure user exists in database
    # ========================================
    await ensure_user(
        pool=None,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    # ========================================
    # Clear any previous upload data
    # ========================================
    clear_upload_data(user.id)
    
    # ========================================
    # Send welcome message with cancel button
    # ========================================
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel Upload", callback_data="upload_cancel")]
    ])
    
    await update.message.reply_text(
        "📤 *Card Upload Wizard*\n\n"
        "Let's add a new card to the collection!\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📝 *Step 1/3*: Enter the anime/series name\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Examples:\n"
        "• `Naruto`\n"
        "• `One Piece`\n"
        "• `Attack on Titan`\n\n"
        "💡 Type the anime name or /cancel to abort.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    
    app_logger.info(f"📤 Upload started by user {user.id} ({user.first_name})")
    
    return UPLOAD_ANIME


async def upload_anime_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle anime name input.
    
    Validates and stores the anime name, then asks for character name.
    """
    user = update.effective_user
    anime_name = update.message.text.strip()
    
    # ========================================
    # Validate anime name
    # ========================================
    if len(anime_name) < 2:
        await update.message.reply_text(
            "⚠️ *Invalid Name*\n\n"
            "Anime name must be at least 2 characters.\n"
            "Please try again:",
            parse_mode="Markdown"
        )
        return UPLOAD_ANIME
    
    if len(anime_name) > 100:
        await update.message.reply_text(
            "⚠️ *Name Too Long*\n\n"
            "Anime name must be under 100 characters.\n"
            "Please try again:",
            parse_mode="Markdown"
        )
        return UPLOAD_ANIME
    
    # ========================================
    # Store anime name
    # ========================================
    upload_data = get_upload_data(user.id)
    upload_data["anime"] = anime_name
    
    app_logger.info(f"📤 Upload: User {user.id} entered anime '{anime_name}'")
    
    # ========================================
    # Ask for character name
    # ========================================
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Go Back", callback_data="upload_back_anime")],
        [InlineKeyboardButton("❌ Cancel Upload", callback_data="upload_cancel")]
    ])
    
    await update.message.reply_text(
        f"✅ *Anime:* `{anime_name}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📝 *Step 2/3*: Enter the character name\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Examples:\n"
        "• `Naruto Uzumaki`\n"
        "• `Monkey D. Luffy`\n"
        "• `Eren Yeager`\n\n"
        "💡 Type the character name:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    
    return UPLOAD_CHARACTER


async def upload_character_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle character name input.
    
    Validates and stores the character name, then asks for photo.
    """
    user = update.effective_user
    character_name = update.message.text.strip()
    
    # ========================================
    # Validate character name
    # ========================================
    if len(character_name) < 2:
        await update.message.reply_text(
            "⚠️ *Invalid Name*\n\n"
            "Character name must be at least 2 characters.\n"
            "Please try again:",
            parse_mode="Markdown"
        )
        return UPLOAD_CHARACTER
    
    if len(character_name) > 100:
        await update.message.reply_text(
            "⚠️ *Name Too Long*\n\n"
            "Character name must be under 100 characters.\n"
            "Please try again:",
            parse_mode="Markdown"
        )
        return UPLOAD_CHARACTER
    
    # ========================================
    # Store character name
    # ========================================
    upload_data = get_upload_data(user.id)
    upload_data["character"] = character_name
    
    app_logger.info(f"📤 Upload: User {user.id} entered character '{character_name}'")
    
    # ========================================
    # Ask for photo
    # ========================================
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Go Back", callback_data="upload_back_character")],
        [InlineKeyboardButton("❌ Cancel Upload", callback_data="upload_cancel")]
    ])
    
    anime = upload_data.get("anime", "Unknown")
    
    await update.message.reply_text(
        f"✅ *Anime:* `{anime}`\n"
        f"✅ *Character:* `{character_name}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🖼️ *Step 3/3*: Send the character image\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Accepted formats:\n"
        "• 📷 Photo (compressed)\n"
        "• 📎 Document (image file)\n\n"
        "⚠️ *Requirements:*\n"
        "• Clear character image\n"
        "• Good quality\n"
        "• Appropriate content\n\n"
        "💡 Send the image now:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    
    return UPLOAD_PHOTO


async def upload_photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle photo/document input.
    
    Validates the image, generates rarity, saves to DB, and shows preview.
    """
    user = update.effective_user
    message = update.message
    
    # ========================================
    # Extract photo file ID
    # ========================================
    photo_file_id: Optional[str] = None
    
    # Check if it's a photo
    if message.photo:
        # Get the largest photo size
        photo: PhotoSize = message.photo[-1]
        photo_file_id = photo.file_id
        app_logger.info(f"📤 Upload: Received photo from user {user.id}")
    
    # Check if it's a document (image file)
    elif message.document:
        doc: Document = message.document
        
        # Validate MIME type
        if doc.mime_type and doc.mime_type.startswith("image/"):
            photo_file_id = doc.file_id
            app_logger.info(f"📤 Upload: Received document image from user {user.id}")
        else:
            await message.reply_text(
                "❌ *Invalid File Type*\n\n"
                "Please send an image file (JPG, PNG, etc.)\n"
                "or send a photo directly.\n\n"
                "💡 Try again:",
                parse_mode="Markdown"
            )
            return UPLOAD_PHOTO
    
    # No valid image found
    if not photo_file_id:
        await message.reply_text(
            "❌ *No Image Detected*\n\n"
            "Please send:\n"
            "• A photo (📷)\n"
            "• An image file (📎)\n\n"
            "💡 Try again:",
            parse_mode="Markdown"
        )
        return UPLOAD_PHOTO
    
    # ========================================
    # Get upload data
    # ========================================
    upload_data = get_upload_data(user.id)
    anime = upload_data.get("anime", "Unknown")
    character = upload_data.get("character", "Unknown")
    
    # ========================================
    # Generate random rarity
    # ========================================
    rarity_id = get_random_rarity()
    rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity_id)
    
    app_logger.info(
        f"📤 Upload: Generated rarity {rarity_id} ({rarity_name}) for {character}"
    )
    
    # ========================================
    # Save card to database
    # ========================================
    try:
        card = await add_card(
            pool=None,
            anime=anime,
            character=character,
            rarity=rarity_id,
            photo_file_id=photo_file_id,
            uploader_id=user.id,
            description=f"Uploaded by {user.first_name}",
            tags=[anime.lower(), character.lower().split()[0]]
        )
        
        if card is None:
            # Card already exists (duplicate)
            await message.reply_text(
                "⚠️ *Card Already Exists*\n\n"
                f"A card for *{character}* from *{anime}* "
                "is already in the database.\n\n"
                "Use /upload to add a different card.",
                parse_mode="Markdown"
            )
            clear_upload_data(user.id)
            return ConversationHandler.END
        
        card_id = card["card_id"]
        
        app_logger.info(
            f"✅ Upload: Card #{card_id} saved - {character} ({anime}) "
            f"by user {user.id}"
        )
        
    except Exception as e:
        error_logger.error(f"Failed to save card: {e}", exc_info=True)
        await message.reply_text(
            "❌ *Database Error*\n\n"
            "Failed to save the card. Please try again later.\n"
            f"Error: `{str(e)[:100]}`",
            parse_mode="Markdown"
        )
        clear_upload_data(user.id)
        return ConversationHandler.END
    
    # ========================================
    # Set cooldown
    # ========================================
    set_upload_cooldown(user.id)
    
    # ========================================
    # Get total card count
    # ========================================
    total_cards = await get_card_count(None)
    
    # ========================================
    # Send preview with the image
    # ========================================
    preview_text = (
        "🎉 *Card Uploaded Successfully!*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 *ID:* `#{card_id}`\n"
        f"🎬 *Anime:* {anime}\n"
        f"👤 *Character:* {character}\n"
        f"✨ *Rarity:* {rarity_emoji} {rarity_name}\n"
        f"📊 *Probability:* {rarity_prob}%\n"
        f"👤 *Uploader:* {user.first_name}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 Total cards in database: *{total_cards}*\n\n"
        "Use /upload to add more cards!"
    )
    
    # Create keyboard for additional actions
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📤 Upload Another", callback_data="upload_new"),
            InlineKeyboardButton("📊 View Stats", callback_data="admin_stats")
        ]
    ])
    
    # Send the preview with the card image
    await message.reply_photo(
        photo=photo_file_id,
        caption=preview_text,
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    
    # ========================================
    # Clear upload data
    # ========================================
    clear_upload_data(user.id)
    
    return ConversationHandler.END


async def upload_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle upload cancellation via /cancel command.
    """
    user = update.effective_user
    
    # Clear upload data
    clear_upload_data(user.id)
    
    await update.message.reply_text(
        "❌ *Upload Cancelled*\n\n"
        "Your upload has been cancelled.\n"
        "Use /upload to start again.",
        parse_mode="Markdown"
    )
    
    app_logger.info(f"📤 Upload cancelled by user {user.id}")
    
    return ConversationHandler.END


async def upload_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle callback queries during upload conversation.
    """
    query = update.callback_query
    user = query.from_user
    data = query.data
    
    await query.answer()
    
    # ========================================
    # Cancel upload
    # ========================================
    if data == "upload_cancel":
        clear_upload_data(user.id)
        
        await query.edit_message_text(
            "❌ *Upload Cancelled*\n\n"
            "Your upload has been cancelled.\n"
            "Use /upload to start again.",
            parse_mode="Markdown"
        )
        
        app_logger.info(f"📤 Upload cancelled via button by user {user.id}")
        return ConversationHandler.END
    
    # ========================================
    # Go back to anime input
    # ========================================
    elif data == "upload_back_anime":
        # Clear stored anime
        upload_data = get_upload_data(user.id)
        upload_data.pop("anime", None)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel Upload", callback_data="upload_cancel")]
        ])
        
        await query.edit_message_text(
            "📤 *Card Upload Wizard*\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📝 *Step 1/3*: Enter the anime/series name\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "💡 Type the anime name:",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        
        return UPLOAD_ANIME
    
    # ========================================
    # Go back to character input
    # ========================================
    elif data == "upload_back_character":
        # Clear stored character
        upload_data = get_upload_data(user.id)
        upload_data.pop("character", None)
        anime = upload_data.get("anime", "Unknown")
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Go Back", callback_data="upload_back_anime")],
            [InlineKeyboardButton("❌ Cancel Upload", callback_data="upload_cancel")]
        ])
        
        await query.edit_message_text(
            f"✅ *Anime:* `{anime}`\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📝 *Step 2/3*: Enter the character name\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "💡 Type the character name:",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        
        return UPLOAD_CHARACTER
    
    # ========================================
    # Start new upload
    # ========================================
    elif data == "upload_new":
        # Check cooldown
        is_cooldown, remaining = check_upload_cooldown(user.id)
        if is_cooldown:
            await query.answer(
                f"⏳ Please wait {remaining} seconds before uploading again.",
                show_alert=True
            )
            return ConversationHandler.END
        
        clear_upload_data(user.id)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel Upload", callback_data="upload_cancel")]
        ])
        
        await query.edit_message_caption(
            caption=(
                "📤 *Card Upload Wizard*\n\n"
                "Let's add another card!\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "📝 *Step 1/3*: Enter the anime/series name\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "💡 Type the anime name or /cancel to abort."
            ),
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        
        return UPLOAD_ANIME
    
    return ConversationHandler.END


async def upload_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle conversation timeout.
    """
    user_id = update.effective_user.id if update.effective_user else None
    
    if user_id:
        clear_upload_data(user_id)
        app_logger.info(f"📤 Upload timed out for user {user_id}")
    
    return ConversationHandler.END


async def upload_invalid_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle invalid input during conversation.
    """
    await update.message.reply_text(
        "⚠️ *Invalid Input*\n\n"
        "Please follow the instructions above.\n"
        "Use /cancel to abort the upload.",
        parse_mode="Markdown"
    )
    
    # Stay in the current state
    return None


# ============================================================
# 🔧 Conversation Handler Setup
# ============================================================

# Create the upload conversation handler
upload_conversation_handler = ConversationHandler(
    entry_points=[
        CommandHandler("upload", upload_start),
    ],
    states={
        UPLOAD_ANIME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, upload_anime_received),
            CallbackQueryHandler(upload_callback_handler, pattern=r"^upload_"),
        ],
        UPLOAD_CHARACTER: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, upload_character_received),
            CallbackQueryHandler(upload_callback_handler, pattern=r"^upload_"),
        ],
        UPLOAD_PHOTO: [
            MessageHandler(filters.PHOTO | filters.Document.IMAGE, upload_photo_received),
            CallbackQueryHandler(upload_callback_handler, pattern=r"^upload_"),
            MessageHandler(
                filters.ALL & ~filters.COMMAND & ~filters.PHOTO & ~filters.Document.IMAGE,
                upload_invalid_input
            ),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", upload_cancel),
        CallbackQueryHandler(upload_callback_handler, pattern=r"^upload_"),
    ],
    conversation_timeout=300,  # 5 minute timeout
    name="upload_conversation",
    persistent=False,
    per_message=True,
)


# ============================================================
# 📤 Quick Upload Function (for admins)
# ============================================================

async def quick_upload(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Quick upload by replying to a photo with:
    /quickupload Anime | Character | Rarity(optional)
    
    Example: /quickupload Naruto | Naruto Uzumaki | 5
    """
    user = update.effective_user
    message = update.message
    
    # Check admin
    if not Config.is_admin(user.id):
        await message.reply_text("❌ Admin only command.")
        return
    
    # Check if replying to a photo
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.reply_text(
            "📤 *Quick Upload*\n\n"
            "Reply to a photo with:\n"
            "`/quickupload Anime | Character | Rarity`\n\n"
            "Example:\n"
            "`/quickupload Naruto | Naruto Uzumaki | 5`\n\n"
            "Rarity is optional (1-11). Random if not specified.",
            parse_mode="Markdown"
        )
        return
    
    # Parse arguments
    args_text = message.text.replace("/quickupload", "").strip()
    
    if not args_text:
        await message.reply_text(
            "❌ Please provide: `Anime | Character | Rarity(optional)`",
            parse_mode="Markdown"
        )
        return
    
    parts = [p.strip() for p in args_text.split("|")]
    
    if len(parts) < 2:
        await message.reply_text(
            "❌ Format: `Anime | Character | Rarity(optional)`",
            parse_mode="Markdown"
        )
        return
    
    anime = parts[0]
    character = parts[1]
    rarity_id = None
    
    if len(parts) >= 3 and parts[2].isdigit():
        rarity_id = int(parts[2])
        if not 1 <= rarity_id <= 11:
            rarity_id = None
    
    if rarity_id is None:
        rarity_id = get_random_rarity()
    
    # Get photo file ID
    photo_file_id = message.reply_to_message.photo[-1].file_id
    
    # Save to database
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
            await message.reply_text("⚠️ Card already exists!")
            
    except Exception as e:
        error_logger.error(f"Quick upload failed: {e}", exc_info=True)
        await message.reply_text(f"❌ Error: {e}")


# Quick upload command handler
quick_upload_handler = CommandHandler("quickupload", quick_upload)