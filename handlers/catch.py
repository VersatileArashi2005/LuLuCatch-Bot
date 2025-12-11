# ============================================================
# 📁 File: handlers/catch.py
# 📍 Location: telegram_card_bot/handlers/catch.py
# 📝 Description: Secure card catching system with anti-cheat
# ============================================================

import asyncio
import random
import hashlib
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, Set
from dataclasses import dataclass, field
from collections import defaultdict

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from telegram.error import TelegramError, BadRequest
from telegram.constants import ChatType

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
)
from utils.logger import app_logger, error_logger, log_command, log_card_catch
from utils.rarity import (
    get_random_rarity,
    rarity_to_text,
    get_rarity_emoji,
    calculate_rarity_value,
    RARITY_TABLE,
)


# ============================================================
# ⚙️ Configuration Constants
# ============================================================

USER_COOLDOWN_SECONDS = 240  # 4 minutes per user
BATTLE_TIMEOUT_SECONDS = 30  # Time to click battle
BASE_WIN_CHANCE = 85
WIN_CHANCE_REDUCTION_PER_RARITY = 5

# Anti-cheat settings
MAX_REQUESTS_PER_SECOND = 2  # Rate limit
CHEAT_THRESHOLD = 5  # Suspicious actions before flagging
BAN_THRESHOLD = 10  # Actions before auto-ban from catching


# ============================================================
# 🛡️ Anti-Cheat System
# ============================================================

@dataclass
class CheatRecord:
    """Track suspicious activity for a user."""
    user_id: int
    username: str
    first_name: str
    violations: int = 0
    last_violation: Optional[datetime] = None
    violation_types: list = field(default_factory=list)
    is_banned: bool = False


class AntiCheatSystem:
    """
    Comprehensive anti-cheat system.
    
    Detects and prevents:
    - Button spam attacks
    - Token reuse attempts
    - Race condition exploits
    - Duplicate card attempts
    """
    
    _instance: Optional["AntiCheatSystem"] = None
    
    def __new__(cls) -> "AntiCheatSystem":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # Used tokens (one-time use)
        self._used_tokens: Set[str] = set()
        
        # Rate limiting: {user_id: [timestamps]}
        self._request_timestamps: Dict[int, list] = defaultdict(list)
        
        # Cheat records: {user_id: CheatRecord}
        self._cheat_records: Dict[int, CheatRecord] = {}
        
        # Processed battles (prevent duplicates)
        self._processed_battles: Set[str] = set()
        
        # Lock for thread safety
        self._locks: Dict[int, asyncio.Lock] = {}
        
        self._initialized = True
    
    def get_user_lock(self, user_id: int) -> asyncio.Lock:
        """Get or create a lock for a specific user."""
        if user_id not in self._locks:
            self._locks[user_id] = asyncio.Lock()
        return self._locks[user_id]
    
    def generate_token(self, user_id: int, card_id: int, timestamp: float) -> str:
        """Generate a unique one-time battle token."""
        data = f"{user_id}:{card_id}:{timestamp}:{random.randint(0, 999999)}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def validate_and_consume_token(self, token: str) -> bool:
        """
        Validate a token and mark it as used.
        Returns True if valid, False if already used or invalid.
        """
        if not token or len(token) != 16:
            return False
        
        if token in self._used_tokens:
            return False
        
        self._used_tokens.add(token)
        
        # Cleanup old tokens (keep last 10000)
        if len(self._used_tokens) > 10000:
            # Remove oldest tokens
            tokens_list = list(self._used_tokens)
            self._used_tokens = set(tokens_list[-5000:])
        
        return True
    
    def check_rate_limit(self, user_id: int) -> Tuple[bool, int]:
        """
        Check if user is within rate limits.
        Returns (is_allowed, violations_count).
        """
        now = time.time()
        timestamps = self._request_timestamps[user_id]
        
        # Remove timestamps older than 1 second
        timestamps = [t for t in timestamps if now - t < 1.0]
        self._request_timestamps[user_id] = timestamps
        
        if len(timestamps) >= MAX_REQUESTS_PER_SECOND:
            return False, len(timestamps)
        
        timestamps.append(now)
        return True, 0
    
    def is_battle_processed(self, user_id: int, token: str) -> bool:
        """Check if this specific battle was already processed."""
        battle_key = f"{user_id}:{token}"
        return battle_key in self._processed_battles
    
    def mark_battle_processed(self, user_id: int, token: str) -> None:
        """Mark a battle as processed to prevent duplicates."""
        battle_key = f"{user_id}:{token}"
        self._processed_battles.add(battle_key)
        
        # Cleanup old entries
        if len(self._processed_battles) > 5000:
            battles_list = list(self._processed_battles)
            self._processed_battles = set(battles_list[-2500:])
    
    def record_violation(
        self,
        user_id: int,
        username: str,
        first_name: str,
        violation_type: str
    ) -> CheatRecord:
        """Record a cheat violation for a user."""
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
        
        # Auto-ban if threshold exceeded
        if record.violations >= BAN_THRESHOLD:
            record.is_banned = True
        
        error_logger.warning(
            f"🚨 CHEAT DETECTED: User {user_id} (@{username}) - "
            f"Type: {violation_type} - Total violations: {record.violations}"
        )
        
        return record
    
    def is_user_banned(self, user_id: int) -> bool:
        """Check if user is banned from catching."""
        record = self._cheat_records.get(user_id)
        return record is not None and record.is_banned
    
    def get_cheat_record(self, user_id: int) -> Optional[CheatRecord]:
        """Get cheat record for a user."""
        return self._cheat_records.get(user_id)
    
    def should_notify_groups(self, user_id: int) -> bool:
        """Check if we should broadcast a cheater alert."""
        record = self._cheat_records.get(user_id)
        if not record:
            return False
        return record.violations >= CHEAT_THRESHOLD
    
    def clear_user_record(self, user_id: int) -> None:
        """Admin: Clear a user's cheat record."""
        self._cheat_records.pop(user_id, None)


# Global anti-cheat instance
anti_cheat = AntiCheatSystem()


# ============================================================
# 🎲 Win Chance Calculator
# ============================================================

def calculate_win_chance(rarity_id: int) -> int:
    """Calculate win chance based on rarity."""
    reduction = (rarity_id - 1) * WIN_CHANCE_REDUCTION_PER_RARITY
    return max(20, BASE_WIN_CHANCE - reduction)


def get_difficulty_text(rarity_id: int) -> Tuple[str, str]:
    """Get difficulty description."""
    win_chance = calculate_win_chance(rarity_id)
    
    if win_chance >= 80:
        return "Easy", "🟢"
    elif win_chance >= 65:
        return "Medium", "🟡"
    elif win_chance >= 50:
        return "Hard", "🟠"
    elif win_chance >= 35:
        return "Very Hard", "🔴"
    else:
        return "Extreme", "💀"


# ============================================================
# 📊 Battle Session Manager
# ============================================================

@dataclass
class BattleSession:
    """Secure battle session with one-time token."""
    user_id: int
    card_id: int
    card_data: Dict[str, Any]
    message_id: int
    chat_id: int
    token: str  # One-time use token
    created_at: datetime = field(default_factory=datetime.now)
    is_completed: bool = False
    
    def is_expired(self) -> bool:
        elapsed = (datetime.now() - self.created_at).total_seconds()
        return elapsed > BATTLE_TIMEOUT_SECONDS


class CatchManager:
    """Manages cooldowns and battle sessions."""
    
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
        """Check user cooldown."""
        if user_id not in self._user_cooldowns:
            return False, 0
        
        last_catch = self._user_cooldowns[user_id]
        elapsed = (datetime.now() - last_catch).total_seconds()
        
        if elapsed >= USER_COOLDOWN_SECONDS:
            return False, 0
        
        return True, int(USER_COOLDOWN_SECONDS - elapsed)
    
    def set_user_cooldown(self, user_id: int) -> None:
        """Set cooldown for user."""
        self._user_cooldowns[user_id] = datetime.now()
    
    def clear_user_cooldown(self, user_id: int) -> None:
        """Clear user cooldown."""
        self._user_cooldowns.pop(user_id, None)
    
    def format_cooldown(self, seconds: int) -> str:
        """Format cooldown time."""
        if seconds >= 60:
            return f"{seconds // 60}m {seconds % 60}s"
        return f"{seconds}s"
    
    def start_battle(
        self,
        user_id: int,
        card_id: int,
        card_data: Dict[str, Any],
        message_id: int,
        chat_id: int
    ) -> Optional[str]:
        """
        Start a new battle session.
        Returns the unique token or None if failed.
        """
        # Clean expired battles
        self._cleanup_expired_battles()
        
        # Check for existing active battle
        if user_id in self._active_battles:
            existing = self._active_battles[user_id]
            if not existing.is_expired() and not existing.is_completed:
                return None
        
        # Generate unique token
        token = anti_cheat.generate_token(user_id, card_id, time.time())
        
        # Create session
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
        """Get active battle session."""
        battle = self._active_battles.get(user_id)
        
        if battle and (battle.is_expired() or battle.is_completed):
            self._active_battles.pop(user_id, None)
            return None
        
        return battle
    
    def complete_battle(self, user_id: int, won: bool) -> bool:
        """
        Complete a battle and update stats.
        Returns True if successful, False if already completed.
        """
        battle = self._active_battles.get(user_id)
        
        if not battle:
            return False
        
        if battle.is_completed:
            return False
        
        # Mark as completed
        battle.is_completed = True
        
        # Update stats
        if user_id not in self._user_stats:
            self._user_stats[user_id] = {"wins": 0, "losses": 0, "streak": 0}
        
        stats = self._user_stats[user_id]
        
        if won:
            stats["wins"] += 1
            stats["streak"] += 1
        else:
            stats["losses"] += 1
            stats["streak"] = 0
        
        # Remove from active battles
        self._active_battles.pop(user_id, None)
        
        return True
    
    def get_user_stats(self, user_id: int) -> Dict[str, int]:
        """Get user battle statistics."""
        return self._user_stats.get(user_id, {"wins": 0, "losses": 0, "streak": 0})
    
    def _cleanup_expired_battles(self) -> None:
        """Remove expired battle sessions."""
        expired = [
            uid for uid, battle in self._active_battles.items()
            if battle.is_expired() or battle.is_completed
        ]
        for uid in expired:
            self._active_battles.pop(uid, None)


# Global manager
catch_manager = CatchManager()


# ============================================================
# 🚨 Cheater Broadcast System
# ============================================================

async def broadcast_cheater_alert(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    username: str,
    first_name: str,
    violation_type: str,
    violations: int
) -> None:
    """Broadcast cheater alert to all active groups."""
    try:
        groups = await get_all_groups(None, active_only=True)
        
        if not groups:
            return
        
        alert_text = (
            "🚨 **CHEATER ALERT** 🚨\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **User:** {first_name}\n"
            f"📛 **Username:** @{username}\n"
            f"🆔 **ID:** `{user_id}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"⚠️ **Violation:** {violation_type}\n"
            f"📊 **Total Violations:** {violations}\n\n"
            "This user has been flagged for cheating.\n"
            "🛡️ _Anti-cheat system activated._"
        )
        
        sent_count = 0
        
        for group in groups[:50]:  # Limit to 50 groups
            try:
                await context.bot.send_message(
                    chat_id=group["group_id"],
                    text=alert_text,
                    parse_mode="Markdown"
                )
                sent_count += 1
                
                # Rate limiting
                if sent_count % 10 == 0:
                    await asyncio.sleep(1)
                    
            except TelegramError:
                continue
        
        app_logger.warning(
            f"🚨 Cheater alert sent to {sent_count} groups for user {user_id}"
        )
        
    except Exception as e:
        error_logger.error(f"Failed to broadcast cheater alert: {e}")


# ============================================================
# 🎭 Battle Messages
# ============================================================

VICTORY_MESSAGES = [
    "⚔️ **LEGENDARY VICTORY!** ⚔️\n\n"
    "**{card_name}** falls to their knees!\n"
    "\"You're too powerful!\" they whisper.\n\n"
    "🏆 **THE CARD IS YOURS!**",
    
    "🔥 **FLAWLESS TRIUMPH!** 🔥\n\n"
    "Your ultimate attack connects!\n"
    "**{card_name}** never stood a chance!\n\n"
    "👑 **ABSOLUTE DOMINATION!**",
    
    "✨ **DESTINED VICTORY!** ✨\n\n"
    "The stars aligned! Perfect strike!\n"
    "**{card_name}** is defeated!\n\n"
    "🌟 **FATE CHOSE YOU!**",
]

DEFEAT_MESSAGES = [
    "💀 **CRUSHING DEFEAT!** 💀\n\n"
    "**{card_name}** looks at you with pity...\n"
    "\"Was that your best?\" they laugh.\n\n"
    "😭 **YOU GOT DESTROYED!**",
    
    "🪦 **TOTAL ANNIHILATION!** 🪦\n\n"
    "**{card_name}** demolished you!\n"
    "Your pride lies shattered...\n\n"
    "🤡 **ABSOLUTELY PATHETIC!**",
    
    "💔 **HUMILIATING FAILURE!** 💔\n\n"
    "**{card_name}** didn't even try!\n"
    "They yawned while defeating you!\n\n"
    "😱 **SO EMBARRASSING!**",
]


# ============================================================
# 🎴 Main Catch Command
# ============================================================

async def catch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /catch command with full anti-cheat protection."""
    user = update.effective_user
    chat = update.effective_chat
    message = update.message
    
    if not message or not user:
        return
    
    log_command(user.id, "catch", chat.id)
    
    # Check if user is banned for cheating
    if anti_cheat.is_user_banned(user.id):
        await message.reply_text(
            "🚫 **You are banned from catching cards.**\n\n"
            "Reason: Cheating detected.\n"
            "Contact an admin if you believe this is an error.",
            parse_mode="Markdown"
        )
        return
    
    # Ensure user exists
    await ensure_user(
        pool=None,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    # Private chat - show help
    if chat.type == ChatType.PRIVATE:
        stats = catch_manager.get_user_stats(user.id)
        is_cooldown, remaining = catch_manager.check_user_cooldown(user.id)
        
        cooldown_text = ""
        if is_cooldown:
            cooldown_text = f"\n⏳ Cooldown: **{catch_manager.format_cooldown(remaining)}**"
        
        await message.reply_text(
            "⚔️ **Battle Catch System**\n\n"
            "Use `/catch` in a group to find a card!\n\n"
            "**How it works:**\n"
            "1️⃣ Use `/catch` to spawn a card\n"
            "2️⃣ Click ⚔️ **BATTLE** to fight\n"
            "3️⃣ Win = Card is yours! 🏆\n"
            "4️⃣ Lose = Card escapes 💀\n\n"
            "**Win Chances:**\n"
            "🟢 Common: ~80-85%\n"
            "🟡 Rare: ~60-70%\n"
            "🔴 Legendary: ~35%\n\n"
            f"📊 **Your Stats:**\n"
            f"✅ Wins: {stats['wins']} | ❌ Losses: {stats['losses']}\n"
            f"🔥 Streak: {stats['streak']}"
            f"{cooldown_text}",
            parse_mode="Markdown"
        )
        return
    
    # Group chat
    await ensure_group(None, chat.id, chat.title)
    
    # Check cooldown
    is_cooldown, remaining = catch_manager.check_user_cooldown(user.id)
    
    if is_cooldown:
        await message.reply_text(
            f"⏳ **Cooldown Active**\n\n"
            f"Wait: **{catch_manager.format_cooldown(remaining)}**\n\n"
            f"💡 _Each user has their own cooldown!_",
            parse_mode="Markdown"
        )
        return
    
    # Check existing battle
    existing = catch_manager.get_battle(user.id)
    if existing:
        await message.reply_text(
            "⚔️ **Battle in Progress!**\n\n"
            "Finish your current battle first!",
            parse_mode="Markdown"
        )
        return
    
    # Check cards exist
    total_cards = await get_card_count(None)
    if total_cards == 0:
        await message.reply_text(
            "❌ **No Cards Available**\n\n"
            "Ask an admin to upload cards first!",
            parse_mode="Markdown"
        )
        return
    
    # Get random card
    rarity_id = get_random_rarity()
    card = await get_random_card(None, rarity=rarity_id)
    
    if not card:
        card = await get_random_card(None)
    
    if not card:
        await message.reply_text("❌ Failed to find a card. Try again.")
        return
    
    # Extract card info
    card_id = card["card_id"]
    character = card["character_name"]
    anime = card["anime"]
    rarity = card["rarity"]
    photo_file_id = card["photo_file_id"]
    
    rarity_name, _, rarity_emoji = rarity_to_text(rarity)
    value = calculate_rarity_value(rarity)
    win_chance = calculate_win_chance(rarity)
    difficulty, diff_emoji = get_difficulty_text(rarity)
    
    # Start battle and get token
    token = catch_manager.start_battle(
        user_id=user.id,
        card_id=card_id,
        card_data=dict(card),
        message_id=0,  # Will update after sending
        chat_id=chat.id
    )
    
    if not token:
        await message.reply_text("❌ Failed to start battle. Try again.")
        return
    
    # Set cooldown immediately
    catch_manager.set_user_cooldown(user.id)
    
    # Build message
    spawn_text = (
        f"🎴 **A Wild Card Appeared!**\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎬 **Anime:** {anime}\n"
        f"✨ **Rarity:** {rarity_emoji} {rarity_name}\n"
        f"💰 **Value:** {value:,} coins\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{diff_emoji} **Difficulty:** {difficulty}\n"
        f"🎲 **Win Chance:** {win_chance}%\n\n"
        f"⏱️ **{BATTLE_TIMEOUT_SECONDS}s** to battle!\n\n"
        f"👤 [{user.first_name}](tg://user?id={user.id})'s challenge"
    )
    
    # Token embedded in callback data for security
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⚔️ BATTLE!",
                callback_data=f"cb_{user.id}_{card_id}_{token}"
            ),
        ],
        [
            InlineKeyboardButton(
                "🏃 Run Away",
                callback_data=f"cf_{user.id}_{token}"
            ),
        ],
    ])
    
    try:
        sent = await message.reply_photo(
            photo=photo_file_id,
            caption=spawn_text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        
        # Update message ID in battle session
        battle = catch_manager.get_battle(user.id)
        if battle:
            battle.message_id = sent.message_id
        
        app_logger.info(
            f"🎴 Card spawned: {character} ({rarity_emoji}) for {user.first_name} "
            f"- {win_chance}% chance - Token: {token[:8]}..."
        )
        
        # Schedule expiration
        asyncio.create_task(
            handle_battle_expiration(
                context, user.id, sent.message_id, chat.id, token, card
            )
        )
        
    except TelegramError as e:
        error_logger.error(f"Failed to send card: {e}")
        catch_manager.clear_user_cooldown(user.id)
        catch_manager.complete_battle(user.id, won=False)
        await message.reply_text("❌ Failed to spawn card.")


async def handle_battle_expiration(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    message_id: int,
    chat_id: int,
    token: str,
    card: Dict[str, Any]
) -> None:
    """Handle battle timeout - delete the message."""
    await asyncio.sleep(BATTLE_TIMEOUT_SECONDS)
    
    battle = catch_manager.get_battle(user_id)
    
    if battle and battle.message_id == message_id and not battle.is_completed:
        # Mark as completed (timeout = loss)
        catch_manager.complete_battle(user_id, won=False)
        
        # Delete the message to prevent any further interaction
        try:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=message_id
            )
        except TelegramError:
            # If can't delete, try to edit
            try:
                await context.bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption=(
                        "⏳ **Time's Up!**\n\n"
                        f"💨 _{card['character_name']} escaped..._"
                    ),
                    parse_mode="Markdown",
                    reply_markup=None  # Remove buttons
                )
            except TelegramError:
                pass
        
        app_logger.info(f"⏳ Battle expired for user {user_id}")


# ============================================================
# ⚔️ Battle Callback Handler (Secured)
# ============================================================

async def battle_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle battle callbacks with full anti-cheat protection.
    
    Security measures:
    1. Rate limiting
    2. Token validation (one-time use)
    3. User verification
    4. Atomic operations with locks
    5. Immediate message deletion
    """
    query = update.callback_query
    user = query.from_user
    data = query.data
    
    # Rate limit check
    is_allowed, violation_count = anti_cheat.check_rate_limit(user.id)
    
    if not is_allowed:
        # Record violation
        record = anti_cheat.record_violation(
            user.id,
            user.username or "unknown",
            user.first_name or "Unknown",
            "RATE_LIMIT_EXCEEDED"
        )
        
        await query.answer(
            "🚫 Too many requests! Slow down!",
            show_alert=True
        )
        
        # Broadcast if threshold reached
        if anti_cheat.should_notify_groups(user.id):
            asyncio.create_task(
                broadcast_cheater_alert(
                    context, user.id,
                    user.username or "unknown",
                    user.first_name or "Unknown",
                    "Button Spam Attack",
                    record.violations
                )
            )
        
        return
    
    # Check if banned
    if anti_cheat.is_user_banned(user.id):
        await query.answer("🚫 You are banned for cheating!", show_alert=True)
        return
    
    await query.answer()
    
    # Handle flee
    if data.startswith("cf_"):
        await handle_flee(update, context, data)
        return
    
    # Handle battle
    if data.startswith("cb_"):
        await handle_battle(update, context, data)
        return


async def handle_flee(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str
) -> None:
    """Handle flee action with security checks."""
    query = update.callback_query
    user = query.from_user
    
    try:
        parts = data.split("_")
        owner_id = int(parts[1])
        token = parts[2]
    except (IndexError, ValueError):
        await query.answer("❌ Invalid action.", show_alert=True)
        return
    
    # Verify owner
    if user.id != owner_id:
        # Cheat attempt: clicking someone else's button
        anti_cheat.record_violation(
            user.id,
            user.username or "unknown",
            user.first_name or "Unknown",
            "UNAUTHORIZED_BUTTON_CLICK"
        )
        await query.answer("❌ This isn't your battle!", show_alert=True)
        return
    
    # Validate token
    if not anti_cheat.validate_and_consume_token(token):
        anti_cheat.record_violation(
            user.id,
            user.username or "unknown",
            user.first_name or "Unknown",
            "TOKEN_REUSE_ATTEMPT"
        )
        await query.answer("❌ Invalid or expired action!", show_alert=True)
        return
    
    # Complete battle as loss
    catch_manager.complete_battle(user.id, won=False)
    
    # Delete the message
    try:
        await query.message.delete()
    except TelegramError:
        try:
            await query.edit_message_caption(
                caption="🏃 **You fled!**\n\n_The card watches you run..._",
                parse_mode="Markdown",
                reply_markup=None
            )
        except TelegramError:
            pass


async def handle_battle(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str
) -> None:
    """Handle battle action with full security."""
    query = update.callback_query
    user = query.from_user
    
    try:
        parts = data.split("_")
        owner_id = int(parts[1])
        card_id = int(parts[2])
        token = parts[3]
    except (IndexError, ValueError):
        await query.answer("❌ Invalid action.", show_alert=True)
        return
    
    # Verify owner
    if user.id != owner_id:
        anti_cheat.record_violation(
            user.id,
            user.username or "unknown",
            user.first_name or "Unknown",
            "UNAUTHORIZED_BATTLE_ATTEMPT"
        )
        await query.answer("❌ This isn't your battle!", show_alert=True)
        return
    
    # Get user lock for atomic operation
    lock = anti_cheat.get_user_lock(user.id)
    
    async with lock:
        # Check if already processed
        if anti_cheat.is_battle_processed(user.id, token):
            anti_cheat.record_violation(
                user.id,
                user.username or "unknown",
                user.first_name or "Unknown",
                "DUPLICATE_BATTLE_ATTEMPT"
            )
            
            record = anti_cheat.get_cheat_record(user.id)
            
            if record and anti_cheat.should_notify_groups(user.id):
                asyncio.create_task(
                    broadcast_cheater_alert(
                        context, user.id,
                        user.username or "unknown",
                        user.first_name or "Unknown",
                        "Duplicate Battle Exploit",
                        record.violations
                    )
                )
            
            await query.answer("❌ Already processed!", show_alert=True)
            return
        
        # Validate and consume token
        if not anti_cheat.validate_and_consume_token(token):
            anti_cheat.record_violation(
                user.id,
                user.username or "unknown",
                user.first_name or "Unknown",
                "INVALID_TOKEN"
            )
            await query.answer("❌ Invalid or expired!", show_alert=True)
            return
        
        # Mark as processed BEFORE doing anything
        anti_cheat.mark_battle_processed(user.id, token)
        
        # Get battle session
        battle = catch_manager.get_battle(user.id)
        
        if not battle:
            await query.answer("⏳ Battle expired!", show_alert=True)
            return
        
        if battle.card_id != card_id:
            await query.answer("❌ Card mismatch!", show_alert=True)
            return
        
        # Execute battle
        await execute_battle(update, context, battle, token)


async def execute_battle(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    battle: BattleSession,
    token: str
) -> None:
    """Execute the battle with dramatic effect."""
    query = update.callback_query
    user = query.from_user
    card = battle.card_data
    
    character = card["character_name"]
    anime = card["anime"]
    rarity = card["rarity"]
    rarity_name, _, rarity_emoji = rarity_to_text(rarity)
    value = calculate_rarity_value(rarity)
    win_chance = calculate_win_chance(rarity)
    
    # Show battle animation (quick)
    try:
        await query.edit_message_caption(
            caption=(
                f"⚔️ **BATTLE!**\n\n"
                f"**{user.first_name}** vs **{character}**\n\n"
                f"🎲 Rolling... ({win_chance}% chance)"
            ),
            parse_mode="Markdown",
            reply_markup=None  # Remove buttons immediately!
        )
    except TelegramError:
        pass
    
    # Brief pause
    await asyncio.sleep(1.5)
    
    # Determine outcome
    roll = random.randint(1, 100)
    won = roll <= win_chance
    
    # Complete battle (atomic)
    if not catch_manager.complete_battle(user.id, won):
        # Already completed somehow - possible exploit
        anti_cheat.record_violation(
            user.id,
            user.username or "unknown",
            user.first_name or "Unknown",
            "BATTLE_ALREADY_COMPLETED"
        )
        return
    
    stats = catch_manager.get_user_stats(user.id)
    
    if won:
        # Add to collection
        try:
            await add_to_collection(None, user.id, battle.card_id, battle.chat_id)
            await increment_card_caught(None, battle.card_id)
            await update_user_stats(None, user.id, coins_delta=value, catches_delta=1)
            log_card_catch(user.id, character, rarity_name)
        except Exception as e:
            error_logger.error(f"Failed to add card: {e}")
        
        victory_msg = random.choice(VICTORY_MESSAGES).format(card_name=character)
        
        streak_text = ""
        if stats["streak"] >= 3:
            streak_text = f"\n\n🔥 **{stats['streak']} Win Streak!**"
        
        result_text = (
            f"{victory_msg}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **{character}**\n"
            f"🎬 {anime}\n"
            f"✨ {rarity_emoji} {rarity_name}\n"
            f"💰 +{value:,} coins\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🏆 [{user.first_name}](tg://user?id={user.id})"
            f"{streak_text}"
        )
        
        app_logger.info(f"🏆 {user.first_name} caught {character} ({rarity_emoji})")
        
    else:
        defeat_msg = random.choice(DEFEAT_MESSAGES).format(card_name=character)
        
        result_text = (
            f"{defeat_msg}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎲 Rolled: **{roll}** (needed ≤{win_chance})\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📊 {stats['wins']}W / {stats['losses']}L"
        )
        
        app_logger.info(
            f"💀 {user.first_name} lost to {character} "
            f"- Rolled {roll}, needed ≤{win_chance}"
        )
    
    # Update message with result, then delete after delay
    try:
        await query.edit_message_caption(
            caption=result_text,
            parse_mode="Markdown",
            reply_markup=None
        )
        
        # Delete after 10 seconds to prevent any lingering exploit
        await asyncio.sleep(10)
        
        try:
            await query.message.delete()
        except TelegramError:
            pass
            
    except TelegramError as e:
        error_logger.error(f"Error updating result: {e}")


# ============================================================
# 🔧 Admin Commands
# ============================================================

async def reset_cooldown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: Reset user cooldown."""
    user = update.effective_user
    
    if not update.message or not Config.is_admin(user.id):
        return
    
    target_id = user.id
    if context.args:
        try:
            target_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID.")
            return
    
    catch_manager.clear_user_cooldown(target_id)
    await update.message.reply_text(f"✅ Cooldown cleared for `{target_id}`", parse_mode="Markdown")


async def clear_cheat_record_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: Clear a user's cheat record."""
    user = update.effective_user
    
    if not update.message or not Config.is_admin(user.id):
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /clearcheat <user_id>")
        return
    
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")
        return
    
    anti_cheat.clear_user_record(target_id)
    await update.message.reply_text(f"✅ Cheat record cleared for `{target_id}`", parse_mode="Markdown")


async def view_cheaters_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: View all flagged cheaters."""
    user = update.effective_user
    
    if not update.message or not Config.is_admin(user.id):
        return
    
    records = anti_cheat._cheat_records
    
    if not records:
        await update.message.reply_text("✅ No cheaters detected!")
        return
    
    text = "🚨 **Flagged Users**\n\n"
    
    for uid, record in list(records.items())[:20]:
        status = "🚫 BANNED" if record.is_banned else "⚠️ Warned"
        text += (
            f"{status} `{uid}` @{record.username}\n"
            f"   Violations: {record.violations}\n"
        )
    
    await update.message.reply_text(text, parse_mode="Markdown")


# ============================================================
# 🔧 Handler Exports
# ============================================================

catch_command_handler = CommandHandler("catch", catch_command)
force_spawn_handler = CommandHandler("resetcooldown", reset_cooldown_command)
clear_cheat_handler = CommandHandler("clearcheat", clear_cheat_record_command)
view_cheaters_handler = CommandHandler("cheaters", view_cheaters_command)

battle_callback = CallbackQueryHandler(
    battle_callback_handler,
    pattern=r"^c[bf]_"
)

# Disabled name guessing for security
name_guess_message_handler = MessageHandler(
    filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
    lambda u, c: None
)