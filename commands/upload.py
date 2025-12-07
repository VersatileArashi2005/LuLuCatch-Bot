# commands/upload.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters
from db import add_card, ensure_user, give_card_to_user, register_group, get_all_groups
from commands.utils import rarity_to_text
import re

# in-memory pending uploads: user_id -> {"name":..., "anime":..., "rarity":int}
pending_uploads = {}

async def upload_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id, user.first_name or user.username or "User")

    text = update.message.text or ""
    # Expect format: /upload Name|Anime
    parts = text.split(" ", 1)
    if len(parts) < 2:
        await update.message.reply_text("Usage: /upload <Name>|<Anime>\nExample: /upload Nami|One Piece\nAfter this I will ask you to send the image.")
        return

    payload = parts[1].strip()
    if "|" not in payload:
        await update.message.reply_text("Please separate Name and Anime with a pipe '|' character. Example: /upload Nami|One Piece")
        return

    name, anime = [p.strip() for p in payload.split("|", 1)]
    # Set default rarity prompt (user will be asked to choose rarity after image)
    pending_uploads[user.id] = {"name": name, "anime": anime, "rarity": None}
    await update.message.reply_text("Got it. Please send the card image now (in this chat or in bot DM). After image, I'll ask you to choose rarity.")

# photo handler to finalize upload
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in pending_uploads:
        # Not an upload flow: ignore or inform
        return

    if not update.message.photo:
        await update.message.reply_text("Please send a photo (image).")
        return

    file_id = update.message.photo[-1].file_id  # highest res
    data = pending_uploads[user.id]
    # temporarily store file_id, ask for rarity
    data['file_id'] = file_id

    # Show rarity buttons
    keyboard = []
    for rid in range(1, 11):
        name, pct, emoji = rarity_to_text(rid)
        keyboard.append([InlineKeyboardButton(f"{emoji} {name.capitalize()} ({pct}%)", callback_data=f"upload_rarity_{rid}")])
    await update.message.reply_text("Choose rarity for this card:", reply_markup=InlineKeyboardMarkup(keyboard))

# callback for rarity selection
async def upload_rarity_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    m = re.match(r"upload_rarity_(\d+)", query.data)
    if not m:
        await query.edit_message_text("Invalid selection.")
        return
    rid = int(m.group(1))
    if user.id not in pending_uploads:
        await query.edit_message_text("Upload session expired or not found. Start /upload again.")
        return
    info = pending_uploads.pop(user.id)
    info['rarity'] = rid
    # persist to DB
    card_id = add_card(info['name'], info['anime'], info['rarity'], info['file_id'], user.id)
    # auto-give uploader the card
    give_card_to_user(user.id, card_id)

    # Notify uploader
    name, pct, emoji = rarity_to_text(rid)
    await query.edit_message_text(f"✅ Uploaded card id {card_id}\n{name.capitalize()} {emoji} ({pct}%)\nAnime: {info['anime']}\nName: {info['name']}")

    # Notify all registered groups
    groups = get_all_groups()
    caption = f"🎴 New card uploaded!\n{emoji} {info['name']}\n📌 ID: {card_id}\n🎬 Anime: {info['anime']}\n🏷 Rarity: {name.capitalize()} ({pct}%)\nTry to claim it in chat!"
    for chat_id in groups:
        try:
            await context.bot.send_photo(chat_id=chat_id, photo=info['file_id'], caption=caption)
        except Exception:
            # ignore per-chat send errors
            pass

# Export function to register handlers from main
def register_handlers(application):
    application.add_handler(CommandHandler("upload", upload_cmd))
    # photos in any chat (private or group) - we only act if user has pending upload
    application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, photo_handler))
    application.add_handler(CallbackQueryHandler(upload_rarity_cb, pattern=r"^upload_rarity_\d+$"))
