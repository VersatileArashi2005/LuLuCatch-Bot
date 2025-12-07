# commands/upload.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    CommandHandler,
    filters
)
from db import add_card, ensure_user, give_card_to_user, register_group, get_all_groups
from commands.utils import rarity_to_text
import re

# In-memory pending uploads
pending_uploads = {}


async def upload_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id, user.first_name or user.username or "User")

    text = update.message.text or ""
    parts = text.split(" ", 1)

    if len(parts) < 2:
        await update.message.reply_text(
            "Usage: /upload <Name>|<Anime>\nExample: /upload Nami|One Piece\n"
            "After this, send the image."
        )
        return

    payload = parts[1].strip()

    if "|" not in payload:
        await update.message.reply_text(
            "Please separate Name and Anime with '|'\nExample: /upload Nami|One Piece"
        )
        return

    name, anime = [p.strip() for p in payload.split("|", 1)]

    pending_uploads[user.id] = {
        "name": name,
        "anime": anime,
        "rarity": None
    }

    await update.message.reply_text(
        "Got it! Now send the card **image**.\n"
        "After image, I'll ask you to choose rarity."
    )


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if user.id not in pending_uploads:
        return  # Not an upload flow

    if not update.message.photo:
        await update.message.reply_text("Please send a photo.")
        return

    file_id = update.message.photo[-1].file_id
    pending_uploads[user.id]["file_id"] = file_id

    # Build rarity buttons
    keyboard = []
    for rid in range(1, 10 + 1):
        r_name, pct, emoji = rarity_to_text(rid)
        btn = InlineKeyboardButton(
            f"{emoji} {r_name.capitalize()} ({pct}%)",
            callback_data=f"upload_rarity_{rid}"
        )
        keyboard.append([btn])

    await update.message.reply_text(
        "Choose a rarity for this card:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


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
        await query.edit_message_text(
            "Upload session expired. Please run /upload again."
        )
        return

    info = pending_uploads.pop(user.id)
    info["rarity"] = rid

    # Save to DB
    card_id = add_card(
        info["name"],
        info["anime"],
        info["rarity"],
        info["file_id"],
        user.id
    )

    # Give uploader the card automatically
    give_card_to_user(user.id, card_id)

    r_name, pct, emoji = rarity_to_text(rid)

    await query.edit_message_text(
        f"✅ Card uploaded!\n"
        f"🎴 ID: {card_id}\n"
        f"{emoji} {info['name']}\n"
        f"🎬 {info['anime']}\n"
        f"🏷 {r_name.capitalize()} ({pct}%)"
    )

    # Broadcast to all registered groups
    caption = (
        f"🎴 New card uploaded!\n"
        f"{emoji} {info['name']}\n"
        f"📌 ID: {card_id}\n"
        f"🎬 Anime: {info['anime']}\n"
        f"🏷 Rarity: {r_name.capitalize()} ({pct}%)\n"
        f"Try to claim it!"
    )

    groups = get_all_groups()

    for chat_id in groups:
        try:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=info["file_id"],
                caption=caption
            )
        except:
            pass


def register_handlers(application):
    application.add_handler(CommandHandler("upload", upload_cmd))
    application.add_handler(
        MessageHandler(filters.PHOTO & ~filters.COMMAND, photo_handler)
    )
    application.add_handler(
        CallbackQueryHandler(upload_rarity_cb, pattern=r"^upload_rarity_\d+$")
    )
