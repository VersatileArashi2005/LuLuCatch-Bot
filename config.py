"""
Configuration module for the Telegram Card Bot.
Loads environment variables and provides centralized configuration.
"""

import os
from dotenv import load_dotenv
from typing import List

# Load environment variables from .env file
load_dotenv()


class Config:
    """Bot configuration class with all settings."""
    
    # ===== Bot Settings =====
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")
    PORT: int = int(os.getenv("PORT", 8000))
    
    # ===== Database Settings =====
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/cardbot")
    DB_POOL_MIN_SIZE: int = int(os.getenv("DB_POOL_MIN_SIZE", 5))
    DB_POOL_MAX_SIZE: int = int(os.getenv("DB_POOL_MAX_SIZE", 20))
    
    # ===== Admin Settings =====
    OWNER_ID: int = int(os.getenv("OWNER_ID", 0))
    
    # ===== Cooldown Settings (in hours) =====
    DEFAULT_CATCH_COOLDOWN: int = int(os.getenv("DEFAULT_CATCH_COOLDOWN", 24))
    
    # ===== Pagination Settings =====
    CARDS_PER_PAGE: int = 10
    HAREM_PER_PAGE: int = 5
    
    # ===== Role Hierarchy =====
    ROLES: List[str] = ["user", "uploader", "admin", "dev", "owner"]
    
    @classmethod
    def validate(cls) -> bool:
        """Validate required configuration."""
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_TOKEN is required!")
        if not cls.DATABASE_URL:
            raise ValueError("DATABASE_URL is required!")
        return True


# Create global config instance
config = Config()