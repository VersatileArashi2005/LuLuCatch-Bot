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

pending_uploads = {}

def db_list_animes():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT anime FROM cards WHERE anime IS NOT NULL ORDER BY LOWER(anime) ASC")
        return [r['anime'] for r in cur.fetchall()]

def db_list_characters(anime):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT character FROM cards WHERE anime=%s AND character IS NOT NULL ORDER BY LOWER(character) ASC", (anime,))
        return [r['character'] for r in cur.fetchall()]

ALLOWED_ROLES = {"owner", "dev", "admin", "uploader"}

# ------------------ Upload Command (DM-only) ------------------
async def upload_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if not chat or chat.type != "private":
        await update.message.reply_text("❌ /upload ကို private chat မှာပဲ အသုံးပြုနိုင်ပါတယ်။ (Bot ကို DM ဖြင့်ဖန်တီးပါ)")
        return

    ensure_user(user.id, user.first_name or user.username or "User")

    u = get_user_by_id(user.id)
    role = (u.get('role') if u else None) or "user"
    if role.lower() not in ALLOWED_ROLES:
        await update.message.reply_text("❌ သင်မှာ upload ခွင့်မရှိပါ (Uploader/Admin/Dev/Owner တစ်ခုခု ဖြစ်ရပါမယ်).")
        return

    animes = db_list_animes()
    keyboard = [[InlineKeyboardButton(a, callback_data=f"upload_choose_anime::{quote_plus(a)}")] for a in animes]
    keyboard.append([InlineKeyboardButton("➕ Add new anime", callback_data="upload_add_anime")])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])

    pending_uploads[user.id] = {"stage": "anime_select"}
    await update.message.reply_text(
        "🌸 Anime ရွေးပါ — မင်း add လုပ်ချင်တဲ့ anime မရှိရင် ➕ Add new anime ကိုနှိပ်ပါ။",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ------------------ Callback Handler ------------------
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data or ""

    st = pending_uploads.get(user.id)

    if data == "upload_cancel":
        pending_uploads.pop(user.id, None)
        await query.edit_message_text("✅ Upload canceled.")
        return

    if data == "upload_add_anime":
        pending_uploads[user.id] = {"stage": "adding_anime"}
        await query.edit_message_text("✏️ စာရိုက်ပေးပါ — Add new anime name.")
        return

    m = re.match(r"^upload_choose_anime::(.+)$", data)
    if m:
        anime = unquote_plus(m.group(1))
        pending_uploads[user.id] = {"stage": "character_select", "anime": anime}
        chars = db_list_characters(anime)
        keyboard = [[InlineKeyboardButton(c, callback_data=f"upload_choose_character::{quote_plus(c)}")] for c in chars]
        keyboard.append([InlineKeyboardButton("➕ Add new character", callback_data="upload_add_character")])
        keyboard.append([InlineKeyboardButton("⬅️ Back to anime", callback_data="upload_back_anime")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
        await query.edit_message_text(f"🎬 Anime: *{anime}*\nအခု Character ရွေးပါ (Add new character if missing).",
                                      reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    if data == "upload_add_character":
        if not st or not st.get("anime"):
            await query.edit_message_text("⚠️ ပြဿနာ — Anime ကိုရွေးရှာအရင် (Back and choose anime).")
            return
        pending_uploads[user.id]["stage"] = "adding_character"
        await query.edit_message_text("✏️ Send the character name to add for the chosen anime.")
        return

    if data == "upload_back_anime":
        animes = db_list_animes()
        keyboard = [[InlineKeyboardButton(a, callback_data=f"upload_choose_anime::{quote_plus(a)}")] for a in animes]
        keyboard.append([InlineKeyboardButton("➕ Add new anime", callback_data="upload_add_anime")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
        pending_uploads[user.id] = {"stage": "anime_select"}
        await query.edit_message_text("🌸 Anime ရွေးပါ — Add new anime if missing.",
                                      reply_markup=InlineKeyboardMarkup(keyboard))
        return

    m = re.match(r"^upload_choose_character::(.+)$", data)
    if m:
        char = unquote_plus(m.group(1))
        anime = st.get("anime")
        st.update({"stage": "rarity_select", "character": char})
        pending_uploads[user.id] = st
        keyboard = [[InlineKeyboardButton(f"{rarity_to_text(rid)[2]} {rarity_to_text(rid)[0].capitalize()} ({rarity_to_text(rid)[1]}%)",
                                           callback_data=f"upload_rarity::{rid}")] for rid in range(1, 11)]
        keyboard.append([InlineKeyboardButton("⬅️ Back to characters", callback_data="upload_back_char")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
        await query.edit_message_text(f"🔖 Selected: *{char}* from *{anime}*\nChoose rarity:",
                                      reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    if data == "upload_back_char":
        anime = st.get("anime")
        chars = db_list_characters(anime)
        keyboard = [[InlineKeyboardButton(c, callback_data=f"upload_choose_character::{quote_plus(c)}")] for c in chars]
        keyboard.append([InlineKeyboardButton("➕ Add new character", callback_data="upload_add_character")])
        keyboard.append([InlineKeyboardButton("⬅️ Back to anime", callback_data="upload_back_anime")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
        pending_uploads[user.id]["stage"] = "character_select"
        await query.edit_message_text("Select character:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    m = re.match(r"^upload_rarity::(\d+)$", data)
    if m:
        if not st or st.get("stage") != "rarity_select":
            pending_uploads.pop(user.id, None)
            await query.edit_message_text("⚠️ Session expired. Start /upload again.")
            return
        st["rarity"] = int(m.group(1))
        st["stage"] = "awaiting_photo"
        pending_uploads[user.id] = st
        await query.edit_message_text("📷 Now *send the card image/photo* (as photo).", parse_mode="Markdown")
        return

    await query.edit_message_text("Unsupported action or expired session. Start /upload again if needed.")
    pending_uploads.pop(user.id, None)

# ------------------ Text Handler (DM-only) ------------------
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not chat or chat.type != "private":
        return

    st = pending_uploads.get(user.id)
    if not st:
        return

    text = (update.message.text or "").strip()

    if st.get("stage") == "adding_anime":
        anime = text
        pending_uploads[user.id] = {"stage": "character_select", "anime": anime}
        chars = db_list_characters(anime)
        keyboard = [[InlineKeyboardButton(c, callback_data=f"upload_choose_character::{quote_plus(c)}")] for c in chars]
        keyboard.append([InlineKeyboardButton("➕ Add new character", callback_data="upload_add_character")])
        keyboard.append([InlineKeyboardButton("⬅️ Back to anime", callback_data="upload_back_anime")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
        await update.message.reply_text(f"🎬 Added/selected anime: *{anime}*\nSelect character:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    if st.get("stage") == "adding_character":
        char = text
        st["character"] = char
        st["stage"] = "rarity_select"
        pending_uploads[user.id] = st
        keyboard = [[InlineKeyboardButton(f"{rarity_to_text(rid)[2]} {rarity_to_text(rid)[0].capitalize()} ({rarity_to_text(rid)[1]}%)",
                                           callback_data=f"upload_rarity::{rid}")] for rid in range(1, 11)]
        keyboard.append([InlineKeyboardButton("⬅️ Back to characters", callback_data="upload_back_char")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
        await update.message.reply_text(f"✅ Character set to *{char}*. Choose rarity next:",
                                      reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    await update.message.reply_text("⚠️ အဲဒီအဆင့်မှာ စာရိုက်ဖို့ မလိုပါဘူး — buttons နဲ့ရွေးပါ။")

# ------------------ Photo Handler (DM-only) ------------------
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not chat or chat.type != "private":
        return

    st = pending_uploads.get(user.id)
    if not st or st.get("stage") != "awaiting_photo":
        return

    if not update.message.photo:
        await update.message.reply_text("Please send a photo (as Telegram photo).")
        return

    st["file_id"] = update.message.photo[-1].file_id
    anime = st.get("anime")
    character = st.get("character")
    rarity = st.get("rarity")

    if not (anime and character and rarity):
        pending_uploads.pop(user.id, None)
        await update.message.reply_text("⚠️ Missing data. Start /upload again.")
        return

    try:
        card_id = add_card(anime, character, rarity, st["file_id"], user.id)
        give_card_to_user(user.id, card_id)
    except Exception as e:
        pending_uploads.pop(user.id, None)
        await update.message.reply_text(f"❌ DB error: {e}")
        return

    name, pct, emoji = rarity_to_text(rarity)
    await update.message.reply_text(
        f"✅ Uploaded!\n🎴 ID: {card_id}\n{emoji} {character}\n🎬 {anime}\n🏷 {name.capitalize()} ({pct}%)"
    )

    caption = (
        f"🎴 New card uploaded!\n{emoji} {character}\n📌 ID: {card_id}\n"
        f"🎬 Anime: {anime}\n🏷 Rarity: {name.capitalize()} ({pct}%)\nTry to claim it!"
    )
    try:
        for chat_id in get_all_groups():
            await context.bot.send_photo(chat_id=chat_id, photo=st["file_id"], caption=caption)
    except Exception:
        pass

    pending_uploads.pop(user.id, None)

# ------------------ Register Handlers ------------------
def register_handlers(application):
    application.add_handler(CommandHandler("upload", upload_cmd))
    application.add_handler(CallbackQueryHandler(callback_router, pattern=r"^upload_"))
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, text_handler))
    application.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE & ~filters.COMMAND, photo_handler))