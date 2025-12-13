# ============================================================
# 📁 File: handlers/catch.py (Part 1 of 2)
# 📍 Location: telegram_card_bot/handlers/catch.py
# 📝 Description: Card catching with auto-reactions
# ============================================================

import asyncio
import random
import hashlib
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, Set, List
from dataclasses import dataclass, field
from collections import defaultdict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.error import TelegramError, BadRequest
from telegram.constants import ChatType, ParseMode

# Try to import ReactionTypeEmoji for auto-reactions
try:
    from telegram import ReactionTypeEmoji
    REACTIONS_AVAILABLE = True
except ImportError:
    REACTIONS_AVAILABLE = False

from config import Config
from db import (
    db,
    ensure_user,
    get_random_card,
    get_card_by_id,
    add_to_collection,
    update_user_stats,
    increment_card_caught,
    ensure_group,
    get_card_count,
    get_all_groups,
    check_user_has_card,
)
from utils.logger import app_logger, error_logger, log_command, log_card_catch
from utils.rarity import (
    get_random_rarity,
    rarity_to_text,
    get_rarity,
    get_catch_reaction,
    should_celebrate,
    get_xp_reward,
    get_coin_reward,
)
from utils.constants import (
    RARITY_EMOJIS,
    RARITY_NAMES,
    PRIMARY_CATCH_REACTION,
    ButtonLabels,
)
from utils.ui import format_catch_message, send_catch_reaction


# ============================================================
# ⚙️ Configuration
# ============================================================

USER_COOLDOWN_SECONDS = 240  # 4 minutes
BATTLE_TIMEOUT_SECONDS = 30
BASE_WIN_CHANCE = 85
WIN_CHANCE_REDUCTION_PER_RARITY = 5

# Anti-cheat
MAX_REQUESTS_PER_SECOND = 2
CHEAT_THRESHOLD = 5
BAN_THRESHOLD = 10


# ============================================================
# 🛡️ Anti-Cheat System
# ============================================================

@dataclass
class CheatRecord:
    """Track suspicious activity."""
    user_id: int
    username: str
    first_name: str
    violations: int = 0
    last_violation: Optional[datetime] = None
    violation_types: List[str] = field(default_factory=list)
    is_banned: bool = False


class AntiCheatSystem:
    """Comprehensive anti-cheat system."""
    
    _instance: Optional["AntiCheatSystem"] = None
    
    def __new__(cls) -> "AntiCheatSystem":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._used_tokens: Set[str] = set()
        self._request_timestamps: Dict[int, list] = defaultdict(list)
        self._cheat_records: Dict[int, CheatRecord] = {}
        self._processed_battles: Set[str] = set()
        self._locks: Dict[int, asyncio.Lock] = {}
        self._initialized = True
    
    def get_user_lock(self, user_id: int) -> asyncio.Lock:
        if user_id not in self._locks:
            self._locks[user_id] = asyncio.Lock()
        return self._locks[user_id]
    
    def generate_token(self, user_id: int, card_id: int, timestamp: float) -> str:
        data = f"{user_id}:{card_id}:{timestamp}:{random.randint(0, 999999)}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def validate_and_consume_token(self, token: str) -> bool:
        if not token or len(token) != 16:
            return False
        if token in self._used_tokens:
            return False
        self._used_tokens.add(token)
        if len(self._used_tokens) > 10000:
            tokens_list = list(self._used_tokens)
            self._used_tokens = set(tokens_list[-5000:])
        return True
    
    def check_rate_limit(self, user_id: int) -> Tuple[bool, int]:
        now = time.time()
        timestamps = self._request_timestamps[user_id]
        timestamps = [t for t in timestamps if now - t < 1.0]
        self._request_timestamps[user_id] = timestamps
        if len(timestamps) >= MAX_REQUESTS_PER_SECOND:
            return False, len(timestamps)
        timestamps.append(now)
        return True, 0
    
    def is_battle_processed(self, user_id: int, token: str) -> bool:
        return f"{user_id}:{token}" in self._processed_battles
    
    def mark_battle_processed(self, user_id: int, token: str) -> None:
        self._processed_battles.add(f"{user_id}:{token}")
        if len(self._processed_battles) > 5000:
            battles_list = list(self._processed_battles)
            self._processed_battles = set(battles_list[-2500:])
    
    def record_violation(self, user_id: int, username: str, first_name: str, violation_type: str) -> CheatRecord:
        if user_id not in self._cheat_records:
            self._cheat_records[user_id] = CheatRecord(
                user_id=user_id,
                username=username or "unknown",
                first_name=first_name or "Unknown"
            )
        record = self._cheat_records[user_id]
        record.violations += 1
        record.last_violation = datetime.now()
        record.violation_types.append(violation_type)
        if record.violations >= BAN_THRESHOLD:
            record.is_banned = True
        error_logger.warning(f"🚨 CHEAT: {user_id} - {violation_type} - Total: {record.violations}")
        return record
    
    def is_user_banned(self, user_id: int) -> bool:
        record = self._cheat_records.get(user_id)
        return record is not None and record.is_banned
    
    def get_cheat_record(self, user_id: int) -> Optional[CheatRecord]:
        return self._cheat_records.get(user_id)
    
    def should_notify_groups(self, user_id: int) -> bool:
        record = self._cheat_records.get(user_id)
        return record is not None and record.violations >= CHEAT_THRESHOLD
    
    def clear_user_record(self, user_id: int) -> None:
        self._cheat_records.pop(user_id, None)


anti_cheat = AntiCheatSystem()


# ============================================================
# 🎲 Battle Helpers
# ============================================================

def calculate_win_chance(rarity_id: int) -> int:
    """Calculate win chance based on rarity."""
    reduction = (rarity_id - 1) * WIN_CHANCE_REDUCTION_PER_RARITY
    return max(20, BASE_WIN_CHANCE - reduction)


def get_difficulty_display(rarity_id: int) -> Tuple[str, str]:
    """Get difficulty text and emoji."""
    chance = calculate_win_chance(rarity_id)
    if chance >= 80:
        return "Easy", "🟢"
    elif chance >= 65:
        return "Medium", "🟡"
    elif chance >= 50:
        return "Hard", "🟠"
    elif chance >= 35:
        return "Very Hard", "🔴"
    else:
        return "Extreme", "💀"


# ============================================================
# 📊 Battle Session Manager
# ============================================================

@dataclass
class BattleSession:
    """Secure battle session."""
    user_id: int
    card_id: int
    card_data: Dict[str, Any]
    message_id: int
    chat_id: int
    token: str
    created_at: datetime = field(default_factory=datetime.now)
    is_completed: bool = False
    
    def is_expired(self) -> bool:
        return (datetime.now() - self.created_at).total_seconds() > BATTLE_TIMEOUT_SECONDS


class CatchManager:
    """Manages cooldowns and battles."""
    
    _instance: Optional["CatchManager"] = None
    
    def __new__(cls) -> "CatchManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._user_cooldowns: Dict[int, datetime] = {}
        self._active_battles: Dict[int, BattleSession] = {}
        self._user_stats: Dict[int, Dict[str, int]] = {}
        self._initialized = True
    
    def check_user_cooldown(self, user_id: int) -> Tuple[bool, int]:
        if user_id not in self._user_cooldowns:
            return False, 0
        last = self._user_cooldowns[user_id]
        elapsed = (datetime.now() - last).total_seconds()
        if elapsed >= USER_COOLDOWN_SECONDS:
            return False, 0
        return True, int(USER_COOLDOWN_SECONDS - elapsed)
    
    def set_user_cooldown(self, user_id: int) -> None:
        self._user_cooldowns[user_id] = datetime.now()
    
    def clear_user_cooldown(self, user_id: int) -> None:
        self._user_cooldowns.pop(user_id, None)
    
    def format_cooldown(self, seconds: int) -> str:
        if seconds >= 60:
            return f"{seconds // 60}m {seconds % 60}s"
        return f"{seconds}s"
    
    def start_battle(self, user_id: int, card_id: int, card_data: Dict, message_id: int, chat_id: int) -> Optional[str]:
        self._cleanup_expired_battles()
        if user_id in self._active_battles:
            existing = self._active_battles[user_id]
            if not existing.is_expired() and not existing.is_completed:
                return None
        
        token = anti_cheat.generate_token(user_id, card_id, time.time())
        self._active_battles[user_id] = BattleSession(
            user_id=user_id,
            card_id=card_id,
            card_data=card_data,
            message_id=message_id,
            chat_id=chat_id,
            token=token
        )
        return token
    
    def get_battle(self, user_id: int) -> Optional[BattleSession]:
        battle = self._active_battles.get(user_id)
        if battle and (battle.is_expired() or battle.is_completed):
            self._active_battles.pop(user_id, None)
            return None
        return battle
    
    def complete_battle(self, user_id: int, won: bool) -> bool:
        battle = self._active_battles.get(user_id)
        if not battle or battle.is_completed:
            return False
        
        battle.is_completed = True
        
        if user_id not in self._user_stats:
            self._user_stats[user_id] = {"wins": 0, "losses": 0, "streak": 0}
        
        stats = self._user_stats[user_id]
        if won:
            stats["wins"] += 1
            stats["streak"] += 1
        else:
            stats["losses"] += 1
            stats["streak"] = 0
        
        self._active_battles.pop(user_id, None)
        return True
    
    def get_user_stats(self, user_id: int) -> Dict[str, int]:
        return self._user_stats.get(user_id, {"wins": 0, "losses": 0, "streak": 0})
    
    def _cleanup_expired_battles(self) -> None:
        expired = [uid for uid, b in self._active_battles.items() if b.is_expired() or b.is_completed]
        for uid in expired:
            self._active_battles.pop(uid, None)


catch_manager = CatchManager()


# ============================================================
# 🎉 Auto-Reaction Helper
# ============================================================

async def send_catch_reaction_safe(message, rarity_id: int) -> bool:
    """
    Send auto-reaction on successful catch.
    Returns True if successful.
    """
    if not REACTIONS_AVAILABLE:
        return False
    
    if not Config.ENABLE_CATCH_REACTIONS:
        return False
    
    try:
        reaction_emoji = get_catch_reaction(rarity_id)
        await message.set_reaction(reaction=[ReactionTypeEmoji(emoji=reaction_emoji)])
        app_logger.debug(f"✨ Reaction sent: {reaction_emoji}")
        return True
    except Exception as e:
        app_logger.debug(f"Could not send reaction: {e}")
        return False


# ============================================================
# 🎴 Main Catch Command
# ============================================================

async def catch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /catch command with anti-cheat and auto-reactions."""
    user = update.effective_user
    chat = update.effective_chat
    message = update.message
    
    if not message or not user:
        return
    
    log_command(user.id, "catch", chat.id)
    
    # Check ban
    if anti_cheat.is_user_banned(user.id):
        await message.reply_text(
            "🚫 *Banned from catching*\n\n"
            "Reason: Cheat detected",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Ensure user exists
    await ensure_user(None, user.id, user.username, user.first_name, user.last_name)
    
    # Private chat - show help
    if chat.type == ChatType.PRIVATE:
        stats = catch_manager.get_user_stats(user.id)
        is_cd, remaining = catch_manager.check_user_cooldown(user.id)
        
        cd_text = f"\n⏳ Cooldown: *{catch_manager.format_cooldown(remaining)}*" if is_cd else ""
        
        await message.reply_text(
            f"⚔️ *Battle Catch*\n\n"
            f"Use `/catch` in a group!\n\n"
            f"*How it works:*\n"
            f"1️⃣ /catch spawns a card\n"
            f"2️⃣ Tap ⚔️ BATTLE\n"
            f"3️⃣ Win = Card is yours! 🏆\n\n"
            f"*Your Stats:*\n"
            f"✅ Wins: {stats['wins']}\n"
            f"❌ Losses: {stats['losses']}\n"
            f"🔥 Streak: {stats['streak']}"
            f"{cd_text}",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Group chat
    await ensure_group(None, chat.id, chat.title)
    
    # Check cooldown
    is_cd, remaining = catch_manager.check_user_cooldown(user.id)
    if is_cd:
        await message.reply_text(
            f"⏳ *Cooldown*\n\n"
            f"Wait: *{catch_manager.format_cooldown(remaining)}*",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Check existing battle
    if catch_manager.get_battle(user.id):
        await message.reply_text(
            "⚔️ *Battle in progress!*\n\nFinish your current battle.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Check cards exist
    total_cards = await get_card_count(None)
    if total_cards == 0:
        await message.reply_text("❌ No cards available!")
        return
    
    # Get random card
    rarity_id = get_random_rarity()
    card = await get_random_card(None, rarity=rarity_id)
    if not card:
        card = await get_random_card(None)
    if not card:
        await message.reply_text("❌ Failed to get card.")
        return
    
    # Extract info
    card_id = card["card_id"]
    character = card["character_name"]
    anime = card["anime"]
    rarity = card["rarity"]
    photo_file_id = card["photo_file_id"]
    
    rarity_name, prob, rarity_emoji = rarity_to_text(rarity)
    win_chance = calculate_win_chance(rarity)
    difficulty, diff_emoji = get_difficulty_display(rarity)
    coin_reward = get_coin_reward(rarity)
    
    # Start battle
    token = catch_manager.start_battle(user.id, card_id, dict(card), 0, chat.id)
    if not token:
        await message.reply_text("❌ Failed to start battle.")
        return
    
    # Set cooldown
    catch_manager.set_user_cooldown(user.id)
    
    # Build message
    caption = (
        f"🎴 *A wild card appeared!*\n\n"
        f"🎬 {anime}\n"
        f"{rarity_emoji} {rarity_name}\n"
        f"💰 {coin_reward:,} coins\n\n"
        f"{diff_emoji} {difficulty} ({win_chance}%)\n"
        f"⏱️ {BATTLE_TIMEOUT_SECONDS}s to battle!\n\n"
        f"👤 [{user.first_name}](tg://user?id={user.id})"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ BATTLE!", callback_data=f"cb_{user.id}_{card_id}_{token}")],
        [InlineKeyboardButton("🏃 Run Away", callback_data=f"cf_{user.id}_{token}")],
    ])
    
    try:
        sent = await message.reply_photo(
            photo=photo_file_id,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        
        # Update message ID
        battle = catch_manager.get_battle(user.id)
        if battle:
            battle.message_id = sent.message_id
        
        app_logger.info(f"🎴 Spawned: {character} ({rarity_emoji}) for {user.first_name}")
        
        # Schedule expiration
        asyncio.create_task(handle_battle_expiration(context, user.id, sent.message_id, chat.id, token, card))
        
    except TelegramError as e:
        error_logger.error(f"Spawn failed: {e}")
        catch_manager.clear_user_cooldown(user.id)
        catch_manager.complete_battle(user.id, won=False)


async def handle_battle_expiration(context, user_id: int, message_id: int, chat_id: int, token: str, card: Dict) -> None:
    """Handle battle timeout."""
    await asyncio.sleep(BATTLE_TIMEOUT_SECONDS)
    
    battle = catch_manager.get_battle(user_id)
    if battle and battle.message_id == message_id and not battle.is_completed:
        catch_manager.complete_battle(user_id, won=False)
        
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except TelegramError:
            try:
                await context.bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption=f"⏳ *Time's up!*\n\n{card['character_name']} escaped...",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=None
                )
            except TelegramError:
                pass