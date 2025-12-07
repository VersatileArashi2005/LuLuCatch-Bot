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
import psycopg2.extras

from db import (
    add_card,
    ensure_user,
    give_card_to_user,
    get_all_groups,
    get_user_by_id,
    get_conn
)
from commands.utils import rarity_to_text

# Upload & Edit sessions
pending_uploads = {}
pending_edits = {}

# ---------------------------------------------------
# DB Query Helpers
# ---------------------------------------------------

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

def get_card_by_id(card_id):
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM cards WHERE id=%s", (card_id,))
        return cur.fetchone()

def update_card_name(card_id, new_name):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE cards SET character=%s WHERE id=%s", (new_name, card_id))
        conn.commit()

def update_card_anime(card_id, new_anime):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE cards SET anime=%s WHERE id=%s", (new_anime, card_id))
        conn.commit()

def update_card_rarity(card_id, new_rarity):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE cards SET rarity=%s WHERE id=%s", (new_rarity, card_id))
        conn.commit()

def update_card_photo(card_id, new_file_id):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE cards SET file_id=%s WHERE id=%s", (new_file_id, card_id))
        conn.commit()

def delete_card(card_id):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM cards WHERE id=%s", (card_id,))
        conn.commit()

ALLOWED_ROLES = {"owner", "dev", "admin", "uploader"}

# ---------------------------------------------------
# /upload  — DM ONLY
# (Original upload_cmd, callback_router, text_handler, photo_handler)
# ... copy all previous upload code here ...
# ---------------------------------------------------

# ---------------------------------------------------
# /edit command
# ---------------------------------------------------

async def edit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if not chat or chat.type != "private":
        await update.message.reply_text("❌ /edit can only be used in private chat.")
        return

    ensure_user(user.id, user.first_name or user.username or "User")
    u = get_user_by_id(user.id)
    role = (u.get("role") or "user").lower()
    if role not in ALLOWED_ROLES:
        await update.message.reply_text("❌ You do not have permission to edit cards.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("⚠️ Please provide card ID, e.g., /edit 7")
        return

    try:
        card_id = int(args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Invalid card ID.")
        return

    card = get_card_by_id(card_id)
    if not card:
        await update.message.reply_text(f"❌ Card ID {card_id} not found.")
        return

    pending_edits[user.id] = {"card_id": card_id}

    keyboard = [
        [InlineKeyboardButton("Edit Name", callback_data="edit_name")],
        [InlineKeyboardButton("Edit Anime Name", callback_data="edit_anime")],
        [InlineKeyboardButton("Edit Rarity", callback_data="edit_rarity")],
        [InlineKeyboardButton("Edit Photo", callback_data="edit_photo")],
    ]
    await update.message.reply_text(
        f"📝 Editing Card ID {card_id}\n"
        f"🎬 {card['anime']} | 🎴 {card['character']} | 🏷 {rarity_to_text(card['rarity'])[0]}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ---------------------------------------------------
# /delete command
# ---------------------------------------------------

async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if not chat or chat.type != "private":
        await update.message.reply_text("❌ /delete can only be used in private chat.")
        return

    ensure_user(user.id, user.first_name or user.username or "User")
    u = get_user_by_id(user.id)
    role = (u.get("role") or "user").lower()
    if role not in ALLOWED_ROLES:
        await update.message.reply_text("❌ You do not have permission to delete cards.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("⚠️ Please provide card ID, e.g., /delete 7")
        return

    try:
        card_id = int(args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Invalid card ID.")
        return

    card = get_card_by_id(card_id)
    if not card:
        await update.message.reply_text(f"❌ Card ID {card_id} not found.")
        return

    delete_card(card_id)
    await update.message.reply_text(f"✅ Card ID {card_id} deleted successfully.")

# ---------------------------------------------------
# Edit Inline Callback Router
# ---------------------------------------------------

async def edit_callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data or ""
    st = pending_edits.get(user.id)
    if not st:
        return

    card_id = st["card_id"]
    card = get_card_by_id(card_id)
    if not card:
        await query.edit_message_text(f"❌ Card ID {card_id} not found.")
        pending_edits.pop(user.id, None)
        return

    if data == "edit_name":
        st["stage"] = "edit_name"
        pending_edits[user.id] = st
        await query.edit_message_text(f"✏️ Send new name for Card ID {card_id}.")
    elif data == "edit_anime":
        st["stage"] = "edit_anime"
        pending_edits[user.id] = st
        await query.edit_message_text(f"✏️ Send new anime name for Card ID {card_id}.")
    elif data == "edit_rarity":
        st["stage"] = "edit_rarity"
        pending_edits[user.id] = st
        keyboard = [
            [InlineKeyboardButton(
                f"{rarity_to_text(rid)[2]} {rarity_to_text(rid)[0].capitalize()} ({rarity_to_text(rid)[1]}%)",
                callback_data=f"edit_rarity_select::{rid}"
            )] for rid in range(1, 11)
        ]
        await query.edit_message_text(
            f"🎭 Select new rarity for Card ID {card_id}:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif data.startswith("edit_rarity_select::"):
        rid = int(data.split("::")[1])
        update_card_rarity(card_id, rid)
        await query.edit_message_text(f"✅ Card ID {card_id} rarity updated.")
        pending_edits.pop(user.id, None)
    elif data == "edit_photo":
        st["stage"] = "edit_photo"
        pending_edits[user.id] = st
        await query.edit_message_text(f"📷 Send new photo for Card ID {card_id}.")

# ---------------------------------------------------
# Text handler for Edit
# ---------------------------------------------------

async def edit_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if chat.type != "private":
        return

    st = pending_edits.get(user.id)
    if not st or "stage" not in st:
        return

    text = update.message.text.strip()
    card_id = st["card_id"]

    if st["stage"] == "edit_name":
        update_card_name(card_id, text)
        await update.message.reply_text(f"✅ Card ID {card_id} name updated to {text}.")
        pending_edits.pop(user.id, None)
    elif st["stage"] == "edit_anime":
        update_card_anime(card_id, text)
        await update.message.reply_text(f"✅ Card ID {card_id} anime updated to {text}.")
        pending_edits.pop(user.id, None)

# ---------------------------------------------------
# Photo handler for Edit
# ---------------------------------------------------

async def edit_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if chat.type != "private":
        return

    st = pending_edits.get(user.id)
    if not st or st.get("stage") != "edit_photo":
        return

    if not update.message.photo:
        await update.message.reply_text("❌ Please send a photo.")
        return

    file_id = update.message.photo[-1].file_id
    card_id = st["card_id"]
    update_card_photo(card_id, file_id)
    await update.message.reply_text(f"✅ Card ID {card_id} photo updated.")
    pending_edits.pop(user.id, None)

# ---------------------------------------------------
# Register Handlers
# ---------------------------------------------------

def register_handlers(application):
    # Upload
    application.add_handler(CommandHandler("upload", upload_cmd))
    application.add_handler(CallbackQueryHandler(callback_router, pattern=r"^upload_"))
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, text_handler))
    application.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE & ~filters.COMMAND, photo_handler))

    # Edit & Delete
    application.add_handler(CommandHandler("edit", edit_cmd))
    application.add_handler(CommandHandler("delete", delete_cmd))
    application.add_handler(CallbackQueryHandler(edit_callback_router, pattern=r"^edit_"))
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, edit_text_handler))
    application.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE & ~filters.COMMAND, edit_photo_handler))