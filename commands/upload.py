# commands/upload.py
import re
from urllib.parse import quote_plus, unquote_plus
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler, filters
from commands.utils import rarity_to_text
from db import (add_card, ensure_user, give_card_to_user, get_all_groups,
                get_user_by_id, get_pool, get_cards_by_ids)

pending_uploads = {}
ALLOWED_ROLES = {"owner","dev","admin","uploader"}
ADMIN_ROLES = {"owner","dev","admin"}

# --- DB helpers ---
async def db_list_animes(pool):
    rows = await pool.fetch("SELECT anime FROM cards WHERE anime IS NOT NULL GROUP BY anime ORDER BY LOWER(anime)")
    return [r['anime'] for r in rows]

async def db_list_characters(pool, anime):
    rows = await pool.fetch("SELECT character FROM cards WHERE anime=$1 GROUP BY character ORDER BY LOWER(character)", anime)
    return [r['character'] for r in rows]

# --- Commands ---
async def upload_cmd(update: Update, context):
    pool = context.application.bot_data["pool"]
    chat = update.effective_chat
    user = update.effective_user
    if chat.type != "private":
        await update.message.reply_text("❌ Use /upload in private chat (DM).")
        return
    await ensure_user(pool, user.id, user.first_name or user.username or "User")
    u = await get_user_by_id(pool, user.id)
    role = (u.get("role") or "user").lower()
    if role not in ALLOWED_ROLES:
        await update.message.reply_text("❌ You don't have permission to upload.")
        return
    animes = await db_list_animes(pool)
    keyboard = [[InlineKeyboardButton(a, callback_data=f"upload_choose_anime::{quote_plus(a)}")] for a in animes]
    keyboard.append([InlineKeyboardButton("➕ Add new anime", callback_data="upload_add_anime")])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
    pending_uploads[user.id] = {"stage":"anime_select"}
    await update.message.reply_text("🎬 Select Anime:", reply_markup=InlineKeyboardMarkup(keyboard))

# --- Callback Router ---
async def callback_router(update: Update, context):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    pool = context.application.bot_data["pool"]
    data = query.data or ""
    st = pending_uploads.get(user.id, {})

    # --- Cancel handlers ---
    if data in {"upload_cancel","edit_cancel"}:
        pending_uploads.pop(user.id, None)
        await query.edit_message_text("❌ Operation cancelled.")
        return

    # --- Add new anime ---
    if data == "upload_add_anime":
        pending_uploads[user.id] = {"stage":"adding_anime"}
        await query.edit_message_text("✏️ Send the new anime name.")
        return

    # --- Choose anime ---
    m = re.match(r"^upload_choose_anime::(.+)$", data)
    if m:
        anime = unquote_plus(m.group(1))
        st.update({"stage":"character_select","anime":anime})
        pending_uploads[user.id] = st
        chars = await db_list_characters(pool, anime)
        keyboard = [[InlineKeyboardButton(c, callback_data=f"upload_choose_character::{quote_plus(c)}")] for c in chars]
        keyboard.append([InlineKeyboardButton("➕ Add new character", callback_data="upload_add_character")])
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="upload_back_anime")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
        await query.edit_message_text(f"🎬 Anime: *{anime}*\nSelect character:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    # --- Add new character ---
    if data == "upload_add_character":
        if not st or "anime" not in st:
            await query.edit_message_text("⚠️ Please select anime first.")
            return
        st["stage"] = "adding_character"
        pending_uploads[user.id] = st
        await query.edit_message_text("✏️ Send character name.")
        return

    # --- Choose character ---
    m = re.match(r"^upload_choose_character::(.+)$", data)
    if m:
        char = unquote_plus(m.group(1))
        st.update({"stage":"rarity_select","character":char})
        pending_uploads[user.id]=st
        keyboard = [[InlineKeyboardButton(f"{rarity_to_text(rid)[2]} {rarity_to_text(rid)[0]}", callback_data=f"upload_rarity::{rid}")] for rid in range(1,12)]
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="upload_back_char")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
        await query.edit_message_text(f"🎭 Character: *{char}*\nSelect rarity:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    # --- Choose rarity ---
    m = re.match(r"^upload_rarity::(\d+)$", data)
    if m:
        rid = int(m.group(1))
        st.update({"stage":"preview","rarity":rid})
        pending_uploads[user.id] = st
        keyboard = [
            [InlineKeyboardButton("✅ Confirm & Save", callback_data="upload_confirm_save")],
            [InlineKeyboardButton("✏️ Edit", callback_data="upload_edit")],
            [InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")]
        ]
        await query.edit_message_text(f"📷 Send the card photo now in this chat.\n\nPreview will show after sending.", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # --- Confirm / Edit / Cancel at preview ---
    if st.get("stage") == "preview":
        if data == "upload_confirm_save":
            # Save to DB
            if "file_id" not in st:
                await query.edit_message_text("⚠️ Send the photo first!")
                return
            anime = st["anime"]; character = st["character"]; rarity = st["rarity"]; file_id = st["file_id"]
            card_id = await add_card(pool, anime, character, rarity, file_id, user.id)
            await give_card_to_user(pool, user.id, card_id)
            name,pct,emoji = rarity_to_text(rarity)
            await query.edit_message_text(f"✅ Uploaded!\n{emoji} {character}\n🎬 {anime}\nID: {card_id}\nRarity: {name}")
            for gid in await get_all_groups(pool):
                try:
                    await context.bot.send_photo(chat_id=gid, photo=file_id, caption=f"🎴 New Card: {emoji} {character} — ID {card_id}")
                except: pass
            pending_uploads.pop(user.id, None)
            return
        elif data == "upload_edit":
            st["stage"] = "awaiting_photo"
            pending_uploads[user.id] = st
            await query.edit_message_text("✏️ Resend the photo to edit the card.")
            return

    # --- Navigation buttons ---
    if data == "upload_back_anime":
        await upload_cmd(update, context)
        return
    if data == "upload_back_char":
        anime = st.get("anime")
        chars = await db_list_characters(pool, anime)
        keyboard = [[InlineKeyboardButton(c, callback_data=f"upload_choose_character::{quote_plus(c)}")] for c in chars]
        keyboard.append([InlineKeyboardButton("➕ Add new character", callback_data="upload_add_character")])
        keyboard.append([InlineKeyboardButton("⬅️ Back to anime", callback_data="upload_back_anime")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")]
        )
        st["stage"] = "character_select"
        pending_uploads[user.id] = st
        await query.edit_message_text("Select Character:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

# --- Text handler ---
async def text_handler(update: Update, context):
    user = update.effective_user
    pool = context.application.bot_data["pool"]
    st = pending_uploads.get(user.id)
    if not st:
        return
    text = update.message.text.strip()
    if st.get("stage") == "adding_anime":
        anime = text
        st.update({"anime":anime,"stage":"character_select"})
        pending_uploads[user.id] = st
        chars = await db_list_characters(pool, anime)
        keyboard = [[InlineKeyboardButton(c, callback_data=f"upload_choose_character::{quote_plus(c)}")] for c in chars]
        keyboard.append([InlineKeyboardButton("➕ Add new character", callback_data="upload_add_character")])
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="upload_back_anime")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
        await update.message.reply_text(f"🎬 Anime set to *{anime}*.\nSelect character:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return
    if st.get("stage") == "adding_character":
        st["character"] = text
        st["stage"] = "rarity_select"
        pending_uploads[user.id] = st
        keyboard = [[InlineKeyboardButton(f"{rarity_to_text(rid)[2]} {rarity_to_text(rid)[0]}", callback_data=f"upload_rarity::{rid}")] for rid in range(1,12)]
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="upload_back_char")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
        await update.message.reply_text(f"Character set to *{text}*. Select rarity:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

# --- Photo handler ---
async def photo_handler(update: Update, context):
    user = update.effective_user
    pool = context.application.bot_data["pool"]
    st = pending_uploads.get(user.id)
    if not st or st.get("stage") not in {"awaiting_photo","preview"}:
        return
    if not update.message.photo:
        await update.message.reply_text("❌ Please send a photo.")
        return
    file_id = update.message.photo[-1].file_id
    st["file_id"] = file_id
    pending_uploads[user.id] = st
    # Send preview + Confirm/Edit/Cancel
    keyboard = [
        [InlineKeyboardButton("✅ Confirm & Save", callback_data="upload_confirm_save")],
        [InlineKeyboardButton("✏️ Edit", callback_data="upload_edit")],
        [InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")]
    ]
    await update.message.reply_photo(photo=file_id, caption=f"📷 Preview for *{st['character']}* — *{st['anime']}*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# --- Register handlers ---
def register_upload_handlers(app):
    app.add_handler(CommandHandler("upload", upload_cmd))
    app.add_handler(CallbackQueryHandler(callback_router, pattern=r"^(upload_|edit_field::|upload_add_anime|upload_add_character|upload_cancel|edit_cancel|upload_back_|upload_confirm_save|upload_edit)"))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, text_handler))
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE & ~filters.COMMAND, photo_handler))