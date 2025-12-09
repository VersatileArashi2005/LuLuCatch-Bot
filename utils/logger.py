# ============================================================
# 📁 File: utils/logger.py
# 📍 Location: telegram_card_bot/utils/logger.py
# 📝 Description: Colored console logging with emoji support
# ============================================================

import logging
import sys
from datetime import datetime
from typing import Optional


class ColorCodes:
    """ANSI color codes for terminal output."""
    
    # Reset
    RESET = "\033[0m"
    
    # Regular colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    
    # Bright/Bold colors
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"
    
    # Styles
    BOLD = "\033[1m"
    DIM = "\033[2m"
    UNDERLINE = "\033[4m"


class EmojiFormatter(logging.Formatter):
    """
    Custom formatter that adds colors and emojis to log messages.
    Makes console output more readable and visually appealing.
    """
    
    # Level-specific formatting
    LEVEL_FORMATS = {
        logging.DEBUG: {
            "emoji": "🔍",
            "color": ColorCodes.BRIGHT_BLACK,
            "label": "DEBUG"
        },
        logging.INFO: {
            "emoji": "📗",
            "color": ColorCodes.BRIGHT_GREEN,
            "label": "INFO"
        },
        logging.WARNING: {
            "emoji": "⚠️",
            "color": ColorCodes.BRIGHT_YELLOW,
            "label": "WARN"
        },
        logging.ERROR: {
            "emoji": "❌",
            "color": ColorCodes.BRIGHT_RED,
            "label": "ERROR"
        },
        logging.CRITICAL: {
            "emoji": "🔥",
            "color": ColorCodes.RED + ColorCodes.BOLD,
            "label": "CRITICAL"
        }
    }
    
    def __init__(self, use_colors: bool = True, use_emojis: bool = True):
        """
        Initialize the formatter.
        
        Args:
            use_colors: Enable ANSI color codes
            use_emojis: Enable emoji prefixes
        """
        super().__init__()
        self.use_colors = use_colors
        self.use_emojis = use_emojis
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format the log record with colors and emojis.
        
        Args:
            record: The log record to format
            
        Returns:
            Formatted log string
        """
        # Get level-specific formatting
        level_fmt = self.LEVEL_FORMATS.get(record.levelno, {
            "emoji": "📝",
            "color": ColorCodes.WHITE,
            "label": "LOG"
        })
        
        # Format timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        
        # Build the log message
        parts = []
        
        # Timestamp (dimmed)
        if self.use_colors:
            parts.append(f"{ColorCodes.DIM}{timestamp}{ColorCodes.RESET}")
        else:
            parts.append(timestamp)
        
        # Emoji (if enabled)
        if self.use_emojis:
            parts.append(level_fmt["emoji"])
        
        # Level label (colored)
        if self.use_colors:
            parts.append(
                f"{level_fmt['color']}[{level_fmt['label']:^8}]{ColorCodes.RESET}"
            )
        else:
            parts.append(f"[{level_fmt['label']:^8}]")
        
        # Logger name (cyan)
        if self.use_colors:
            parts.append(f"{ColorCodes.CYAN}{record.name}{ColorCodes.RESET}")
        else:
            parts.append(record.name)
        
        # Separator
        parts.append("→")
        
        # Message (colored based on level)
        if self.use_colors:
            parts.append(f"{level_fmt['color']}{record.getMessage()}{ColorCodes.RESET}")
        else:
            parts.append(record.getMessage())
        
        # Combine parts
        formatted = " ".join(parts)
        
        # Add exception info if present
        if record.exc_info:
            if self.use_colors:
                formatted += f"\n{ColorCodes.BRIGHT_RED}"
            formatted += "\n" + self.formatException(record.exc_info)
            if self.use_colors:
                formatted += ColorCodes.RESET
        
        return formatted


class LoggerFactory:
    """Factory class for creating configured loggers."""
    
    _loggers: dict[str, logging.Logger] = {}
    _initialized: bool = False
    
    @classmethod
    def setup(
        cls, 
        level: int = logging.INFO,
        use_colors: bool = True,
        use_emojis: bool = True
    ) -> None:
        """
        Set up the logging configuration.
        
        Args:
            level: Minimum logging level
            use_colors: Enable colored output
            use_emojis: Enable emoji prefixes
        """
        if cls._initialized:
            return
        
        # Create handler with our custom formatter
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(EmojiFormatter(use_colors=use_colors, use_emojis=use_emojis))
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(level)
        root_logger.handlers.clear()
        root_logger.addHandler(handler)
        
        # Reduce noise from third-party libraries
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("telegram").setLevel(logging.WARNING)
        logging.getLogger("asyncpg").setLevel(logging.WARNING)
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        
        cls._initialized = True
    
    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """
        Get or create a logger with the given name.
        
        Args:
            name: Logger name (usually module name)
            
        Returns:
            Configured logger instance
        """
        if name not in cls._loggers:
            cls._loggers[name] = logging.getLogger(name)
        return cls._loggers[name]


# ============================================================
# 📦 Pre-configured Logger Instances
# ============================================================

def setup_logging(debug: bool = False) -> None:
    """
    Initialize the logging system.
    
    Args:
        debug: Enable debug level logging
    """
    level = logging.DEBUG if debug else logging.INFO
    LoggerFactory.setup(level=level)


# Application logger for general info/debug messages
app_logger = LoggerFactory.get_logger("🎴 CardBot")

# Error logger for exceptions and errors
error_logger = LoggerFactory.get_logger("🚨 Error")


# ============================================================
# 📊 Specialized Logging Functions
# ============================================================

def log_startup(message: str) -> None:
    """Log startup-related messages with special formatting."""
    app_logger.info(f"🚀 {message}")


def log_shutdown(message: str) -> None:
    """Log shutdown-related messages."""
    app_logger.info(f"🛑 {message}")


def log_database(message: str) -> None:
    """Log database-related messages."""
    app_logger.info(f"🗄️ {message}")


def log_webhook(message: str) -> None:
    """Log webhook-related messages."""
    app_logger.info(f"🌐 {message}")


def log_command(user_id: int, command: str, chat_id: int) -> None:
    """
    Log a command execution.
    
    Args:
        user_id: Telegram user ID
        command: Command name
        chat_id: Chat ID where command was executed
    """
    app_logger.info(f"📨 Command /{command} from user {user_id} in chat {chat_id}")


def log_card_catch(user_id: int, card_name: str, rarity: str) -> None:
    """
    Log when a user catches a card.
    
    Args:
        user_id: User who caught the card
        card_name: Name of the caught card
        rarity: Card rarity
    """
    app_logger.info(f"🎯 User {user_id} caught {card_name} ({rarity})")


def log_error_with_context(
    error: Exception,
    context: str,
    user_id: Optional[int] = None,
    chat_id: Optional[int] = None
) -> None:
    """
    Log an error with additional context.
    
    Args:
        error: The exception that occurred
        context: Description of what was happening
        user_id: Related user ID (optional)
        chat_id: Related chat ID (optional)
    """
    context_parts = [f"Context: {context}"]
    if user_id:
        context_parts.append(f"User: {user_id}")
    if chat_id:
        context_parts.append(f"Chat: {chat_id}")
    
    error_logger.error(
        f"{' | '.join(context_parts)} | Error: {type(error).__name__}: {error}",
        exc_info=True
    )


# Initialize logging on module import with default settings
# Can be reconfigured later with setup_logging()
LoggerFactory.setup(level=logging.INFO)