# ============================================================
# 📁 File: handlers/upload.py
# 📍 Location: telegram_card_bot/handlers/upload.py
# 📝 Description: Card upload system with rarity selection
# ============================================================

from datetime import datetime
from typing import Optional, Dict, Any

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

UPLOAD_ANIME = 0
UPLOAD_CHARACTER = 1
UPLOAD_PHOTO = 2


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
# 📝 Pending Uploads Storage (for rarity selection)
# ============================================================

# Store pending uploads waiting for rarity selection
# Format: {user_id: {"anime": str, "character": str, "photo_file_id": str, "message_id": int}}
_pending_uploads: Dict[int, Dict[str, Any]] = {}


def save_pending_upload(user_id: int, anime: str, character: str, photo_file_id: str, message_id: int) -> None:
    """Save a pending upload waiting for rarity selection."""
    _pending_uploads[user_id] = {
        "anime": anime,
        "character": character,
        "photo_file_id": photo_file_id,
        "message_id": message_id,
        "created_at": datetime.now()
    }


def get_pending_upload(user_id: int) -> Optional[Dict[str, Any]]:
    """Get pending upload for a user."""
    return _pending_uploads.get(user_id)


def clear_pending_upload(user_id: int) -> None:
    """Clear pending upload for a user."""
    _pending_uploads.pop(user_id, None)


# ============================================================
# 🎴 Upload Command Handlers
# ============================================================

async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /upload command - Start the upload conversation."""
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
    
    # Clear any pending uploads
    clear_pending_upload(user.id)
    
    # Clear context data
    context.user_data.clear()
    
    # Send welcome message
    await update.message.reply_text(
        "📤 *Card Upload Wizard*\n\n"
        "Let's add a new card to the collection!\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📝 *Step 1/4*: Enter the anime/series name\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Examples:\n"
        "• `Naruto`\n"
        "• `One Piece`\n"
        "• `Attack on Titan`\n\n"
        "💡 Type the anime name or /cancel to abort.",
        parse_mode="Markdown"
    )
    
    app_logger.info(f"📤 Upload started by user {user.id} ({user.first_name})")
    
    return UPLOAD_ANIME


async def upload_anime_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle anime name input."""
    user = update.effective_user
    anime_name = update.message.text.strip()
    
    # Validate anime name
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
    
    # Store anime name in context
    context.user_data["anime"] = anime_name
    
    app_logger.info(f"📤 Upload: User {user.id} entered anime '{anime_name}'")
    
    # Ask for character name
    await update.message.reply_text(
        f"✅ *Anime:* `{anime_name}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📝 *Step 2/4*: Enter the character name\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Examples:\n"
        "• `Naruto Uzumaki`\n"
        "• `Monkey D. Luffy`\n"
        "• `Eren Yeager`\n\n"
        "💡 Type the character name or /cancel to abort:",
        parse_mode="Markdown"
    )
    
    return UPLOAD_CHARACTER


async def upload_character_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle character name input."""
    user = update.effective_user
    character_name = update.message.text.strip()
    
    # Validate character name
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
    
    # Store character name in context
    context.user_data["character"] = character_name
    
    app_logger.info(f"📤 Upload: User {user.id} entered character '{character_name}'")
    
    anime = context.user_data.get("anime", "Unknown")
    
    # Ask for photo
    await update.message.reply_text(
        f"✅ *Anime:* `{anime}`\n"
        f"✅ *Character:* `{character_name}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🖼️ *Step 3/4*: Send the character image\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Accepted formats:\n"
        "• 📷 Photo (compressed)\n"
        "• 📎 Document (image file)\n\n"
        "💡 Send the image now or /cancel to abort:",
        parse_mode="Markdown"
    )
    
    return UPLOAD_PHOTO


async def upload_photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle photo/document input - then show rarity selection."""
    user = update.effective_user
    message = update.message
    
    # Extract photo file ID
    photo_file_id: Optional[str] = None
    
    if message.photo:
        photo: PhotoSize = message.photo[-1]
        photo_file_id = photo.file_id
        app_logger.info(f"📤 Upload: Received photo from user {user.id}")
    
    elif message.document:
        doc: Document = message.document
        
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
    
    # Get stored data
    anime = context.user_data.get("anime", "Unknown")
    character = context.user_data.get("character", "Unknown")
    
    # Build rarity selection keyboard
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🛞 Normal (50%)", callback_data=f"upload_rarity_{user.id}_1"),
            InlineKeyboardButton("🌀 Common (20%)", callback_data=f"upload_rarity_{user.id}_2"),
        ],
        [
            InlineKeyboardButton("🥏 Uncommon (10%)", callback_data=f"upload_rarity_{user.id}_3"),
            InlineKeyboardButton("☘️ Rare (7%)", callback_data=f"upload_rarity_{user.id}_4"),
        ],
        [
            InlineKeyboardButton("🫧 Epic (4%)", callback_data=f"upload_rarity_{user.id}_5"),
            InlineKeyboardButton("🎐 Limited (2%)", callback_data=f"upload_rarity_{user.id}_6"),
        ],
        [
            InlineKeyboardButton("❄️ Platinum (1%)", callback_data=f"upload_rarity_{user.id}_7"),
            InlineKeyboardButton("💎 Emerald (0.5%)", callback_data=f"upload_rarity_{user.id}_8"),
        ],
        [
            InlineKeyboardButton("🌸 Crystal (0.3%)", callback_data=f"upload_rarity_{user.id}_9"),
            InlineKeyboardButton("🧿 Mythical (0.15%)", callback_data=f"upload_rarity_{user.id}_10"),
        ],
        [
            InlineKeyboardButton("⚡ Legendary (0.05%)", callback_data=f"upload_rarity_{user.id}_11"),
        ],
        [
            InlineKeyboardButton("🎲 Random Rarity", callback_data=f"upload_rarity_{user.id}_random"),
        ],
        [
            InlineKeyboardButton("❌ Cancel Upload", callback_data=f"upload_rarity_{user.id}_cancel"),
        ],
    ])
    
    # Send image preview with rarity selection
    sent_message = await message.reply_photo(
        photo=photo_file_id,
        caption=(
            f"✅ *Anime:* `{anime}`\n"
            f"✅ *Character:* `{character}`\n"
            f"✅ *Image:* Received\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✨ *Step 4/4*: Select the rarity\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Choose the rarity for this card:"
        ),
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    
    # Save pending upload data
    save_pending_upload(
        user_id=user.id,
        anime=anime,
        character=character,
        photo_file_id=photo_file_id,
        message_id=sent_message.message_id
    )
    
    app_logger.info(f"📤 Upload: Waiting for rarity selection from user {user.id}")
    
    # End conversation - rarity will be handled by separate callback handler
    return ConversationHandler.END


async def upload_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle upload cancellation via /cancel command."""
    user = update.effective_user
    
    # Clear data
    clear_pending_upload(user.id)
    context.user_data.clear()
    
    await update.message.reply_text(
        "❌ *Upload Cancelled*\n\n"
        "Your upload has been cancelled.\n"
        "Use /upload to start again.",
        parse_mode="Markdown"
    )
    
    app_logger.info(f"📤 Upload cancelled by user {user.id}")
    
    return ConversationHandler.END


# ============================================================
# 🎨 Rarity Selection Callback Handler (SEPARATE from ConversationHandler)
# ============================================================

async def upload_rarity_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle rarity selection callback - runs OUTSIDE ConversationHandler."""
    query = update.callback_query
    user = query.from_user
    data = query.data
    
    # Parse callback data: upload_rarity_{user_id}_{rarity}
    try:
        parts = data.split("_")
        # upload_rarity_123456789_5
        if len(parts) != 4 or parts[0] != "upload" or parts[1] != "rarity":
            return
        
        callback_user_id = int(parts[2])
        rarity_value = parts[3]
        
    except (ValueError, IndexError):
        await query.answer("❌ Invalid selection.", show_alert=True)
        return
    
    # Verify user is the uploader
    if user.id != callback_user_id:
        await query.answer("❌ This is not your upload!", show_alert=True)
        return
    
    await query.answer()
    
    # Get pending upload
    pending = get_pending_upload(user.id)
    
    if not pending:
        await query.edit_message_caption(
            caption="❌ *Session Expired*\n\nPlease use /upload to start again.",
            parse_mode="Markdown"
        )
        return
    
    # Handle cancel
    if rarity_value == "cancel":
        clear_pending_upload(user.id)
        
        await query.edit_message_caption(
            caption="❌ *Upload Cancelled*\n\nUse /upload to start again.",
            parse_mode="Markdown"
        )
        
        app_logger.info(f"📤 Upload cancelled by user {user.id} via button")
        return
    
    # Determine rarity
    if rarity_value == "random":
        rarity_id = get_random_rarity()
        app_logger.info(f"📤 Upload: Random rarity selected: {rarity_id}")
    else:
        try:
            rarity_id = int(rarity_value)
            if not 1 <= rarity_id <= 11:
                rarity_id = get_random_rarity()
        except ValueError:
            rarity_id = get_random_rarity()
    
    # Get data from pending upload
    anime = pending["anime"]
    character = pending["character"]
    photo_file_id = pending["photo_file_id"]
    
    rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity_id)
    
    app_logger.info(f"📤 Upload: User {user.id} selected rarity {rarity_id} ({rarity_name})")
    
    # Save card to database
    try:
        card = await add_card(
            pool=None,
            anime=anime,
            character=character,
            rarity=rarity_id,
            photo_file_id=photo_file_id,
            uploader_id=user.id,
            description=f"Uploaded by {user.first_name}",
            tags=[anime.lower(), character.lower().split()[0] if character else ""]
        )
        
        if card is None:
            await query.edit_message_caption(
                caption=(
                    "⚠️ *Card Already Exists*\n\n"
                    f"A card for *{character}* from *{anime}* "
                    "is already in the database.\n\n"
                    "Use /upload to add a different card."
                ),
                parse_mode="Markdown"
            )
            clear_pending_upload(user.id)
            return
        
        card_id = card["card_id"]
        
        app_logger.info(f"✅ Upload: Card #{card_id} saved - {character} ({anime}) by user {user.id}")
        
    except Exception as e:
        error_logger.error(f"Failed to save card: {e}", exc_info=True)
        await query.edit_message_caption(
            caption=(
                "❌ *Database Error*\n\n"
                "Failed to save the card. Please try again later.\n"
                f"Error: `{str(e)[:100]}`"
            ),
            parse_mode="Markdown"
        )
        clear_pending_upload(user.id)
        return
    
    # Set cooldown
    set_upload_cooldown(user.id)
    
    # Get total card count
    total_cards = await get_card_count(None)
    
    # Update message with success
    await query.edit_message_caption(
        caption=(
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
        ),
        parse_mode="Markdown"
    )
    
    # Clear pending upload
    clear_pending_upload(user.id)


# ============================================================
# 📤 Quick Upload Function (for admins)
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
            "`/quickupload One Piece | Luffy | Legendary`\n"
            "`/quickupload Demon Slayer | Tanjiro | random`\n\n"
            "*Rarity options:*\n"
            "1=Normal, 2=Common, 3=Uncommon, 4=Rare\n"
            "5=Epic, 6=Limited, 7=Platinum, 8=Emerald\n"
            "9=Crystal, 10=Mythical, 11=Legendary",
            parse_mode="Markdown"
        )
        return
    
    args_text = message.text.replace("/quickupload", "").strip()
    
    if not args_text:
        await message.reply_text(
            "❌ Please provide: `Anime | Character | Rarity`",
            parse_mode="Markdown"
        )
        return
    
    parts = [p.strip() for p in args_text.split("|")]
    
    if len(parts) < 2:
        await message.reply_text(
            "❌ Format: `Anime | Character | Rarity`",
            parse_mode="Markdown"
        )
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


# ============================================================
# 🔧 Handlers Export
# ============================================================

# ConversationHandler for steps 1-3
upload_conversation_handler = ConversationHandler(
    entry_points=[
        CommandHandler("upload", upload_start),
    ],
    states={
        UPLOAD_ANIME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, upload_anime_received),
        ],
        UPLOAD_CHARACTER: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, upload_character_received),
        ],
        UPLOAD_PHOTO: [
            MessageHandler(filters.PHOTO | filters.Document.IMAGE, upload_photo_received),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", upload_cancel),
    ],
    name="upload_conversation",
    persistent=False,
)

# Separate callback handler for rarity selection (NOT inside ConversationHandler)
upload_rarity_callback_handler = CallbackQueryHandler(
    upload_rarity_callback,
    pattern=r"^upload_rarity_"
)

# Quick upload command handler
quick_upload_handler = CommandHandler("quickupload", quick_upload)