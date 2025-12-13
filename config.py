# ============================================================
# 📁 File: config.py
# 📍 Location: telegram_card_bot/config.py
# 📝 Description: Enhanced configuration with modern display
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
    # 🎨 UI Configuration (NEW)
    # ========================
    
    # Enable auto-reactions on catches
    ENABLE_CATCH_REACTIONS: bool = os.getenv("ENABLE_CATCH_REACTIONS", "true").lower() == "true"
    
    # Celebrate rare catches with special messages
    CELEBRATE_RARE_CATCHES: bool = os.getenv("CELEBRATE_RARE_CATCHES", "true").lower() == "true"
    
    # Minimum rarity for celebration (7 = Platinum)
    CELEBRATION_MIN_RARITY: int = int(os.getenv("CELEBRATION_MIN_RARITY", "7"))
    
    # ========================
    # 👑 Owner & Admin Configuration
    # ========================
    
    OWNER_ID: Optional[int] = (
        int(os.getenv("OWNER_ID")) 
        if os.getenv("OWNER_ID", "").isdigit() 
        else None
    )
    
    ADMIN_IDS: List[int] = [
        int(x.strip()) 
        for x in os.getenv("ADMIN_IDS", "").split(",") 
        if x.strip().isdigit()
    ]
    
    # ========================
    # 📢 Channel Configuration
    # ========================
    
    DATABASE_CHANNEL_ID: Optional[int] = (
        int(os.getenv("DATABASE_CHANNEL_ID"))
        if os.getenv("DATABASE_CHANNEL_ID", "").lstrip("-").isdigit()
        else None
    )
    
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
    
    # ========================
    # 🎯 Drop System Configuration
    # ========================
    
    DROP_ENABLED: bool = os.getenv("DROP_ENABLED", "true").lower() == "true"
    DEFAULT_DROP_THRESHOLD: int = int(os.getenv("DEFAULT_DROP_THRESHOLD", "50"))
    
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
        """Return a clean formatted string of non-sensitive config for logging."""
        
        # Status indicators
        db_status = "✅" if cls.DATABASE_URL and cls.DATABASE_URL != "postgresql://user:password@localhost:5432/cardbot" else "⚠️"
        webhook_status = "✅" if cls.WEBHOOK_URL else "⚠️ Polling"
        owner_status = "✅" if cls.OWNER_ID else "⚠️ Not Set"
        
        return f"""
🎴 *LuLuCatch Bot Configuration*

🤖 Bot: @{cls.BOT_USERNAME}
🌐 Webhook: {webhook_status}
🗄️ Database: {db_status}
👑 Owner: {owner_status}

⚙️ *Settings*
├ Cooldown: {cls.COOLDOWN_SECONDS}s
├ Cards/Page: {cls.CARDS_PER_PAGE}
├ Reactions: {"✅" if cls.ENABLE_CATCH_REACTIONS else "❌"}
└ Debug: {"✅" if cls.DEBUG else "❌"}

📊 *Features*
├ Inline Mode: {"✅" if cls.ENABLE_INLINE_MODE else "❌"}
├ Trading: {"✅" if cls.ENABLE_TRADING else "❌"}
├ Auto Spawn: {"✅" if cls.AUTO_SPAWN else "❌"}
└ Drop System: {"✅" if cls.DROP_ENABLED else "❌"}
"""
    
    @classmethod
    def display_config_simple(cls) -> str:
        """Simple one-line config display for startup logs."""
        features = []
        if cls.ENABLE_INLINE_MODE:
            features.append("inline")
        if cls.ENABLE_TRADING:
            features.append("trading")
        if cls.ENABLE_CATCH_REACTIONS:
            features.append("reactions")
        if cls.DROP_ENABLED:
            features.append("drops")
        
        return f"@{cls.BOT_USERNAME} | Features: {', '.join(features) or 'none'}"


config = Config()