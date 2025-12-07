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

# db functions we expect in db.py
from db import (
    add_card,
    ensure_user,
    give_card_to_user,
    get_all_groups,
    get_user_by_id,
    get_conn
)
from commands.utils import rarity_to_text

# in-memory per-user upload state
# structure example:
# pending_uploads[user_id] = {
#   "stage": "anime_select" | "adding_anime" | "character_select" | "adding_character" | "rarity_select" | "awaiting_photo",
#   "anime": "One Piece",
#   "character": "Nami",
#   "rarity": 4,
#   "file_id": "<tg file id>"
# }
pending_uploads = {}

# helper: read distinct anime names from DB (cards table)
def db_list_animes():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT anime FROM cards WHERE anime IS NOT NULL ORDER BY LOWER(anime) ASC")
        rows = cur.fetchall()
        return [r['anime'] for r in rows]

# helper: read distinct characters for given anime
def db_list_characters(anime):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT character FROM cards WHERE anime=%s AND character IS NOT NULL ORDER BY LOWER(character) ASC", (anime,))
        rows = cur.fetchall()
        return [r['character'] for r in rows]

# role check allowed set
ALLOWED_ROLES = {"owner", "dev", "admin", "uploader"}

async def upload_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Must be DM only
    chat = update.effective_chat
    user = update.effective_user

    if not chat or chat.type != "private":
        await update.message.reply_text("❌ /upload ကို private chat မှာပဲ အသုံးပြုနိုင်ပါတယ်။ (Bot ကို DM ဖြင့်ဖန်တီးပါ)")
        return

    ensure_user(user.id, user.first_name or user.username or "User")

    # role check
    u = get_user_by_id(user.id)
    role = (u.get('role') if u else None) or "user"
    if role.lower() not in ALLOWED_ROLES:
        await update.message.reply_text("❌ သင်မှာ upload ခွင့်မရှိပါ (Uploader/Admin/Dev/Owner တစ်ခုခု ဖြစ်ရပါမယ်).")
        return

    # start flow: present anime list + Add new button
    animes = db_list_animes()
    keyboard = []
    for a in animes:
        # callback encode anime name
        keyboard.append([InlineKeyboardButton(a, callback_data=f"upload_choose_anime::{quote_plus(a)}")])
    # Add new anime button
    keyboard.append([InlineKeyboardButton("➕ Add new anime", callback_data="upload_add_anime")])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])

    pending_uploads[user.id] = {"stage": "anime_select"}
    await update.message.reply_text(
        "🌸 Anime ရွေးပါ — မင်း add လုပ်ချင်တဲ့ anime မ(blank)ရှိရင် ➕ Add new anime ကိုနှိပ်ပါ။",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# callback: choose anime or add new
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data or ""

    if data == "upload_cancel":
        pending_uploads.pop(user.id, None)
        await query.edit_message_text("✅ Upload canceled.")
        return

    if data == "upload_add_anime":
        # go to adding anime (user types anime name)
        pending_uploads[user.id] = {"stage": "adding_anime"}
        await query.edit_message_text("✏️ စာရိုက်ပေးပါ — Add new anime name (just send the anime name text).")
        return

    m = re.match(r"^upload_choose_anime::(.+)$", data)
    if m:
        anime_enc = m.group(1)
        anime = unquote_plus(anime_enc)
        # set anime in pending and go to character selection
        pending_uploads[user.id] = {"stage": "character_select", "anime": anime}
        # list characters for this anime
        chars = db_list_characters(anime)
        keyboard = []
        for c in chars:
            keyboard.append([InlineKeyboardButton(c, callback_data=f"upload_choose_character::{quote_plus(c)}")])
        keyboard.append([InlineKeyboardButton("➕ Add new character", callback_data="upload_add_character")])
        keyboard.append([InlineKeyboardButton("⬅️ Back to anime", callback_data="upload_back_anime")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
        await query.edit_message_text(f"🎬 Anime: *{anime}*\nအခု Character ရွေးပါ (မရှိရင် Add new character ကိုနှိပ်ပါ).", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    if data == "upload_add_character":
        # ensure we have anime in pending state
        st = pending_uploads.get(user.id)
        if not st or not st.get("anime"):
            await query.edit_message_text("⚠️ ပြဿနာ — Anime ကိုရွေးရှာအရင် (Back and choose anime).")
            return
        pending_uploads[user.id]["stage"] = "adding_character"
        await query.edit_message_text("✏️ Send the character name to add for the chosen anime.")
        return

    if data == "upload_back_anime":
        # go back to anime selection
        animes = db_list_animes()
        keyboard = []
        for a in animes:
            keyboard.append([InlineKeyboardButton(a, callback_data=f"upload_choose_anime::{quote_plus(a)}")])
        keyboard.append([InlineKeyboardButton("➕ Add new anime", callback_data="upload_add_anime")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
        pending_uploads[user.id] = {"stage": "anime_select"}
        await query.edit_message_text("🌸 Anime ရွေးပါ — မင်း add လုပ်ချင်တဲ့ anime မ(blank)ရှိရင် ➕ Add new anime ကိုနှိပ်ပါ။", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    m = re.match(r"^upload_choose_character::(.+)$", data)
    if m:
        char = unquote_plus(m.group(1))
        st = pending_uploads.get(user.id) or {}
        anime = st.get("anime")
        # set character and go to rarity
        st.update({"stage": "rarity_select", "character": char})
        pending_uploads[user.id] = st
        # build rarity buttons (from utils)
        keyboard = []
        for rid in sorted(__import__("commands.utils").commands.utils.RARITY.keys()) if False else sorted(__import__("commands.utils").commands.utils.RARITY.keys()):
            pass
        # simpler: use 1..10
        keyboard = []
        for rid in range(1, 11):
            name, pct, emoji = rarity_to_text(rid)
            keyboard.append([InlineKeyboardButton(f"{emoji} {name.capitalize()} ({pct}%)", callback_data=f"upload_rarity::{rid}")])
        keyboard.append([InlineKeyboardButton("⬅️ Back to characters", callback_data=f"upload_back_char")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
        await query.edit_message_text(f"🔖 Selected: *{char}* from *{anime}*\nChoose rarity:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    if data == "upload_back_char":
        st = pending_uploads.get(user.id) or {}
        anime = st.get("anime")
        if not anime:
            await query.edit_message_text("⚠️ No anime selected. Go back and choose anime.")
            return
        chars = db_list_characters(anime)
        keyboard = []
        for c in chars:
            keyboard.append([InlineKeyboardButton(c, callback_data=f"upload_choose_character::{quote_plus(c)}")])
        keyboard.append([InlineKeyboardButton("➕ Add new character", callback_data="upload_add_character")])
        keyboard.append([InlineKeyboardButton("⬅️ Back to anime", callback_data="upload_back_anime")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
        pending_uploads[user.id]["stage"] = "character_select"
        await query.edit_message_text("Select character:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    m = re.match(r"^upload_rarity::(\d+)$", data)
    if m:
        rid = int(m.group(1))
        st = pending_uploads.get(user.id)
        if not st or st.get("stage") not in ("rarity_select",):
            await query.edit_message_text("⚠️ Session expired or wrong stage. Start /upload again.")
            pending_uploads.pop(user.id, None)
            return
        st["rarity"] = rid
        st["stage"] = "awaiting_photo"
        pending_uploads[user.id] = st
        await query.edit_message_text("📷 Good! Now *send the card image/photo* (as photo) to finish upload.", parse_mode="Markdown")
        return

    # fallback
    await query.edit_message_text("Unsupported action or expired session. Start /upload again if needed.")
    pending_uploads.pop(user.id, None)

# text message handler in DM — used for adding new anime/character (and as fallback)
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not chat or chat.type != "private":
        # ignore non-private here
        return

    st = pending_uploads.get(user.id)
    text = (update.message.text or "").strip()
    if not st:
        # no upload ongoing — ignore or tell usage
        return

    # adding new anime
    if st.get("stage") == "adding_anime":
        anime = text
        # set anime and proceed to character selection stage
        pending_uploads[user.id] = {"stage": "character_select", "anime": anime}
        # show character list (likely empty) and Add new character button
        chars = db_list_characters(anime)
        keyboard = []
        for c in chars:
            keyboard.append([InlineKeyboardButton(c, callback_data=f"upload_choose_character::{quote_plus(c)}")])
        keyboard.append([InlineKeyboardButton("➕ Add new character", callback_data="upload_add_character")])
        keyboard.append([InlineKeyboardButton("⬅️ Back to anime", callback_data="upload_back_anime")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
        await update.message.reply_text(f"🎬 Added/selected anime: *{anime}*\nအခု Character ရွေးပါ (If none, add new character).", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    # adding new character
    if st.get("stage") == "adding_character":
        char = text
        st["character"] = char
        st["stage"] = "rarity_select"
        pending_uploads[user.id] = st
        # build rarity buttons
        keyboard = []
        for rid in range(1, 11):
            name, pct, emoji = rarity_to_text(rid)
            keyboard.append([InlineKeyboardButton(f"{emoji} {name.capitalize()} ({pct}%)", callback_data=f"upload_rarity::{rid}")])
        keyboard.append([InlineKeyboardButton("⬅️ Back to characters", callback_data=f"upload_back_char")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")])
        await update.message.reply_text(f"✅ Character set to *{char}*.\nChoose rarity next:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    # fallback: other text during flow
    await update.message.reply_text("⚠️ အဲဒီအဆင့်မှာ စာရိုက်ဖို့ မလိုပါဘူး — buttons နဲ့ရွေးပါ။")

# photo handler finalizes upload
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not chat or chat.type != "private":
        return

    st = pending_uploads.get(user.id)
    if not st or st.get("stage") != "awaiting_photo":
        # not expecting a photo right now
        return

    if not update.message.photo:
        await update.message.reply_text("Please send a photo (as Telegram photo).")
        return

    file_id = update.message.photo[-1].file_id
    st["file_id"] = file_id

    # Save to DB using add_card(anime, character, rarity, file_id, uploader_user_id)
    anime = st.get("anime")
    character = st.get("character")
    rarity = st.get("rarity")
    if not (anime and character and rarity and file_id):
        await update.message.reply_text("⚠️ Missing data in upload flow. Start /upload again.")
        pending_uploads.pop(user.id, None)
        return

    try:
        card_id = add_card(anime, character, rarity, file_id, user.id)
    except Exception as e:
        await update.message.reply_text(f"❌ DB error while saving card: {e}")
        pending_uploads.pop(user.id, None)
        return

    # give uploader the card
    try:
        give_card_to_user(user.id, card_id)
    except Exception:
        # ignore if give logic missing
        pass

    # final message
    name, pct, emoji = rarity_to_text(rarity)
    await update.message.reply_text(
        f"✅ Uploaded!\n🎴 ID: {card_id}\n{emoji} {character}\n🎬 {anime}\n🏷 {name.capitalize()} ({pct}%)"
    )

    # broadcast to groups
    caption = (
        f"🎴 New card uploaded!\n{emoji} {character}\n📌 ID: {card_id}\n"
        f"🎬 Anime: {anime}\n🏷 Rarity: {name.capitalize()} ({pct}%)\nTry to claim it!"
    )
    groups = []
    try:
        groups = get_all_groups()
    except Exception:
        groups = []
    for chat_id in groups:
        try:
            await context.bot.send_photo(chat_id=chat_id, photo=file_id, caption=caption)
        except Exception:
            pass

    pending_uploads.pop(user.id, None)

# register all handlers
def register_handlers(application):
    application.add_handler(CommandHandler("upload", upload_cmd))
    # callback queries for the flow
    application.add_handler(CallbackQueryHandler(callback_router, pattern=r"^upload_"))
    application.add_handler(CallbackQueryHandler(callback_router, pattern=r"^upload_choose_"))
    application.add_handler(CallbackQueryHandler(callback_router, pattern=r"^upload_rarity::\d+$"))
    # text in private for adding anime/character
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, text_handler))
    # photo in private
    application.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE & ~filters.COMMAND, photo_handler))