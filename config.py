# ============================================================
# 📁 File: config.py
# 📍 Location: telegram_card_bot/config.py
# 📝 Description: Configuration settings with role support
# ============================================================

import os
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Central configuration class for the Telegram Card Bot."""
    
    # ========================
    # 🤖 Telegram Bot Settings
    # ========================
    
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    BOT_USERNAME: str = os.getenv("BOT_USERNAME", "LuLuCatchBot")
    
    # ========================
    # 🌐 Webhook Configuration
    # ========================
    
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")
    WEBHOOK_PATH: str = os.getenv("WEBHOOK_PATH", "/webhook")
    WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "supersecrettoken123")
    
    # ========================
    # 🗄️ Database Configuration
    # ========================
    
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/cardbot")
    DB_MIN_CONNECTIONS: int = int(os.getenv("DB_MIN_CONNECTIONS", "2"))
    DB_MAX_CONNECTIONS: int = int(os.getenv("DB_MAX_CONNECTIONS", "10"))
    
    # ========================
    # 🖥️ Server Configuration
    # ========================
    
    PORT: int = int(os.getenv("PORT", "8000"))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    # ========================
    # ⚙️ Game Configuration
    # ========================
    
    COOLDOWN_SECONDS: int = int(os.getenv("COOLDOWN_SECONDS", "60"))
    CATCH_TIMEOUT: int = int(os.getenv("CATCH_TIMEOUT", "30"))
    CARDS_PER_PAGE: int = int(os.getenv("CARDS_PER_PAGE", "6"))
    
    # ========================
    # 👑 Owner & Admin Configuration
    # ========================
    
    OWNER_ID: Optional[int] = (
        int(os.getenv("OWNER_ID")) 
        if os.getenv("OWNER_ID", "").isdigit() 
        else None
    )
    
    # Legacy admin IDs (from env) - will be merged with database roles
    ADMIN_IDS: List[int] = [
        int(x.strip()) 
        for x in os.getenv("ADMIN_IDS", "").split(",") 
        if x.strip().isdigit()
    ]
    
    # ========================
    # 📢 Channel Configuration
    # ========================
    
    # Channel for card database archive
    DATABASE_CHANNEL_ID: Optional[int] = (
        int(os.getenv("DATABASE_CHANNEL_ID"))
        if os.getenv("DATABASE_CHANNEL_ID", "").lstrip("-").isdigit()
        else None
    )
    
    # Channel username (without @) for links
    DATABASE_CHANNEL_USERNAME: str = os.getenv("DATABASE_CHANNEL_USERNAME", "lulucatchdatabase")
    
    # ========================
    # 🔔 Notification Settings
    # ========================
    
    NOTIFY_GROUPS_ON_UPLOAD: bool = os.getenv("NOTIFY_GROUPS_ON_UPLOAD", "true").lower() == "true"
    
    # ========================
    # 📊 Feature Flags
    # ========================
    
    ENABLE_INLINE_MODE: bool = os.getenv("ENABLE_INLINE_MODE", "true").lower() == "true"
    ENABLE_TRADING: bool = os.getenv("ENABLE_TRADING", "true").lower() == "true"
    AUTO_SPAWN: bool = os.getenv("AUTO_SPAWN", "true").lower() == "true"
    
    @classmethod
    def validate(cls) -> tuple[bool, list[str]]:
        """Validate required configuration settings."""
        errors: list[str] = []
        
        if not cls.BOT_TOKEN:
            errors.append("❌ BOT_TOKEN is required")
        
        if not cls.DATABASE_URL:
            errors.append("❌ DATABASE_URL is required")
        
        if cls.WEBHOOK_URL and not cls.WEBHOOK_URL.startswith("https://"):
            errors.append("⚠️ WEBHOOK_URL should use HTTPS")
        
        if not cls.OWNER_ID:
            errors.append("⚠️ OWNER_ID not set - role commands won't work properly")
        
        return len(errors) == 0, errors
    
    @classmethod
    def get_full_webhook_url(cls) -> str:
        """Get the complete webhook URL including path."""
        return f"{cls.WEBHOOK_URL.rstrip('/')}{cls.WEBHOOK_PATH}"
    
    @classmethod
    def is_owner(cls, user_id: int) -> bool:
        """Check if user is the bot owner."""
        return user_id == cls.OWNER_ID
    
    @classmethod
    def is_admin(cls, user_id: int) -> bool:
        """Check if user has admin privileges (legacy check)."""
        return user_id in cls.ADMIN_IDS or user_id == cls.OWNER_ID
    
    @classmethod
    def display_config(cls) -> str:
        """Return a formatted string of non-sensitive config for logging."""
        return f"""
╔══════════════════════════════════════════╗
║       🎴 Card Bot Configuration 🎴        ║
╠══════════════════════════════════════════╣
║ 🤖 Bot Username: @{cls.BOT_USERNAME:<20} ║
║ 🌐 Webhook Mode: {str(bool(cls.WEBHOOK_URL)):<21} ║
║ 🖥️  Port: {cls.PORT:<30} ║
║ ⏱️  Cooldown: {cls.COOLDOWN_SECONDS}s{' ' * (26 - len(str(cls.COOLDOWN_SECONDS)))}║
║ 👑 Owner ID: {str(cls.OWNER_ID or 'Not Set'):<25} ║
║ 📢 DB Channel: {str(cls.DATABASE_CHANNEL_ID or 'Not Set'):<22} ║
║ 🐛 Debug: {str(cls.DEBUG):<28} ║
╚══════════════════════════════════════════╝
"""


config = Config()