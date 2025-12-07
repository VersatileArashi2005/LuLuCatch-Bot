# commands/upload.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    CommandHandler,
    filters,
)
from urllib.parse import quote_plus, unquote_plus
import re

from db import (
    add_card,
    ensure_user,
    give_card_to_user,
    get_all_groups,
    get_user_by_id,
    get_conn
)
from commands.utils import rarity_to_text

# Upload sessions kept here
pending_uploads = {}

# ---------------------------------------------------
# DB Query Helpers
# ---------------------------------------------------

import psycopg2.extras

def db_list_animes():
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT anime FROM cards WHERE anime IS NOT NULL GROUP BY anime ORDER BY LOWER(anime)")
        return [r['anime'] for r in cur.fetchall()]

def db_list_characters(anime):
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT character FROM cards WHERE anime=%s GROUP BY character ORDER BY LOWER(character)", (anime,))
        return [r['character'] for r in cur.fetchall()]

ALLOWED_ROLES = {"owner", "dev", "admin", "uploader"}

# ---------------------------------------------------
# /upload  — DM ONLY
# ---------------------------------------------------

async def upload_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    # ❌ BLOCK IF NOT IN PRIVATE
    if not chat or chat.type != "private":
        await update.message.reply_text(
            "❌ /upload can only be used in **private chat**.\n"
            "➡ Please DM the bot to upload cards."
        )
        return

    ensure_user(user.id, user.first_name or user.username or "User")
    u = get_user_by_id(user.id)
    role = (u.get("role") or "user").lower()

    if role not in ALLOWED_ROLES:
        await update.message.reply_text(
            "❌ You do not have permission to upload.\n"
            "Required role: owner / dev / admin / uploader."
        )
        return

    animes = db_list_animes()
    keyboard = [[InlineKeyboardButton(a, callback_data=f"upload_choose_anime::{quote_plus(a)}")] for a in animes]
    keyboard.append([InlineKeyboardButton("➕ Add new anime", callback_data="upload_add_anime")])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])

    pending_uploads[user.id] = {"stage": "anime_select"}

    await update.message.reply_text(
        "🎬 **Select Anime**\nOr choose *Add new anime* if it's missing.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ---------------------------------------------------
# Inline Button Callback Router
# ---------------------------------------------------

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data or ""
    st = pending_uploads.get(user.id)

    # Cancel
    if data == "upload_cancel":
        pending_uploads.pop(user.id, None)
        await query.edit_message_text("❌ Upload cancelled.")
        return

    # Add new anime
    if data == "upload_add_anime":
        pending_uploads[user.id] = {"stage": "adding_anime"}
        await query.edit_message_text("✏️ Send the new anime name.")
        return

    # Choose anime
    m = re.match(r"^upload_choose_anime::(.+)$", data)
    if m:
        anime = unquote_plus(m.group(1))
        pending_uploads[user.id] = {"stage": "character_select", "anime": anime}

        chars = db_list_characters(anime)
        keyboard = [[InlineKeyboardButton(c, callback_data=f"upload_choose_character::{quote_plus(c)}")] for c in chars]
        keyboard.append([InlineKeyboardButton("➕ Add new character", callback_data="upload_add_character")])
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="upload_back_anime")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])

        await query.edit_message_text(
            f"🎬 Anime: *{anime}*\n\nSelect Character:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return

    # Add character
    if data == "upload_add_character":
        if not st or "anime" not in st:
            await query.edit_message_text("⚠️ Error: please select an anime first.")
            return
        st["stage"] = "adding_character"
        await query.edit_message_text("✏️ Send character name.")
        return

    # Back to anime
    if data == "upload_back_anime":
        animes = db_list_animes()
        keyboard = [[InlineKeyboardButton(a, callback_data=f"upload_choose_anime::{quote_plus(a)}")] for a in animes]
        keyboard.append([InlineKeyboardButton("➕ Add new anime", callback_data="upload_add_anime")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])

        pending_uploads[user.id] = {"stage": "anime_select"}

        await query.edit_message_text(
            "🎬 Select Anime:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Character selection
    m = re.match(r"^upload_choose_character::(.+)$", data)
    if m:
        char = unquote_plus(m.group(1))
        st.update({"stage": "rarity_select", "character": char})
        pending_uploads[user.id] = st

        # Rarity menu
        keyboard = [
            [InlineKeyboardButton(
                f"{rarity_to_text(rid)[2]} {rarity_to_text(rid)[0].capitalize()} ({rarity_to_text(rid)[1]}%)",
                callback_data=f"upload_rarity::{rid}"
            )]
            for rid in range(1, 11)
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="upload_back_char")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])

        await query.edit_message_text(
            f"🎭 Character: *{char}*\n\nSelect rarity:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return

    # Back to characters
    if data == "upload_back_char":
        anime = st.get("anime")
        chars = db_list_characters(anime)

        keyboard = [[InlineKeyboardButton(c, callback_data=f"upload_choose_character::{quote_plus(c)}")] for c in chars]
        keyboard.append([InlineKeyboardButton("➕ Add new character", callback_data="upload_add_character")])
        keyboard.append([InlineKeyboardButton("⬅️ Back to anime", callback_data="upload_back_anime")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])

        st["stage"] = "character_select"

        await query.edit_message_text(
            "Select Character:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Rarity chosen
    m = re.match(r"^upload_rarity::(\d+)$", data)
    if m:
        rid = int(m.group(1))
        st["rarity"] = rid
        st["stage"] = "awaiting_photo"
        pending_uploads[user.id] = st

        await query.edit_message_text(
            "📷 Please send the **card image** now.",
            parse_mode="Markdown"
        )
        return

# ---------------------------------------------------
# Text Handler (DM-only)
# ---------------------------------------------------

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if chat.type != "private":
        return

    st = pending_uploads.get(user.id)
    if not st:
        return

    text = update.message.text.strip()

    # Add anime name
    if st["stage"] == "adding_anime":
        anime = text
        pending_uploads[user.id] = {"stage": "character_select", "anime": anime}

        chars = db_list_characters(anime)
        keyboard = [[InlineKeyboardButton(c, callback_data=f"upload_choose_character::{quote_plus(c)}")] for c in chars]
        keyboard.append([InlineKeyboardButton("➕ Add new character", callback_data="upload_add_character")])
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="upload_back_anime")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])

        await update.message.reply_text(
            f"🎬 Anime set to *{anime}*.\nSelect character:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return

    # Add character name
    if st["stage"] == "adding_character":
        st["character"] = text
        st["stage"] = "rarity_select"

        keyboard = [
            [InlineKeyboardButton(
                f"{rarity_to_text(rid)[2]} {rarity_to_text(rid)[0].capitalize()} ({rarity_to_text(rid)[1]}%)",
                callback_data=f"upload_rarity::{rid}"
            )]
            for rid in range(1, 11)
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="upload_back_char")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])

        await update.message.reply_text(
            f"Character set to *{text}*. Select rarity:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return

    # Wrong stage
    await update.message.reply_text("⚠️ Please use the buttons — text is not required for this step.")

# ---------------------------------------------------
# Photo Handler (DM-only)
# ---------------------------------------------------

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if chat.type != "private":
        return

    st = pending_uploads.get(user.id)
    if not st or st["stage"] != "awaiting_photo":
        return

    if not update.message.photo:
        await update.message.reply_text("❌ Please send a **photo**.")
        return

    file_id = update.message.photo[-1].file_id

    anime = st["anime"]
    character = st["character"]
    rarity = st["rarity"]

    # Save card
    try:
        card_id = add_card(anime, character, rarity, file_id, user.id)
        give_card_to_user(user.id, card_id)
    except Exception as e:
        await update.message.reply_text(f"❌ Database Error: {e}")
        pending_uploads.pop(user.id, None)
        return

    name, pct, emoji = rarity_to_text(rarity)

    await update.message.reply_text(
        f"✅ **Card Uploaded Successfully!**\n"
        f"🎴 ID: {card_id}\n"
        f"{emoji} {character}\n"
        f"🎬 {anime}\n"
        f"🏷 {name.capitalize()} ({pct}%)",
        parse_mode="Markdown"
    )

    # Broadcast to groups
    caption = (
        f"🎴 **New Card!**\n"
        f"{emoji} {character}\n"
        f"📌 ID: {card_id}\n"
        f"🎬 Anime: {anime}\n"
        f"🏷 Rarity: {name.capitalize()} ({pct}%)\n"
        f"➡ Try to claim it!"
    )

    for gid in get_all_groups():
        try:
            await context.bot.send_photo(chat_id=gid, photo=file_id, caption=caption)
        except:
            pass

    # Clear session
    pending_uploads.pop(user.id, None)

# ---------------------------------------------------
# Register Handlers
# ---------------------------------------------------

def register_handlers(application):
    application.add_handler(CommandHandler("upload", upload_cmd))
    application.add_handler(CallbackQueryHandler(callback_router, pattern=r"^upload_"))
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, text_handler))
    application.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE & ~filters.COMMAND, photo_handler))