# commands/upload.py
import re
from urllib.parse import quote_plus, unquote_plus
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler, filters
from commands.utils import rarity_to_text
from db import add_card, ensure_user, get_all_groups, give_card_to_user, get_user_by_id, get_cards_by_ids

# NO module-level pending_uploads anymore — use application.bot_data["pending_uploads"]

ALLOWED_ROLES = {"owner", "dev", "admin", "uploader"}
ADMIN_ROLES = {"owner", "dev", "admin"}

async def _get_pending(application):
    return application.bot_data.setdefault("pending_uploads", {})

# helper: list anime/characters using pool
async def db_list_animes(pool):
    rows = await pool.fetch("SELECT anime FROM cards WHERE anime IS NOT NULL GROUP BY anime ORDER BY LOWER(anime)")
    return [r['anime'] for r in rows]

async def db_list_characters(pool, anime):
    rows = await pool.fetch("SELECT character FROM cards WHERE anime=$1 GROUP BY character ORDER BY LOWER(character)", anime)
    return [r['character'] for r in rows]

# /upload command (private)
async def upload_cmd(update: Update, context):
    pool = context.application.bot_data.get("pool")
    chat = update.effective_chat
    user = update.effective_user
    if not pool:
        await update.message.reply_text("❌ DB not ready. Try again later.")
        return
    if not chat or chat.type != "private":
        await update.message.reply_text("❌ Use /upload in a private chat with the bot.")
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

    pending = await _get_pending(context.application)
    pending[user.id] = {"stage": "anime_select"}
    await update.message.reply_text("🎬 Select Anime:", reply_markup=InlineKeyboardMarkup(keyboard))

# admin edit/delete
async def edit_cmd(update: Update, context):
    pool = context.application.bot_data.get("pool")
    user = update.effective_user
    u = await get_user_by_id(pool, user.id)
    role = (u.get("role") or "user").lower()
    if role not in ADMIN_ROLES:
        await update.message.reply_text("❌ You don't have permission.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /edit <card_id>")
        return
    card_id = int(args[0])
    pending = await _get_pending(context.application)
    pending[user.id] = {"stage": "edit_select_field", "edit_card_id": card_id}
    keyboard = [
        [InlineKeyboardButton("Anime", callback_data=f"edit_field::anime::{card_id}")],
        [InlineKeyboardButton("Character", callback_data=f"edit_field::character::{card_id}")],
        [InlineKeyboardButton("Rarity", callback_data=f"edit_field::rarity::{card_id}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="edit_cancel")]
    ]
    await update.message.reply_text("✏️ Select field to edit:", reply_markup=InlineKeyboardMarkup(keyboard))

async def delete_cmd(update: Update, context):
    pool = context.application.bot_data.get("pool")
    user = update.effective_user
    u = await get_user_by_id(pool, user.id)
    role = (u.get("role") or "user").lower()
    if role not in ADMIN_ROLES:
        await update.message.reply_text("❌ You don't have permission.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /delete <card_id>")
        return
    card_id = int(context.args[0])
    await pool.execute("DELETE FROM cards WHERE id=$1", card_id)
    await update.message.reply_text(f"✅ Card {card_id} deleted.")

# callback router
async def callback_router(update: Update, context):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    pool = context.application.bot_data.get("pool")
    data = query.data or ""
    pending = await _get_pending(context.application)
    st = pending.get(user.id, {})

    # cancel flows
    if data == "upload_cancel":
        pending.pop(user.id, None)
        await query.edit_message_text("❌ Upload cancelled.")
        return
    if data == "edit_cancel":
        pending.pop(user.id, None)
        await query.edit_message_text("❌ Edit cancelled.")
        return

    if data == "upload_add_anime":
        pending[user.id] = {"stage": "adding_anime"}
        await query.edit_message_text("✏️ Send the new anime name (text).")
        return

    m = re.match(r"^upload_choose_anime::(.+)$", data)
    if m:
        anime = unquote_plus(m.group(1))
        pending[user.id] = {"stage": "character_select", "anime": anime}
        chars = await db_list_characters(pool, anime)
        keyboard = [[InlineKeyboardButton(c, callback_data=f"upload_choose_character::{quote_plus(c)}")] for c in chars]
        keyboard.append([InlineKeyboardButton("➕ Add new character", callback_data="upload_add_character")])
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="upload_back_anime")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
        await query.edit_message_text(f"🎬 Anime: *{anime}*\nSelect character:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    if data == "upload_add_character":
        if not st or "anime" not in st:
            await query.edit_message_text("⚠️ Please select an anime first.")
            return
        st["stage"] = "adding_character"
        pending[user.id] = st
        await query.edit_message_text("✏️ Send character name (text).")
        return

    m = re.match(r"^upload_choose_character::(.+)$", data)
    if m:
        char = unquote_plus(m.group(1))
        st.update({"stage": "rarity_select", "character": char})
        pending[user.id] = st
        keyboard = [[InlineKeyboardButton(f"{rarity_to_text(rid)[2]} {rarity_to_text(rid)[0]}", callback_data=f"upload_rarity::{rid}")] for rid in range(1, 11)]
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="upload_back_char")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
        await query.edit_message_text(f"🎭 Character: *{char}*\nSelect rarity:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    m = re.match(r"^upload_rarity::(\d+)$", data)
    if m:
        rid = int(m.group(1))
        st["rarity"] = rid
        st["stage"] = "awaiting_photo"
        pending[user.id] = st
        await query.edit_message_text("📷 Now send the card photo (in this private chat).")
        return

    if data == "upload_back_anime":
        animes = await db_list_animes(pool)
        keyboard = [[InlineKeyboardButton(a, callback_data=f"upload_choose_anime::{quote_plus(a)}")] for a in animes]
        keyboard.append([InlineKeyboardButton("➕ Add new anime", callback_data="upload_add_anime")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
        pending[user.id] = {"stage": "anime_select"}
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
        pending[user.id] = st
        await query.edit_message_text("Select Character:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    m = re.match(r"^edit_field::(\w+)::(\d+)$", data)
    if m:
        field, card_id = m.groups()
        pending[user.id] = {"edit_card_id": int(card_id), "edit_field": field, "stage": "awaiting_new_value"}
        await query.edit_message_text(f"✏️ Send new value for *{field}* of card {card_id}:", parse_mode="Markdown")
        return

# text handler (private)
async def text_handler(update: Update, context):
    if update.effective_chat.type != "private":
        return
    user = update.effective_user
    pool = context.application.bot_data.get("pool")
    pending = await _get_pending(context.application)
    st = pending.get(user.id)
    if not st:
        return

    text = (update.message.text or "").strip()
    if not text:
        return

    if st.get("stage") == "awaiting_new_value":
        card_id = st["edit_card_id"]
        field = st["edit_field"]
        # Basic safety: only allow certain fields
        if field not in ("anime", "character", "rarity", "file_id"):
            await update.message.reply_text("❌ Invalid field.")
        else:
            await pool.execute(f"UPDATE cards SET {field}=$1 WHERE id=$2", text, card_id)
            await update.message.reply_text(f"✅ Card {card_id} updated: {field} = {text}")
        pending.pop(user.id, None)
        return

    if st.get("stage") == "adding_anime":
        anime = text
        pending[user.id] = {"stage": "character_select", "anime": anime}
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
        pending[user.id] = st
        keyboard = [[InlineKeyboardButton(f"{rarity_to_text(rid)[2]} {rarity_to_text(rid)[0]}", callback_data=f"upload_rarity::{rid}")] for rid in range(1, 11)]
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="upload_back_char")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
        await update.message.reply_text(f"Character set to *{text}*. Select rarity:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

# photo handler (private)
async def photo_handler(update: Update, context):
    if update.effective_chat.type != "private":
        return
    user = update.effective_user
    pool = context.application.bot_data.get("pool")
    pending = await _get_pending(context.application)
    st = pending.get(user.id)
    if not st:
        # helpful debug message
        await update.message.reply_text("⚠️ No pending upload found. Start with /upload or select an upload flow first.")
        return

    if st.get("stage") != "awaiting_photo":
        await update.message.reply_text("⚠️ I'm not expecting a photo right now. Follow the upload prompts.")
        return

    if not update.message.photo:
        await update.message.reply_text("❌ Please send a photo (image).")
        return

    file_id = update.message.photo[-1].file_id
    anime = st.get("anime")
    character = st.get("character")
    rarity = st.get("rarity")
    if not (anime and character and rarity):
        await update.message.reply_text("❌ Upload state is incomplete. Please restart with /upload.")
        pending.pop(user.id, None)
        return

    try:
        card_id = await add_card(pool, anime, character, rarity, file_id, user.id)
        await give_card_to_user(pool, user.id, card_id)
    except Exception as e:
        await update.message.reply_text(f"❌ Database Error: {e}")
        pending.pop(user.id, None)
        return

    name, pct, emoji = rarity_to_text(rarity)
    await update.message.reply_text(
        f"✅ Card Uploaded Successfully!\n🎴 ID: {card_id}\n{emoji} {character}\n🎬 {anime}\n🏷 {name} ({pct})"
    )

    # broadcast to groups (best-effort)
    try:
        groups = await get_all_groups(pool)
        for gid in groups:
            try:
                await context.bot.send_photo(chat_id=gid, photo=file_id, caption=f"🎴 New Card!\n{emoji} {character}\nID: {card_id}\n🎬 {anime}")
            except Exception:
                pass
    except Exception:
        pass

    pending.pop(user.id, None)

def register_upload_handlers(application):
    application.add_handler(CommandHandler("upload", upload_cmd))
    application.add_handler(CommandHandler("edit", edit_cmd))
    application.add_handler(CommandHandler("delete", delete_cmd))
    application.add_handler(CallbackQueryHandler(callback_router, pattern=r"^(upload_|edit_field::|upload_add_anime|upload_add_character|upload_cancel|edit_cancel|upload_back_).*"))
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, text_handler))
    application.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE & ~filters.COMMAND, photo_handler))