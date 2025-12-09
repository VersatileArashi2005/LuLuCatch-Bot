# commands/upload.py
import re
from urllib.parse import quote_plus, unquote_plus
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler, filters
from commands.utils import rarity_to_text
from db import add_card, ensure_user, get_all_cards, db  # note: we'll call pool functions directly
from db import get_all_cards as _get_all_cards  # to fetch
from db import get_all_groups, give_card_to_user, get_user_by_id
from db import get_cards_by_ids

# We'll keep a simple in-memory pending uploads map (per-run)
pending_uploads = {}

ALLOWED_ROLES = {"owner", "dev", "admin", "uploader"}
ADMIN_ROLES = {"owner", "dev", "admin"}

# helper: list anime from DB
async def db_list_animes(pool):
    rows = await pool.fetch("SELECT anime FROM cards WHERE anime IS NOT NULL GROUP BY anime ORDER BY LOWER(anime)")
    return [r['anime'] for r in rows]

async def db_list_characters(pool, anime):
    rows = await pool.fetch("SELECT character FROM cards WHERE anime=$1 GROUP BY character ORDER BY LOWER(character)", anime)
    return [r['character'] for r in rows]

async def upload_cmd(update: Update, context):
    pool = context.application.bot_data.get("pool")
    chat = update.effective_chat
    user = update.effective_user
    if not pool:
        await update.message.reply_text("DB not ready.")
        return
    if chat.type != "private":
        await update.message.reply_text("❌ Use /upload in PM with the bot.")
        return

    await ensure_user(pool, user.id, user.first_name or user.username or "User")
    u = await get_user_by_id(pool, user.id)
    role = (u.get("role") or "user").lower()
    if role not in ALLOWED_ROLES:
        await update.message.reply_text("❌ You don't have upload permission.")
        return

    animes = await db_list_animes(pool)
    keyboard = [[InlineKeyboardButton(a, callback_data=f"upload_choose_anime::{quote_plus(a)}")] for a in animes]
    keyboard.append([InlineKeyboardButton("➕ Add new anime", callback_data="upload_add_anime")])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])

    pending_uploads[user.id] = {"stage": "anime_select"}
    await update.message.reply_text("🎬 Select Anime:", reply_markup=InlineKeyboardMarkup(keyboard))

async def edit_cmd(update: Update, context):
    user = update.effective_user
    pool = context.application.bot_data.get("pool")
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
    pending_uploads[user.id] = {"stage": "edit_select_field", "edit_card_id": card_id}
    keyboard = [
        [InlineKeyboardButton("Anime", callback_data=f"edit_field::anime::{card_id}")],
        [InlineKeyboardButton("Character", callback_data=f"edit_field::character::{card_id}")],
        [InlineKeyboardButton("Rarity", callback_data=f"edit_field::rarity::{card_id}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="edit_cancel")]
    ]
    await update.message.reply_text("✏️ Select field to edit:", reply_markup=InlineKeyboardMarkup(keyboard))

async def delete_cmd(update: Update, context):
    user = update.effective_user
    pool = context.application.bot_data.get("pool")
    u = await get_user_by_id(pool, user.id)
    role = (u.get("role") or "user").lower()
    if role not in ADMIN_ROLES:
        await update.message.reply_text("❌ No permission.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /delete <card_id>")
        return
    card_id = int(context.args[0])
    await (await context.application.bot_data.get("pool")).execute("DELETE FROM cards WHERE id=$1", card_id)
    await update.message.reply_text(f"✅ Card {card_id} deleted.")

# Callback router
async def callback_router(update: Update, context):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    pool = context.application.bot_data.get("pool")
    data = query.data or ""
    st = pending_uploads.get(user.id, {})

    if data == "upload_cancel":
        pending_uploads.pop(user.id, None)
        await query.edit_message_text("❌ Upload cancelled.")
        return
    if data == "edit_cancel":
        pending_uploads.pop(user.id, None)
        await query.edit_message_text("❌ Edit cancelled.")
        return
    if data == "upload_add_anime":
        pending_uploads[user.id] = {"stage": "adding_anime"}
        await query.edit_message_text("✏️ Send the new anime name.")
        return

    m = re.match(r"^upload_choose_anime::(.+)$", data)
    if m:
        anime = unquote_plus(m.group(1))
        pending_uploads[user.id] = {"stage":"character_select", "anime": anime}
        chars = await db_list_characters(pool, anime)
        keyboard = [[InlineKeyboardButton(c, callback_data=f"upload_choose_character::{quote_plus(c)}")] for c in chars]
        keyboard.append([InlineKeyboardButton("➕ Add new character", callback_data="upload_add_character")])
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="upload_back_anime")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
        await query.edit_message_text(f"🎬 Anime: *{anime}*\nSelect character:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    if data == "upload_add_character":
        if not st or "anime" not in st:
            await query.edit_message_text("⚠️ Please select anime first.")
            return
        st["stage"] = "adding_character"
        pending_uploads[user.id] = st
        await query.edit_message_text("✏️ Send character name.")
        return

    m = re.match(r"^upload_choose_character::(.+)$", data)
    if m:
        char = unquote_plus(m.group(1))
        st.update({"stage":"rarity_select", "character": char})
        pending_uploads[user.id] = st
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
        pending_uploads[user.id] = st
        await query.edit_message_text("📷 Now send the card photo (in private chat).")
        return

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

    m = re.match(r"^edit_field::(\w+)::(\d+)$", data)
    if m:
        field, card_id = m.groups()
        pending_uploads[user.id] = {"edit_card_id": int(card_id), "edit_field": field, "stage": "awaiting_new_value"}
        await query.edit_message_text(f"✏️ Send new value for *{field}* of card {card_id}:", parse_mode="Markdown")
        return

# Text handler (private)
async def text_handler(update: Update, context):
    user = update.effective_user
    pool = context.application.bot_data.get("pool")
    st = pending_uploads.get(user.id)
    if not st:
        return
    text = update.message.text.strip()

    if st.get("stage") == "awaiting_new_value":
        card_id = st["edit_card_id"]
        field = st["edit_field"]
        await (await context.application.bot_data.get("pool")).execute("UPDATE cards SET {}=$1 WHERE id=$2".format(field), text, card_id)
        await update.message.reply_text(f"✅ Card {card_id} updated: {field} = {text}")
        pending_uploads.pop(user.id, None)
        return

    if st.get("stage") == "adding_anime":
        anime = text
        pending_uploads[user.id] = {"stage":"character_select", "anime":anime}
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
        keyboard = [[InlineKeyboardButton(f"{rarity_to_text(rid)[2]} {rarity_to_text(rid)[0]}", callback_data=f"upload_rarity::{rid}")] for rid in range(1,11)]
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="upload_back_char")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
        await update.message.reply_text(f"Character set to *{text}*. Select rarity:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

# Photo handler (private)
async def photo_handler(update: Update, context):
    user = update.effective_user
    pool = context.application.bot_data.get("pool")
    st = pending_uploads.get(user.id)
    if not st or st.get("stage") != "awaiting_photo":
        return
    if not update.message.photo:
        await update.message.reply_text("Please send a photo.")
        return
    file_id = update.message.photo[-1].file_id
    anime = st["anime"]
    character = st["character"]
    rarity = st["rarity"]
    card_id = await add_card(pool, anime, character, rarity, file_id, user.id)
    await give_card_to_user(pool, user.id, card_id)
    name, pct, emoji = rarity_to_text(rarity)
    await update.message.reply_text(f"✅ Uploaded!\n{emoji} {character}\n🎬 {anime}\nID: {card_id}\nRarity: {name}")
    # broadcast to groups
    for gid in await get_all_groups(pool):
        try:
            await context.bot.send_photo(chat_id=gid, photo=file_id, caption=f"🎴 New Card: {emoji} {character} — ID {card_id}")
        except Exception:
            pass
    pending_uploads.pop(user.id, None)

def register_upload_handlers(application):
    application.add_handler(CommandHandler("upload", upload_cmd))
    application.add_handler(CommandHandler("edit", edit_cmd))
    application.add_handler(CommandHandler("delete", delete_cmd))
    application.add_handler(CallbackQueryHandler(callback_router, pattern=r"^(upload_|edit_field::|upload_add_anime|upload_add_character|upload_cancel|edit_cancel|upload_back_).*"))
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, text_handler))
    application.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE & ~filters.COMMAND, photo_handler))