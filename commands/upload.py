# commands/upload.py
import re
from urllib.parse import quote_plus, unquote_plus
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler, filters
from commands.utils import rarity_to_text
from db import add_card, ensure_user, give_card_to_user, get_all_groups, get_user_by_id, get_pool, get_cards_by_ids

pending_uploads = {}
ALLOWED_ROLES = {"owner","dev","admin","uploader"}
ADMIN_ROLES = {"owner","dev","admin"}

async def db_list_animes(pool):
    rows = await pool.fetch("SELECT anime FROM cards WHERE anime IS NOT NULL GROUP BY anime ORDER BY LOWER(anime)")
    return [r['anime'] for r in rows]

async def db_list_characters(pool, anime):
    rows = await pool.fetch("SELECT character FROM cards WHERE anime=$1 GROUP BY character ORDER BY LOWER(character)", anime)
    return [r['character'] for r in rows]

# --- Upload Command ---
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

# --- Edit Command ---
async def edit_cmd(update: Update, context):
    pool = context.application.bot_data["pool"]
    user = update.effective_user
    u = await get_user_by_id(pool, user.id)
    role = (u.get("role") or "user").lower()
    if role not in ADMIN_ROLES:
        await update.message.reply_text("❌ No permission.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /edit <card_id>")
        return
    card_id = int(args[0])
    pending_uploads[user.id] = {"stage":"edit_select_field","edit_card_id":card_id}
    keyboard = [
        [InlineKeyboardButton("Anime", callback_data=f"edit_field::anime::{card_id}")],
        [InlineKeyboardButton("Character", callback_data=f"edit_field::character::{card_id}")],
        [InlineKeyboardButton("Rarity", callback_data=f"edit_field::rarity::{card_id}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="edit_cancel")]
    ]
    await update.message.reply_text("✏️ Select field to edit:", reply_markup=InlineKeyboardMarkup(keyboard))

# --- Delete Command ---
async def delete_cmd(update: Update, context):
    pool = context.application.bot_data["pool"]
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

# --- Callback Router ---
async def callback_router(update: Update, context):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    pool = context.application.bot_data["pool"]
    data = query.data or ""
    st = pending_uploads.get(user.id, {})

    if data in ["upload_cancel","edit_cancel"]:
        pending_uploads.pop(user.id, None)
        await query.edit_message_text("❌ Operation cancelled.")
        return

    # Add Anime
    if data == "upload_add_anime":
        pending_uploads[user.id] = {"stage":"adding_anime"}
        await query.edit_message_text("✏️ Send the new anime name.")
        return

    # Choose Anime
    m = re.match(r"^upload_choose_anime::(.+)$", data)
    if m:
        anime = unquote_plus(m.group(1))
        pending_uploads[user.id] = {"stage":"character_select","anime":anime}
        chars = await db_list_characters(pool, anime)
        keyboard = [[InlineKeyboardButton(c, callback_data=f"upload_choose_character::{quote_plus(c)}")] for c in chars]
        keyboard.append([InlineKeyboardButton("➕ Add new character", callback_data="upload_add_character")])
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="upload_back_anime")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
        await query.edit_message_text(f"🎬 Anime: *{anime}*\nSelect character:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    # Add Character
    if data == "upload_add_character":
        if not st or "anime" not in st:
            await query.edit_message_text("⚠️ Please select anime first.")
            return
        st["stage"] = "adding_character"
        pending_uploads[user.id] = st
        await query.edit_message_text("✏️ Send character name.")
        return

    # Choose Character
    m = re.match(r"^upload_choose_character::(.+)$", data)
    if m:
        char = unquote_plus(m.group(1))
        st.update({"stage":"rarity_select","character":char})
        pending_uploads[user.id] = st
        keyboard = [[InlineKeyboardButton(f"{rarity_to_text(rid)[2]} {rarity_to_text(rid)[0]}", callback_data=f"upload_rarity::{rid}")] for rid in range(1,12)]
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="upload_back_char")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
        await query.edit_message_text(f"🎭 Character: *{char}*\nSelect rarity:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    # Choose Rarity
    m = re.match(r"^upload_rarity::(\d+)$", data)
    if m:
        rid = int(m.group(1))
        st["rarity"] = rid
        st["stage"] = "awaiting_photo"
        pending_uploads[user.id] = st
        await query.edit_message_text("📷 Please send the card photo now (private chat).")
        return

    # Back buttons
    if data == "upload_back_anime":
        animes = await db_list_animes(pool)
        keyboard = [[InlineKeyboardButton(a, callback_data=f"upload_choose_anime::{quote_plus(a)}")] for a in animes]
        keyboard.append([InlineKeyboardButton("➕ Add new anime", callback_data="upload_add_anime")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
        pending_uploads[user.id] = {"stage":"anime_select"}
        await query.edit_message_text("🎬 Select Anime:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data == "upload_back_char":
        anime = st.get("anime")
        chars = await db_list_characters(pool, anime)
        keyboard = [[InlineKeyboardButton(c, callback_data=f"upload_choose_character::{quote_plus(c)}")] for c in chars]
        keyboard.append([InlineKeyboardButton("➕ Add new character", callback_data="upload_add_character")])
        keyboard.append([InlineKeyboardButton("⬅️ Back to anime", callback_data="upload_back_anime")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
        st["stage"] = "character_select"
        pending_uploads[user.id] = st
        await query.edit_message_text("Select Character:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

# --- Text Handler ---
async def text_handler(update: Update, context):
    user = update.effective_user
    pool = context.application.bot_data["pool"]
    st = pending_uploads.get(user.id)
    if not st:
        return

    text = update.message.text.strip()

    if st.get("stage") == "awaiting_new_value":
        card_id = st["edit_card_id"]
        field = st["edit_field"]
        await pool.execute(f"UPDATE cards SET {field}=$1 WHERE id=$2", text, card_id)
        await update.message.reply_text(f"✅ Card {card_id} updated.")
        pending_uploads.pop(user.id, None)
        return

    if st.get("stage") == "adding_anime":
        anime = text
        pending_uploads[user.id] = {"stage":"character_select","anime":anime}
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

# --- Photo Handler + Confirm Preview ---
async def photo_handler(update: Update, context):
    user = update.effective_user
    pool = context.application.bot_data["pool"]
    st = pending_uploads.get(user.id)
    if not st or st.get("stage") != "awaiting_photo":
        return
    if not update.message.photo:
        await update.message.reply_text("❌ Please send a photo.")
        return

    file_id = update.message.photo[-1].file_id
    st["photo_file_id"] = file_id
    st["stage"] = "confirm_photo"
    pending_uploads[user.id] = st

    # Show preview
    rid = st["rarity"]
    name, pct, emoji = rarity_to_text(rid)
    text = f"🔎 Preview\n{emoji} {st['character']}\n🎬 {st['anime']}\nRarity: {name} ({pct})\n\nPress Confirm & Save to store this card."
    keyboard = [
        [InlineKeyboardButton("✅ Confirm & Save", callback_data="confirm_save")],
        [InlineKeyboardButton("✏️ Edit", callback_data="edit_upload")],
        [InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")]
    ]
    await update.message.reply_photo(file_id, caption=text, reply_markup=InlineKeyboardMarkup(keyboard))

# --- Confirm / Edit Handlers ---
async def confirm_router(update: Update, context):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    pool = context.application.bot_data["pool"]
    st = pending_uploads.get(user.id)
    if not st or st.get("stage") != "confirm_photo":
        await query.edit_message_text("❌ Nothing to confirm.")
        return

    data = query.data
    if data == "confirm_save":
        file_id = st["photo_file_id"]
        anime = st["anime"]
        character = st["character"]
        rarity = st["rarity"]
        card_id = await add_card(pool, anime, character, rarity, file_id, user.id)
        await give_card_to_user(pool, user.id, card_id)
        # Broadcast to all groups
        for gid in await get_all_groups(pool):
            try:
                await context.bot.send_photo(chat_id=gid, photo=file_id,
                    caption=f"🎴 New Card: {rarity_to_text(rarity)[2]} {character} — ID {card_id}")
            except:
                pass
        await query.edit_message_caption(caption=f"✅ Uploaded!\n{rarity_to_text(rarity)[2]} {character}\n🎬 {anime}\nID: {card_id}\nRarity: {rarity_to_text(rarity)[0]}")
        pending_uploads.pop(user.id, None)
        return

    if data == "edit_upload":
        st["stage"] = "awaiting_photo"
        pending_uploads[user.id] = st
        await query.edit_message_caption(caption="✏️ Send new photo to replace the card.")

# --- Register Handlers ---
def register_upload_handlers(app):
    app.add_handler(CommandHandler("upload", upload_cmd))
    app.add_handler(CommandHandler("edit", edit_cmd))
    app.add_handler(CommandHandler("delete", delete_cmd))
    # main callback router
    app.add_handler(CallbackQueryHandler(callback_router, pattern=r"^(upload_|edit_field::|upload_add_anime|upload_add_character|upload_cancel|edit_cancel|upload_back_).*"))
    # confirm photo callbacks
    app.add_handler(CallbackQueryHandler(confirm_router, pattern=r"^(confirm_save|edit_upload)$"))
    # text & photo handlers
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, text_handler))
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE & ~filters.COMMAND, photo_handler))