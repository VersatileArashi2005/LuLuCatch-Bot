# ============================================================
# 📁 File: config.py
# 📍 Location: telegram_card_bot/config.py
# 📝 Description: Configuration settings loaded from environment
# ============================================================

import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()


class Config:
    """
    Central configuration class for the Telegram Card Bot.
    All settings are loaded from environment variables with sensible defaults.
    """
    
    # ========================
    # 🤖 Telegram Bot Settings
    # ========================
    
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    """Telegram Bot API token from @BotFather"""
    
    BOT_USERNAME: str = os.getenv("BOT_USERNAME", "LuLuCatchBot")
    """Bot username without @ symbol"""
    
    # ========================
    # 🌐 Webhook Configuration
    # ========================
    
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")
    """
    Public HTTPS URL for webhook (e.g., https://your-app.railway.app)
    Leave empty to use polling mode instead of webhooks
    """
    
    WEBHOOK_PATH: str = os.getenv("WEBHOOK_PATH", "/webhook")
    """Path for the webhook endpoint"""
    
    WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "supersecrettoken123")
    """Secret token to verify webhook requests from Telegram"""
    
    # ========================
    # 🗄️ Database Configuration
    # ========================
    
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/cardbot")
    """
    PostgreSQL connection URL
    Format: postgresql://user:password@host:port/database
    """
    
    # Parse DATABASE_URL for individual components if needed
    DB_MIN_CONNECTIONS: int = int(os.getenv("DB_MIN_CONNECTIONS", "2"))
    """Minimum number of connections in the pool"""
    
    DB_MAX_CONNECTIONS: int = int(os.getenv("DB_MAX_CONNECTIONS", "10"))
    """Maximum number of connections in the pool"""
    
    # ========================
    # 🖥️ Server Configuration
    # ========================
    
    PORT: int = int(os.getenv("PORT", "8000"))
    """Port for the FastAPI server (Railway assigns this automatically)"""
    
    HOST: str = os.getenv("HOST", "0.0.0.0")
    """Host to bind the server to"""
    
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    """Enable debug mode for development"""
    
    # ========================
    # ⚙️ Game Configuration
    # ========================
    
    COOLDOWN_SECONDS: int = int(os.getenv("COOLDOWN_SECONDS", "60"))
    """Cooldown between card spawns in a group (seconds)"""
    
    CATCH_TIMEOUT: int = int(os.getenv("CATCH_TIMEOUT", "30"))
    """Time window to catch a spawned card (seconds)"""
    
    CARDS_PER_PAGE: int = int(os.getenv("CARDS_PER_PAGE", "6"))
    """Number of cards to show per page in harem view"""
    
    # ========================
    # 👑 Admin Configuration
    # ========================
    
    ADMIN_IDS: list[int] = [
        int(x.strip()) 
        for x in os.getenv("ADMIN_IDS", "").split(",") 
        if x.strip().isdigit()
    ]
    """List of Telegram user IDs with admin privileges"""
    
    OWNER_ID: Optional[int] = (
        int(os.getenv("OWNER_ID")) 
        if os.getenv("OWNER_ID", "").isdigit() 
        else None
    )
    """Primary owner/developer user ID"""
    
    # ========================
    # 📊 Feature Flags
    # ========================
    
    ENABLE_INLINE_MODE: bool = os.getenv("ENABLE_INLINE_MODE", "true").lower() == "true"
    """Enable inline query mode for sharing cards"""
    
    ENABLE_TRADING: bool = os.getenv("ENABLE_TRADING", "true").lower() == "true"
    """Enable card trading between users"""
    
    AUTO_SPAWN: bool = os.getenv("AUTO_SPAWN", "true").lower() == "true"
    """Enable automatic card spawning in groups"""
    
    @classmethod
    def validate(cls) -> tuple[bool, list[str]]:
        """
        Validate required configuration settings.
        
        Returns:
            tuple: (is_valid: bool, errors: list[str])
        """
        errors: list[str] = []
        
        if not cls.BOT_TOKEN:
            errors.append("❌ BOT_TOKEN is required")
        
        if not cls.DATABASE_URL:
            errors.append("❌ DATABASE_URL is required")
        
        if cls.WEBHOOK_URL and not cls.WEBHOOK_URL.startswith("https://"):
            errors.append("⚠️ WEBHOOK_URL should use HTTPS")
        
        return len(errors) == 0, errors
    
    @classmethod
    def get_full_webhook_url(cls) -> str:
        """Get the complete webhook URL including path."""
        return f"{cls.WEBHOOK_URL.rstrip('/')}{cls.WEBHOOK_PATH}"
    
    @classmethod
    def is_admin(cls, user_id: int) -> bool:
        """Check if a user ID has admin privileges."""
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
║ 👑 Admins: {len(cls.ADMIN_IDS):<27} ║
║ 🐛 Debug: {str(cls.DEBUG):<28} ║
╚══════════════════════════════════════════╝
"""


# Create a singleton instance for easy imports
config = Config()