# ============================================================
# 📁 File: handlers/drop.py
# ============================================================

import asyncio, random, re
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from difflib import SequenceMatcher
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from telegram.error import TelegramError
from telegram.constants import ParseMode

try:
    from telegram import ReactionTypeEmoji
    REACTIONS_AVAILABLE = True
except ImportError:
    REACTIONS_AVAILABLE = False

from config import Config
from db import db
from utils.logger import app_logger, error_logger, log_command
from utils.rarity import RARITY_TABLE, get_rarity_emoji, rarity_to_text, get_random_rarity

class TextStyle:
    SMALL_CAPS = {'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ꜰ', 'g': 'ɢ', 'h': 'ʜ', 'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ', 'o': 'ᴏ', 'p': 'ᴘ', 'q': 'ǫ', 'r': 'ʀ', 's': 'ꜱ', 't': 'ᴛ', 'u': 'ᴜ', 'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x', 'y': 'ʏ', 'z': 'ᴢ'}
    SPARKLES = ['✦', '✧', '★', '☆', '✴', '✵', '❋', '❊']
    HEARTS = ['♡', '♥', '❤', '💕', '💖', '💗', '💝']
    
    @classmethod
    def to_small_caps(cls, text: str) -> str:
        return ''.join(cls.SMALL_CAPS.get(c.lower(), c) for c in text)
    
    @classmethod
    def sparkle(cls) -> str:
        return random.choice(cls.SPARKLES)
    
    @classmethod
    def heart(cls) -> str:
        return random.choice(cls.HEARTS)

DEFAULT_DROP_THRESHOLD = 50
MIN_DROP_THRESHOLD = 10
MAX_DROP_THRESHOLD = 500
DROP_TIMEOUT = 300

CATCH_REACTIONS = {"common": ["👍", "🎉"], "rare": ["🔥", "⭐", "🎉"], "epic": ["🔥", "💯", "⭐", "🎊"], "legendary": ["🔥", "💯", "❤️", "🏆", "💎"], "mythic": ["🔥", "💯", "❤️", "🏆", "💎", "🎉"]}

active_drops: Dict[int, Dict[str, Any]] = {}
message_counters: Dict[int, int] = {}

async def get_group_drop_settings(group_id: int) -> Dict[str, Any]:
    try:
        row = await db.fetchrow("SELECT drop_threshold, drop_enabled, message_count, last_drop_at FROM groups WHERE group_id = $1", group_id)
        if row:
            return {"threshold": row.get("drop_threshold") or DEFAULT_DROP_THRESHOLD, "enabled": row.get("drop_enabled", True), "message_count": row.get("message_count") or 0, "last_drop_at": row.get("last_drop_at")}
        return {"threshold": DEFAULT_DROP_THRESHOLD, "enabled": True, "message_count": 0, "last_drop_at": None}
    except Exception as e:
        error_logger.error(f"Failed to get group drop settings: {e}")
        return {"threshold": DEFAULT_DROP_THRESHOLD, "enabled": True, "message_count": 0, "last_drop_at": None}

async def set_group_drop_threshold(group_id: int, threshold: int) -> bool:
    try:
        await db.execute("INSERT INTO groups (group_id, drop_threshold, drop_enabled, message_count) VALUES ($1, $2, TRUE, 0) ON CONFLICT (group_id) DO UPDATE SET drop_threshold = $2", group_id, threshold)
        return True
    except Exception as e:
        error_logger.error(f"Failed to set drop threshold: {e}")
        return False

async def increment_message_count(group_id: int) -> int:
    try:
        result = await db.fetchval("INSERT INTO groups (group_id, message_count, drop_enabled) VALUES ($1, 1, TRUE) ON CONFLICT (group_id) DO UPDATE SET message_count = COALESCE(groups.message_count, 0) + 1 RETURNING message_count", group_id)
        message_counters[group_id] = result or 1
        return result or 1
    except Exception as e:
        error_logger.error(f"Failed to increment message count: {e}")
        message_counters[group_id] = message_counters.get(group_id, 0) + 1
        return message_counters[group_id]

async def reset_message_count(group_id: int) -> bool:
    try:
        await db.execute("UPDATE groups SET message_count = 0, last_drop_at = NOW() WHERE group_id = $1", group_id)
        message_counters[group_id] = 0
        return True
    except Exception as e:
        error_logger.error(f"Failed to reset message count: {e}")
        return False

async def get_random_card_for_drop() -> Optional[Dict[str, Any]]:
    try:
        rarity = get_random_rarity()
        card = await db.fetchrow("SELECT card_id, character_name, anime, rarity, photo_file_id FROM cards WHERE rarity = $1 AND is_active = TRUE ORDER BY RANDOM() LIMIT 1", rarity)
        if not card:
            card = await db.fetchrow("SELECT card_id, character_name, anime, rarity, photo_file_id FROM cards WHERE is_active = TRUE ORDER BY RANDOM() LIMIT 1")
        return dict(card) if card else None
    except Exception as e:
        error_logger.error(f"Failed to get random card: {e}")
        return None

async def record_catch(user_id: int, card_id: int, group_id: int, username: Optional[str] = None, first_name: Optional[str] = None) -> bool:
    try:
        await db.execute("INSERT INTO users (user_id, username, first_name) VALUES ($1, $2, $3) ON CONFLICT (user_id) DO UPDATE SET username = COALESCE($2, users.username), first_name = COALESCE($3, users.first_name)", user_id, username, first_name)
        await db.execute("INSERT INTO collections (user_id, card_id, caught_at, caught_in_group) VALUES ($1, $2, NOW(), $3)", user_id, card_id, group_id)
        await db.execute("UPDATE users SET total_catches = COALESCE(total_catches, 0) + 1 WHERE user_id = $1", user_id)
        await db.execute("UPDATE groups SET total_catches = COALESCE(total_catches, 0) + 1 WHERE group_id = $1", group_id)
        return True
    except Exception as e:
        error_logger.error(f"Failed to record catch: {e}")
        return False

async def ensure_group_exists(group_id: int, group_name: Optional[str] = None) -> bool:
    try:
        await db.execute("INSERT INTO groups (group_id, group_name, drop_enabled, message_count) VALUES ($1, $2, TRUE, 0) ON CONFLICT (group_id) DO UPDATE SET group_name = COALESCE($2, groups.group_name)", group_id, group_name)
        return True
    except Exception as e:
        error_logger.error(f"Failed to ensure group exists: {e}")
        return False

def normalize_name(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(r'[^\w\s]', '', name)
    name = re.sub(r'\s+', ' ', name)
    return name

def calculate_similarity(name1: str, name2: str) -> float:
    norm1, norm2 = normalize_name(name1), normalize_name(name2)
    if norm1 == norm2:
        return 1.0
    return SequenceMatcher(None, norm1, norm2).ratio()

def check_name_match(guess: str, actual_name: str, threshold: float = 0.75) -> Tuple[bool, float]:
    guess, actual = guess.strip(), actual_name.strip()
    full_similarity = calculate_similarity(guess, actual)
    if full_similarity >= threshold:
        return True, full_similarity
    first_name = actual.split()[0] if actual else ""
    first_similarity = calculate_similarity(guess, first_name)
    if first_similarity >= 0.85:
        return True, first_similarity
    norm_guess, norm_actual = normalize_name(guess), normalize_name(actual)
    if len(norm_guess) >= 3 and norm_guess in norm_actual:
        return True, 0.80
    return False, max(full_similarity, first_similarity)

def get_rarity_tier(rarity: int) -> str:
    if rarity >= 10: return "mythic"
    elif rarity >= 8: return "legendary"
    elif rarity >= 6: return "epic"
    elif rarity >= 4: return "rare"
    return "common"

def get_catch_reaction(rarity: int) -> str:
    tier = get_rarity_tier(rarity)
    return random.choice(CATCH_REACTIONS.get(tier, CATCH_REACTIONS["common"]))

def format_group_name(name: Optional[str]) -> str:
    if not name: return "ᴛʜɪꜱ ɢʀᴏᴜᴘ"
    return name[:22] + "..." if len(name) > 25 else name

def create_drop_caption(rarity: int, group_name: str) -> str:
    rarity_emoji = get_rarity_emoji(rarity)
    rarity_name, _, _ = rarity_to_text(rarity)
    styled_group = format_group_name(group_name)
    return (f"{rarity_emoji} {TextStyle.sparkle()} {TextStyle.to_small_caps('a character has appeared')} {TextStyle.sparkle()} {rarity_emoji}\n\n"
            f"╭─────────────────────────╮\n│  {TextStyle.to_small_caps('in')} *{styled_group}*\n╰─────────────────────────╯\n\n"
            f"{TextStyle.heart()} {TextStyle.to_small_caps('capture them and give your')}\n    {TextStyle.to_small_caps('harem some aura with')}\n\n"
            f"    `/lulucatch <name>`\n\n╭───── ⋆ ✦ ⋆ ─────╮\n│  ✨ *{rarity_name}* ✨\n╰───── ⋆ ✦ ⋆ ─────╯")

def create_catch_success_message(user_name: str, user_id: int, character_name: str, anime: str, rarity: int, is_new: bool = True) -> str:
    rarity_emoji = get_rarity_emoji(rarity)
    rarity_name, _, _ = rarity_to_text(rarity)
    tier = get_rarity_tier(rarity)
    if tier in ["legendary", "mythic"]:
        border, sparkle = "═" * 25, "💎✨🌟"
    elif tier == "epic":
        border, sparkle = "─" * 25, "⭐✨"
    else:
        border, sparkle = "─" * 25, "✨"
    new_badge = "  🆕 *ɴᴇᴡ ᴄᴀʀᴅ!*" if is_new else ""
    return (f"{sparkle} *ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟ ᴄᴀᴛᴄʜ!* {sparkle}\n╭{border}╮\n\n"
            f"   👤 [{user_name}](tg://user?id={user_id})\n   {TextStyle.to_small_caps('has captured')}\n\n"
            f"   🎴 *{character_name}*\n   📺 _{anime}_\n   {rarity_emoji} *{rarity_name}*{new_badge}\n\n"
            f"╰{border}╯\n\n   {TextStyle.heart()} {TextStyle.to_small_caps('added to your harem')} {TextStyle.heart()}")

def create_already_caught_message(catcher_name: str, catcher_id: int, character_name: str) -> str:
    return f"⚡ *ᴛᴏᴏ ꜱʟᴏᴡ!*\n\n[{catcher_name}](tg://user?id={catcher_id}) {TextStyle.to_small_caps('already caught')} *{character_name}*!\n\n💨 {TextStyle.to_small_caps('be faster next time')}..."

def create_wrong_guess_message(similarity: float) -> str:
    if similarity >= 0.5: return f"🤏 {TextStyle.to_small_caps('so close! try again')}..."
    elif similarity >= 0.3: return f"🤔 {TextStyle.to_small_caps('not quite right')}..."
    return f"❌ {TextStyle.to_small_caps('wrong character name')}"

async def setdrop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, chat = update.effective_user, update.effective_chat
    log_command(user.id, "setdrop", chat.id)
    if not Config.is_admin(user.id):
        await update.message.reply_text(f"❌ {TextStyle.to_small_caps('only bot owner can use this command')}", parse_mode=ParseMode.MARKDOWN)
        return
    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text(f"❌ {TextStyle.to_small_caps('this command only works in groups')}", parse_mode=ParseMode.MARKDOWN)
        return
    if not context.args:
        settings = await get_group_drop_settings(chat.id)
        await update.message.reply_text(f"⚙️ *ᴅʀᴏᴘ ꜱᴇᴛᴛɪɴɢꜱ*\n\n╭─────────────────────────╮\n│  📊 *ᴄᴜʀʀᴇɴᴛ ᴛʜʀᴇꜱʜᴏʟᴅ:* `{settings['threshold']}`\n│  💬 *ᴍᴇꜱꜱᴀɢᴇ ᴄᴏᴜɴᴛ:* `{settings['message_count']}`\n│  ✅ *ᴇɴᴀʙʟᴇᴅ:* `{settings['enabled']}`\n╰─────────────────────────╯\n\n📝 *ᴜꜱᴀɢᴇ:* `/setdrop <amount>`\n📌 *ᴇxᴀᴍᴘʟᴇ:* `/setdrop 50`\n\n_{TextStyle.to_small_caps('range')}: {MIN_DROP_THRESHOLD} - {MAX_DROP_THRESHOLD}_", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        threshold = int(context.args[0])
    except ValueError:
        await update.message.reply_text(f"❌ {TextStyle.to_small_caps('please provide a valid number')}", parse_mode=ParseMode.MARKDOWN)
        return
    if threshold < MIN_DROP_THRESHOLD or threshold > MAX_DROP_THRESHOLD:
        await update.message.reply_text(f"❌ {TextStyle.to_small_caps('threshold must be between')} `{MIN_DROP_THRESHOLD}` {TextStyle.to_small_caps('and')} `{MAX_DROP_THRESHOLD}`", parse_mode=ParseMode.MARKDOWN)
        return
    await ensure_group_exists(chat.id, chat.title)
    if await set_group_drop_threshold(chat.id, threshold):
        await update.message.reply_text(f"✅ *ᴅʀᴏᴘ ᴛʜʀᴇꜱʜᴏʟᴅ ᴜᴘᴅᴀᴛᴇᴅ!*\n\n╭─────────────────────────╮\n│  🎯 *ɴᴇᴡ ᴛʜʀᴇꜱʜᴏʟᴅ:* `{threshold}` ᴍꜱɢꜱ\n╰─────────────────────────╯\n\n✨ {TextStyle.to_small_caps('a card will drop every')} `{threshold}` {TextStyle.to_small_caps('messages')}!", parse_mode=ParseMode.MARKDOWN)
        app_logger.info(f"⚙️ Drop threshold set to {threshold} in group {chat.id} by {user.id}")
    else:
        await update.message.reply_text(f"❌ {TextStyle.to_small_caps('failed to update settings. please try again.')}", parse_mode=ParseMode.MARKDOWN)

async def droptime_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, chat = update.effective_user, update.effective_chat
    log_command(user.id, "droptime", chat.id)
    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text(f"❌ {TextStyle.to_small_caps('this command only works in groups')}", parse_mode=ParseMode.MARKDOWN)
        return
    settings = await get_group_drop_settings(chat.id)
    threshold, current = settings["threshold"], settings["message_count"]
    remaining = max(0, threshold - current)
    progress = min(100, int((current / threshold) * 100)) if threshold > 0 else 0
    filled, empty = int(progress / 10), 10 - int(progress / 10)
    progress_bar = "▓" * filled + "░" * empty
    active_drop = active_drops.get(chat.id)
    active_status = f"\n\n🚨 *ᴀᴄᴛɪᴠᴇ ᴅʀᴏᴘ!*\n   {TextStyle.to_small_caps('a character is waiting to be caught')}!\n   {TextStyle.to_small_caps('use')} `/lulucatch <name>`" if active_drop and not active_drop.get("caught_by") else ""
    await update.message.reply_text(f"⏱️ *ᴅʀᴏᴘ ꜱᴛᴀᴛᴜꜱ*\n\n╭─────────────────────────╮\n│  📊 *ᴘʀᴏɢʀᴇꜱꜱ:* {progress}%\n│  [{progress_bar}]\n│\n│  💬 *ᴍᴇꜱꜱᴀɢᴇꜱ:* `{current}` / `{threshold}`\n│  ⏳ *ʀᴇᴍᴀɪɴɪɴɢ:* `{remaining}` ᴍꜱɢꜱ\n╰─────────────────────────╯{active_status}\n\n💡 _{TextStyle.to_small_caps('keep chatting to trigger a drop')}!_", parse_mode=ParseMode.MARKDOWN)

async def spawn_card_drop(context: ContextTypes.DEFAULT_TYPE, chat_id: int, chat_title: Optional[str] = None) -> bool:
    try:
        if chat_id in active_drops:
            spawned_at = active_drops[chat_id].get("spawned_at")
            if spawned_at and (datetime.now() - spawned_at).seconds < DROP_TIMEOUT:
                return False
            del active_drops[chat_id]
        card = await get_random_card_for_drop()
        if not card:
            error_logger.warning(f"No cards available for drop in group {chat_id}")
            return False
        rarity, caption = card["rarity"], create_drop_caption(card["rarity"], chat_title)
        photo_file_id = card.get("photo_file_id")
        if not photo_file_id:
            error_logger.warning(f"Card {card['card_id']} has no photo_file_id")
            return False
        message = await context.bot.send_photo(chat_id=chat_id, photo=photo_file_id, caption=caption, parse_mode=ParseMode.MARKDOWN, has_spoiler=True)
        active_drops[chat_id] = {"card": card, "message_id": message.message_id, "spawned_at": datetime.now(), "caught_by": None}
        await reset_message_count(chat_id)
        app_logger.info(f"🎴 Card dropped in group {chat_id}: {card['character_name']} ({card['card_id']}) - Rarity: {rarity}")
        return True
    except TelegramError as e:
        error_logger.error(f"Failed to spawn card drop: {e}")
        return False
    except Exception as e:
        error_logger.error(f"Unexpected error in spawn_card_drop: {e}", exc_info=True)
        return False

async def lulucatch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, chat, message = update.effective_user, update.effective_chat, update.message
    log_command(user.id, "lulucatch", chat.id)
    if chat.type not in ["group", "supergroup"]:
        await message.reply_text(f"❌ {TextStyle.to_small_caps('this command only works in groups')}", parse_mode=ParseMode.MARKDOWN)
        return
    drop = active_drops.get(chat.id)
    if not drop:
        await message.reply_text(f"❌ {TextStyle.to_small_caps('no active drop right now')}!\n\n💡 {TextStyle.to_small_caps('wait for a character to appear')}...", parse_mode=ParseMode.MARKDOWN)
        return
    if drop.get("caught_by"):
        catcher = drop["caught_by"]
        await message.reply_text(create_already_caught_message(catcher["first_name"], catcher["user_id"], drop["card"]["character_name"]), parse_mode=ParseMode.MARKDOWN)
        return
    spawned_at = drop.get("spawned_at")
    if spawned_at and (datetime.now() - spawned_at).seconds >= DROP_TIMEOUT:
        del active_drops[chat.id]
        await message.reply_text(f"⏰ {TextStyle.to_small_caps('this drop has expired')}!\n\n💨 {TextStyle.to_small_caps('the character ran away')}...", parse_mode=ParseMode.MARKDOWN)
        return
    if not context.args:
        await message.reply_text(f"❌ {TextStyle.to_small_caps('please provide the character name')}!\n\n📝 *ᴜꜱᴀɢᴇ:* `/lulucatch <character name>`\n📌 *ᴇxᴀᴍᴘʟᴇ:* `/lulucatch Yumeko`", parse_mode=ParseMode.MARKDOWN)
        return
    guess, actual_name = " ".join(context.args).strip(), drop["card"]["character_name"]
    is_match, similarity = check_name_match(guess, actual_name)
    if not is_match:
        await message.reply_text(create_wrong_guess_message(similarity), parse_mode=ParseMode.MARKDOWN)
        return
    card = drop["card"]
    card_id, character_name, anime, rarity = card["card_id"], card["character_name"], card["anime"], card["rarity"]
    drop["caught_by"] = {"user_id": user.id, "first_name": user.first_name}
    if not await record_catch(user_id=user.id, card_id=card_id, group_id=chat.id, username=user.username, first_name=user.first_name):
        await message.reply_text(f"❌ {TextStyle.to_small_caps('error saving catch. please try again.')}", parse_mode=ParseMode.MARKDOWN)
        drop["caught_by"] = None
        return
    existing = await db.fetchval("SELECT COUNT(*) FROM collections WHERE user_id = $1 AND card_id = $2", user.id, card_id)
    is_new = (existing == 1)
    await message.reply_text(create_catch_success_message(user_name=user.first_name, user_id=user.id, character_name=character_name, anime=anime, rarity=rarity, is_new=is_new), parse_mode=ParseMode.MARKDOWN)
    if REACTIONS_AVAILABLE:
        try:
            await message.set_reaction(reaction=[ReactionTypeEmoji(emoji=get_catch_reaction(rarity))])
        except Exception as e:
            app_logger.debug(f"Could not set reaction: {e}")
    try:
        rarity_emoji = get_rarity_emoji(rarity)
        await context.bot.edit_message_caption(chat_id=chat.id, message_id=drop["message_id"], caption=f"{rarity_emoji} *ᴄᴀᴜɢʜᴛ!* {rarity_emoji}\n\n╭─────────────────────────╮\n│  🎴 *{character_name}*\n│  📺 _{anime}_\n│\n│  👤 ᴄᴀᴜɢʜᴛ ʙʏ:\n│  [{user.first_name}](tg://user?id={user.id})\n╰─────────────────────────╯", parse_mode=ParseMode.MARKDOWN)
    except TelegramError as e:
        app_logger.debug(f"Could not edit drop message: {e}")
    async def cleanup_drop():
        await asyncio.sleep(30)
        if chat.id in active_drops and active_drops[chat.id].get("caught_by"):
            del active_drops[chat.id]
    asyncio.create_task(cleanup_drop())
    app_logger.info(f"🎯 {user.first_name} ({user.id}) caught {character_name} (Card ID: {card_id}, Rarity: {rarity}) in group {chat.id}")

async def forcedrop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, chat = update.effective_user, update.effective_chat
    log_command(user.id, "forcedrop", chat.id)
    if not Config.is_admin(user.id):
        await update.message.reply_text(f"❌ {TextStyle.to_small_caps('only bot owner can use this command')}", parse_mode=ParseMode.MARKDOWN)
        return
    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text(f"❌ {TextStyle.to_small_caps('this command only works in groups')}", parse_mode=ParseMode.MARKDOWN)
        return
    if chat.id in active_drops and not active_drops[chat.id].get("caught_by"):
        await update.message.reply_text(f"⚠️ {TextStyle.to_small_caps('there is already an active drop')}!\n\n💡 {TextStyle.to_small_caps('use')} `/cleardrop` {TextStyle.to_small_caps('to remove it first')}.", parse_mode=ParseMode.MARKDOWN)
        return
    await update.message.reply_text(f"🎲 {TextStyle.to_small_caps('forcing a drop')}...", parse_mode=ParseMode.MARKDOWN)
    if not await spawn_card_drop(context, chat.id, chat.title):
        await update.message.reply_text(f"❌ {TextStyle.to_small_caps('failed to spawn drop. check if cards exist in database.')}", parse_mode=ParseMode.MARKDOWN)
    else:
        app_logger.info(f"🎲 Force drop triggered by admin {user.id} in group {chat.id}")

async def cleardrop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, chat = update.effective_user, update.effective_chat
    log_command(user.id, "cleardrop", chat.id)
    if not Config.is_admin(user.id):
        await update.message.reply_text(f"❌ {TextStyle.to_small_caps('only bot owner can use this command')}", parse_mode=ParseMode.MARKDOWN)
        return
    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text(f"❌ {TextStyle.to_small_caps('this command only works in groups')}", parse_mode=ParseMode.MARKDOWN)
        return
    if chat.id not in active_drops:
        await update.message.reply_text(f"❌ {TextStyle.to_small_caps('no active drop to clear')}", parse_mode=ParseMode.MARKDOWN)
        return
    del active_drops[chat.id]
    await update.message.reply_text(f"✅ {TextStyle.to_small_caps('active drop cleared')}!", parse_mode=ParseMode.MARKDOWN)
    app_logger.info(f"🗑️ Drop cleared by admin {user.id} in group {chat.id}")

async def dropstats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, chat = update.effective_user, update.effective_chat
    log_command(user.id, "dropstats", chat.id)
    if not Config.is_admin(user.id):
        await update.message.reply_text(f"❌ {TextStyle.to_small_caps('only bot owner can use this command')}", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        groups = await db.fetch("SELECT group_id, group_name, drop_threshold, message_count, total_catches, total_spawns, drop_enabled FROM groups WHERE drop_enabled = TRUE ORDER BY total_catches DESC LIMIT 10")
    except Exception as e:
        error_logger.error(f"Failed to get drop stats: {e}")
        await update.message.reply_text(f"❌ {TextStyle.to_small_caps('failed to fetch statistics')}", parse_mode=ParseMode.MARKDOWN)
        return
    if not groups:
        await update.message.reply_text(f"📊 {TextStyle.to_small_caps('no groups with drop system active')}", parse_mode=ParseMode.MARKDOWN)
        return
    stats_lines = []
    for i, g in enumerate(groups, 1):
        name = (g["group_name"] or "Unknown")[:12] + "..." if len(g["group_name"] or "Unknown") > 15 else (g["group_name"] or "Unknown")
        stats_lines.append(f"{i}. *{name}*\n    🎯 `{g['total_catches'] or 0}` ᴄᴀᴛᴄʜᴇꜱ │ 💬 `{g['message_count'] or 0}`/`{g['drop_threshold'] or DEFAULT_DROP_THRESHOLD}`")
    active_count = len([d for d in active_drops.values() if not d.get("caught_by")])
    await update.message.reply_text(f"📊 *ᴅʀᴏᴘ ꜱʏꜱᴛᴇᴍ ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ*\n\n╭─────────────────────────╮\n│  🌐 *ᴀᴄᴛɪᴠᴇ ɢʀᴏᴜᴘꜱ:* `{len(groups)}`\n│  🎴 *ᴀᴄᴛɪᴠᴇ ᴅʀᴏᴘꜱ:* `{active_count}`\n╰─────────────────────────╯\n\n🏆 *ᴛᴏᴘ ɢʀᴏᴜᴘꜱ ʙʏ ᴄᴀᴛᴄʜᴇꜱ:*\n\n" + "\n\n".join(stats_lines), parse_mode=ParseMode.MARKDOWN)

async def message_counter_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or update.effective_chat.type not in ["group", "supergroup"]:
        return
    if update.effective_user and update.effective_user.is_bot:
        return
    if update.message and update.message.text and update.message.text.startswith('/'):
        return
    chat = update.effective_chat
    try:
        await ensure_group_exists(chat.id, chat.title)
        new_count = await increment_message_count(chat.id)
        settings = await get_group_drop_settings(chat.id)
        if new_count >= settings["threshold"]:
            if await spawn_card_drop(context, chat.id, chat.title):
                app_logger.info(f"🎴 Auto-drop triggered in group {chat.id} (messages: {new_count}/{settings['threshold']})")
    except Exception as e:
        error_logger.error(f"Error in message counter: {e}", exc_info=True)

setdrop_handler = CommandHandler("setdrop", setdrop_command)
droptime_handler = CommandHandler("droptime", droptime_command)
lulucatch_handler = CommandHandler("lulucatch", lulucatch_command)
forcedrop_handler = CommandHandler("forcedrop", forcedrop_command)
cleardrop_handler = CommandHandler("cleardrop", cleardrop_command)
dropstats_handler = CommandHandler("dropstats", dropstats_command)
message_counter = MessageHandler(filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, message_counter_handler)

drop_handlers = [setdrop_handler, droptime_handler, lulucatch_handler, forcedrop_handler, cleardrop_handler, dropstats_handler, message_counter]