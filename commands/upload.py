# commands/upload.py
import re
import asyncio
from urllib.parse import quote_plus, unquote_plus
from typing import Dict, Any, Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
)
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from commands.utils import rarity_to_text
from db import (
    add_card,
    ensure_user,
    give_card_to_user,
    get_all_groups,
    get_user_by_id,
    get_cards_by_ids,
)

# -------------------------
# Multi-step Upload State
# -------------------------
# pending_uploads[user_id] = {
#   "stage": "anime_select" | "adding_anime" | "character_select" | "adding_character"
#            | "rarity_select" | "awaiting_photo" | "preview" | "confirm_save" | "edit_field",
#   "anime": str,
#   "character": str,
#   "rarity": int,
#   "file_id": str,
#   "preview_message_id": int,   # optional: to edit/cleanup preview
#   "edit_card_id": int,         # for admin editing
# }
pending_uploads: Dict[int, Dict[str, Any]] = {}

ALLOWED_ROLES = {"owner", "dev", "admin", "uploader"}
ADMIN_ROLES = {"owner", "dev", "admin"}

# -------------------------
# Helpers (DB convenience)
# -------------------------
async def db_list_animes(pool):
    rows = await pool.fetch(
        "SELECT anime FROM cards WHERE anime IS NOT NULL GROUP BY anime ORDER BY LOWER(anime)"
    )
    return [r["anime"] for r in rows]

async def db_list_characters(pool, anime: str):
    rows = await pool.fetch(
        "SELECT character FROM cards WHERE anime=$1 GROUP BY character ORDER BY LOWER(character)",
        anime,
    )
    return [r["character"] for r in rows]

# -------------------------
# Keyboard Creators
# -------------------------
def build_anime_keyboard(animes):
    kb = [[InlineKeyboardButton(a, callback_data=f"upload_choose_anime::{quote_plus(a)}")] for a in animes]
    kb.append([InlineKeyboardButton("➕ Add new anime", callback_data="upload_add_anime")])
    kb.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
    return InlineKeyboardMarkup(kb)

def build_character_keyboard(chars):
    kb = [[InlineKeyboardButton(c, callback_data=f"upload_choose_character::{quote_plus(c)}")] for c in chars]
    kb.append([InlineKeyboardButton("➕ Add new character", callback_data="upload_add_character")])
    kb.append([InlineKeyboardButton("⬅️ Back", callback_data="upload_back_anime")])
    kb.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
    return InlineKeyboardMarkup(kb)

def build_rarity_keyboard():
    kb = []
    for rid in range(1, 11):
        name, pct, emoji = rarity_to_text(rid)
        kb.append([InlineKeyboardButton(f"{emoji} {name.capitalize()} ({pct})", callback_data=f"upload_rarity::{rid}")])
    kb.append([InlineKeyboardButton("⬅️ Back", callback_data="upload_back_char")])
    kb.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
    return InlineKeyboardMarkup(kb)

def build_preview_keyboard():
    kb = [
        [InlineKeyboardButton("✅ Confirm & Save", callback_data="upload_confirm_save")],
        [InlineKeyboardButton("✏️ Edit", callback_data="upload_edit")],
        [InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")],
    ]
    return InlineKeyboardMarkup(kb)

# -------------------------
# /upload command (start)
# -------------------------
async def upload_cmd(update: Update, context):
    pool = context.application.bot_data.get("pool")
    if not pool:
        await update.message.reply_text("DB not ready.")
        return

    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.type != "private":
        await update.message.reply_text("❌ Use /upload in private chat (DM).")
        return

    # Ensure user exists in DB and check role
    await ensure_user(pool, user.id, user.first_name or user.username or "User")
    u = await get_user_by_id(pool, user.id)
    role = (u.get("role") or "user").lower()
    if role not in ALLOWED_ROLES:
        await update.message.reply_text("❌ You don't have permission to upload.")
        return

    animes = await db_list_animes(pool)
    kb = build_anime_keyboard(animes)
    pending_uploads[user.id] = {"stage": "anime_select"}
    await update.message.reply_text("🎬 Select Anime:", reply_markup=kb)

# -------------------------
# /edit (admin) - lightweight
# -------------------------
async def edit_cmd(update: Update, context):
    pool = context.application.bot_data.get("pool")
    user = update.effective_user
    u = await get_user_by_id(pool, user.id)
    role = (u.get("role") or "user").lower()
    if role not in ADMIN_ROLES:
        await update.message.reply_text("❌ You do not have permission to edit cards.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /edit <card_id>")
        return

    card_id = int(context.args[0])
    # prepare state to edit card
    pending_uploads[user.id] = {"stage": "edit_field", "edit_card_id": card_id}
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Anime", callback_data=f"edit_field::anime::{card_id}")],
        [InlineKeyboardButton("Character", callback_data=f"edit_field::character::{card_id}")],
        [InlineKeyboardButton("Rarity", callback_data=f"edit_field::rarity::{card_id}")],
        [InlineKeyboardButton("Photo", callback_data=f"edit_field::photo::{card_id}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="edit_cancel")]
    ])
    await update.message.reply_text("✏️ Select field to edit:", reply_markup=kb)

# -------------------------
# delete simple (admin)
# -------------------------
async def delete_cmd(update: Update, context):
    pool = context.application.bot_data.get("pool")
    user = update.effective_user
    u = await get_user_by_id(pool, user.id)
    role = (u.get("role") or "user").lower()
    if role not in ADMIN_ROLES:
        await update.message.reply_text("❌ No permission.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /delete <card_id>")
        return
    card_id = int(context.args[0])
    await pool.execute("DELETE FROM cards WHERE id=$1", card_id)
    await update.message.reply_text(f"✅ Card {card_id} deleted.")

# -------------------------
# Callback router
# -------------------------
async def callback_router(update: Update, context):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    pool = context.application.bot_data.get("pool")
    data = query.data or ""
    st = pending_uploads.get(user.id, {})

    # Cancel flows
    if data in ("upload_cancel", "edit_cancel"):
        pending_uploads.pop(user.id, None)
        try:
            await query.edit_message_text("❌ Operation cancelled.")
        except:
            pass
        return

    # Add anime branch
    if data == "upload_add_anime":
        pending_uploads[user.id] = {"stage": "adding_anime"}
        await query.edit_message_text("✏️ Send the new anime name (text).")
        return

    # Choose anime
    m = re.match(r"^upload_choose_anime::(.+)$", data)
    if m:
        anime = unquote_plus(m.group(1))
        st = {"stage": "character_select", "anime": anime}
        pending_uploads[user.id] = st
        chars = await db_list_characters(pool, anime)
        kb = build_character_keyboard(chars)
        await query.edit_message_text(f"🎬 Anime: *{anime}*\nSelect Character:", reply_markup=kb, parse_mode="Markdown")
        return

    # Add character branch
    if data == "upload_add_character":
        if not st or "anime" not in st:
            await query.edit_message_text("⚠️ Please select an anime first.")
            return
        st["stage"] = "adding_character"
        pending_uploads[user.id] = st
        await query.edit_message_text("✏️ Send the character name (text).")
        return

    # Choose character
    m = re.match(r"^upload_choose_character::(.+)$", data)
    if m:
        char = unquote_plus(m.group(1))
        st.update({"stage": "rarity_select", "character": char})
        pending_uploads[user.id] = st
        kb = build_rarity_keyboard()
        await query.edit_message_text(f"🎭 Character: *{char}*\nSelect rarity:", reply_markup=kb, parse_mode="Markdown")
        return

    # Rarity chosen
    m = re.match(r"^upload_rarity::(\d+)$", data)
    if m:
        rid = int(m.group(1))
        st["rarity"] = rid
        st["stage"] = "awaiting_photo"
        pending_uploads[user.id] = st
        await query.edit_message_text("📷 Now send the card photo in this private chat (choose an image).")
        return

    # Back to anime list
    if data == "upload_back_anime":
        animes = await db_list_animes(pool)
        kb = build_anime_keyboard(animes)
        pending_uploads[user.id] = {"stage": "anime_select"}
        await query.edit_message_text("🎬 Select Anime:", reply_markup=kb)
        return

    # Back to character list
    if data == "upload_back_char":
        anime = st.get("anime")
        chars = await db_list_characters(pool, anime)
        kb = build_character_keyboard(chars)
        st["stage"] = "character_select"
        pending_uploads[user.id] = st
        await query.edit_message_text("Select Character:", reply_markup=kb)
        return

    # Preview / Confirm Save
    if data == "upload_confirm_save":
        # confirm final save
        if not st or st.get("stage") not in ("preview", "confirm_save"):
            await query.edit_message_text("⚠️ Nothing to save.")
            return
        # Save to DB
        anime = st.get("anime")
        character = st.get("character")
        rarity = st.get("rarity")
        file_id = st.get("file_id")
        try:
            card_id = await add_card(pool, anime, character, rarity, file_id, user.id)
            await give_card_to_user(pool, user.id, card_id)
        except Exception as e:
            await query.edit_message_text(f"❌ Database error saving card: {e}")
            pending_uploads.pop(user.id, None)
            return

        # Broadcast to groups (fire-and-forget)
        try:
            groups = await get_all_groups(pool)
            caption = f"🎴 New Card!\n{rarity_to_text(rarity)[2]} {character}\n📌 ID: {card_id}\n🎬 {anime}"
            for gid in groups:
                try:
                    await context.bot.send_photo(chat_id=gid, photo=file_id, caption=caption)
                except Exception:
                    # ignore failure per group
                    pass
        except Exception:
            pass

        pending_uploads.pop(user.id, None)
        await query.edit_message_text(f"✅ Card saved! ID: {card_id}")
        return

    # Edit preview: let user re-enter fields
    if data == "upload_edit":
        if not st:
            await query.edit_message_text("⚠️ Nothing to edit.")
            return
        # provide edit options
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Anime", callback_data="upload_edit_field::anime")],
            [InlineKeyboardButton("Character", callback_data="upload_edit_field::character")],
            [InlineKeyboardButton("Rarity", callback_data="upload_edit_field::rarity")],
            [InlineKeyboardButton("Photo", callback_data="upload_edit_field::photo")],
            [InlineKeyboardButton("⬅️ Back to preview", callback_data="upload_back_to_preview")],
            [InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")]
        ])
        await query.edit_message_text("✏️ Choose field to edit:", reply_markup=kb)
        return

    # Edit field branches
    m = re.match(r"^upload_edit_field::(\w+)$", data)
    if m:
        field = m.group(1)
        st["stage"] = f"editing_{field}"
        pending_uploads[user.id] = st
        await query.edit_message_text(f"✏️ Send new value for *{field}* (or send a photo for photo):", parse_mode="Markdown")
        return

    if data == "upload_back_to_preview":
        # re-send preview
        if not st or "file_id" not in st:
            await query.edit_message_text("⚠️ No preview available.")
            return
        # edit message: replace with preview
        file_id = st["file_id"]
        caption = (
            f"🔎 Preview\n{rarity_to_text(st['rarity'])[2]} *{st['character']}*\n🎬 *{st['anime']}*\nID: (will be assigned)"
        )
        try:
            await query.edit_message_media(
                media=InputMediaPhoto(media=file_id, caption=caption, parse_mode="Markdown"),
                reply_markup=build_preview_keyboard()
            )
        except Exception:
            # fallback: edit text
            await query.edit_message_text(caption, parse_mode="Markdown", reply_markup=build_preview_keyboard())
        st["stage"] = "preview"
        pending_uploads[user.id] = st
        return

    # Admin edit_field (editing existing card)
    m = re.match(r"^edit_field::(\w+)::(\d+)$", data)
    if m:
        field, card_id = m.groups()
        pending_uploads[user.id] = {"stage": "admin_edit_awaiting", "admin_edit_field": field, "admin_edit_card": int(card_id)}
        await query.edit_message_text(f"✏️ Send new value for *{field}* of card {card_id}:", parse_mode="Markdown")
        return

# -------------------------
# Text handler (private)
# -------------------------
async def text_handler(update: Update, context):
    user = update.effective_user
    pool = context.application.bot_data.get("pool")
    if not pool:
        return
    if not update.message:
        return
    chat = update.effective_chat
    if chat.type != "private":
        return

    st = pending_uploads.get(user.id)
    if not st:
        return

    text = (update.message.text or "").strip()
    # editing existing admin card
    if st.get("stage") == "admin_edit_awaiting":
        field = st.get("admin_edit_field")
        card_id = st.get("admin_edit_card")
        if field == "rarity":
            try:
                new_r = int(text)
            except:
                await update.message.reply_text("Please send a numeric rarity id.")
                return
            await pool.execute("UPDATE cards SET rarity=$1 WHERE id=$2", new_r, card_id)
        else:
            await pool.execute(f"UPDATE cards SET {field}=$1 WHERE id=$2", text, card_id)
        pending_uploads.pop(user.id, None)
        await update.message.reply_text(f"✅ Card {card_id} updated.")
        return

    # adding anime (free text)
    if st.get("stage") == "adding_anime":
        anime = text
        st.update({"anime": anime, "stage": "character_select"})
        pending_uploads[user.id] = st
        chars = await db_list_characters(pool, anime)
        kb = build_character_keyboard(chars)
        await update.message.reply_text(f"🎬 Anime set to *{anime}*\nSelect character:", reply_markup=kb, parse_mode="Markdown")
        return

    # adding character (free text)
    if st.get("stage") == "adding_character":
        char = text
        st.update({"character": char, "stage": "rarity_select"})
        pending_uploads[user.id] = st
        kb = build_rarity_keyboard()
        await update.message.reply_text(f"Character set to *{char}*.\nSelect rarity:", reply_markup=kb, parse_mode="Markdown")
        return

    # editing fields from preview (anime/character/rarity)
    if st.get("stage", "").startswith("editing_"):
        fld = st["stage"].split("_", 1)[1]
        if fld == "rarity":
            try:
                new_r = int(text)
                st["rarity"] = new_r
            except:
                await update.message.reply_text("Please send a numeric rarity id (1-10).")
                return
        else:
            st[fld] = text
        # after edit, go back to awaiting_photo if we haven't file_id, else preview
        if "file_id" in st:
            st["stage"] = "preview"
            # send preview
            file_id = st["file_id"]
            caption = f"🔎 Preview\n{rarity_to_text(st['rarity'])[2]} *{st['character']}*\n🎬 *{st['anime']}*\nPress Confirm to save."
            await update.message.reply_photo(photo=file_id, caption=caption, reply_markup=build_preview_keyboard(), parse_mode="Markdown")
        else:
            st["stage"] = "awaiting_photo"
            await update.message.reply_text("Now send the card photo (image).")
        pending_uploads[user.id] = st
        return

# -------------------------
# Photo handler (private)
# -------------------------
async def photo_handler(update: Update, context):
    user = update.effective_user
    pool = context.application.bot_data.get("pool")
    if not pool:
        return
    if not update.message:
        return
    chat = update.effective_chat
    if chat.type != "private":
        return

    st = pending_uploads.get(user.id)
    if not st or st.get("stage") not in ("awaiting_photo", "editing_photo"):
        # not expecting a photo
        return

    if not update.message.photo:
        await update.message.reply_text("❌ Please send a photo.")
        return

    file_id = update.message.photo[-1].file_id
    st["file_id"] = file_id

    # move to preview
    st["stage"] = "preview"
    pending_uploads[user.id] = st

    # show preview with confirm/edit buttons
    name, pct, emoji = rarity_to_text(st.get("rarity", 1))
    caption = f"🔎 Preview\n{emoji} *{st.get('character','Unknown')}*\n🎬 *{st.get('anime','Unknown')}*\nRarity: {name} ({pct})\n\nPress Confirm & Save to store this card."
    await update.message.reply_photo(photo=file_id, caption=caption, reply_markup=build_preview_keyboard(), parse_mode="Markdown")

# -------------------------
# Register handlers
# -------------------------
def register_upload_handlers(application):
    application.add_handler(CommandHandler("upload", upload_cmd))
    application.add_handler(CommandHandler("addcard", upload_cmd))  # alias
    application.add_handler(CommandHandler("edit", edit_cmd))
    application.add_handler(CommandHandler("delete", delete_cmd))
    application.add_handler(CallbackQueryHandler(callback_router,
        pattern=r"^(upload_|edit_field::|upload_add_anime|upload_add_character|upload_cancel|edit_cancel|upload_back_|upload_confirm_save|upload_edit|upload_edit_field::|upload_back_to_preview|edit_field::)"))
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, text_handler))
    application.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE & ~filters.COMMAND, photo_handler))