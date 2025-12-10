# ============================================================
# 📁 File: db.py
# 📍 Location: telegram_card_bot/db.py
# 📝 Description: AsyncPG database operations with Railway support
# ============================================================

import asyncio
import ssl
from datetime import datetime
from typing import Optional, Any, List
from contextlib import asynccontextmanager
from urllib.parse import urlparse, parse_qs

import asyncpg
from asyncpg import Pool, Connection, Record
from asyncpg.exceptions import (
    DuplicateTableError,
    DuplicateObjectError,
    UndefinedTableError,
    PostgresError,
)

from config import Config
from utils.logger import app_logger, error_logger, log_database


# ============================================================
# 🗄️ Database Pool Management
# ============================================================

class Database:
    """
    Async database manager using asyncpg connection pool.
    
    Features:
    - Singleton pattern for single database instance
    - Railway-compatible SSL handling
    - Connection retry logic
    - Safe connection checking
    """
    
    _pool: Optional[Pool] = None
    _instance: Optional["Database"] = None
    
    def __new__(cls) -> "Database":
        """Singleton pattern to ensure single database instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @property
    def pool(self) -> Pool:
        """Get the connection pool, raising error if not initialized."""
        if self._pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        return self._pool
    
    @property
    def is_connected(self) -> bool:
        """Check if database is connected."""
        return self._pool is not None
    
    def _parse_database_url(self) -> dict:
        """
        Parse DATABASE_URL and extract connection parameters.
        Handles Railway's postgres:// vs postgresql:// difference.
        """
        url = Config.DATABASE_URL
        
        # Railway uses postgres:// but asyncpg needs postgresql://
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        
        return {
            "host": parsed.hostname,
            "port": parsed.port or 5432,
            "user": parsed.username,
            "password": parsed.password,
            "database": parsed.path.lstrip("/"),
            "ssl": "sslmode" in query_params or "require" in str(query_params.get("sslmode", [])),
        }
    
    async def connect(self, max_retries: int = 3, retry_delay: int = 2) -> bool:
        """
        Initialize the database connection pool with retry logic.
        
        Args:
            max_retries: Maximum connection attempts
            retry_delay: Seconds between retries
            
        Returns:
            True if connected successfully, False otherwise
        """
        if self._pool is not None:
            log_database("Connection pool already exists")
            return True
        
        # Check if DATABASE_URL is configured
        if not Config.DATABASE_URL or Config.DATABASE_URL == "postgresql://user:password@localhost:5432/cardbot":
            error_logger.warning(
                "⚠️ DATABASE_URL not configured! "
                "Please add a PostgreSQL database on Railway."
            )
            return False
        
        # Parse connection parameters
        db_params = self._parse_database_url()
        
        log_database(f"Connecting to database at {db_params['host']}:{db_params['port']}...")
        
        # SSL context for Railway (required for external connections)
        ssl_context = None
        if db_params.get("ssl") or "railway" in str(db_params.get("host", "")):
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            log_database("Using SSL connection")
        
        # Prepare DSN
        dsn = Config.DATABASE_URL
        if dsn.startswith("postgres://"):
            dsn = dsn.replace("postgres://", "postgresql://", 1)
        
        # Retry loop for connection
        for attempt in range(1, max_retries + 1):
            try:
                log_database(f"Connection attempt {attempt}/{max_retries}...")
                
                self._pool = await asyncpg.create_pool(
                    dsn=dsn,
                    min_size=Config.DB_MIN_CONNECTIONS,
                    max_size=Config.DB_MAX_CONNECTIONS,
                    command_timeout=60,
                    ssl=ssl_context,
                )
                
                # Test the connection
                async with self._pool.acquire() as conn:
                    await conn.execute("SELECT 1")
                
                log_database(
                    f"✅ Database connected! "
                    f"(pool: {Config.DB_MIN_CONNECTIONS}-{Config.DB_MAX_CONNECTIONS})"
                )
                return True
                
            except asyncpg.InvalidPasswordError as e:
                error_logger.error(f"❌ Database authentication failed: {e}")
                return False
                
            except asyncpg.InvalidCatalogNameError as e:
                error_logger.error(f"❌ Database does not exist: {e}")
                return False
                
            except Exception as e:
                error_logger.error(
                    f"Connection attempt {attempt} failed: {type(e).__name__}: {e}"
                )
                
                if attempt < max_retries:
                    log_database(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                else:
                    error_logger.error(
                        f"❌ Failed to connect after {max_retries} attempts. "
                        f"Check your DATABASE_URL configuration."
                    )
                    return False
        
        return False
    
    async def disconnect(self) -> None:
        """Close the database connection pool."""
        if self._pool is not None:
            log_database("Closing database pool...")
            await self._pool.close()
            self._pool = None
            log_database("✅ Database pool closed")
    
    @asynccontextmanager
    async def acquire(self):
        """
        Context manager for acquiring a connection from the pool.
        
        Usage:
            async with db.acquire() as conn:
                result = await conn.fetch("SELECT * FROM users")
        """
        if not self.is_connected:
            raise RuntimeError("Database not connected")
        async with self.pool.acquire() as connection:
            yield connection
    
    async def execute(self, query: str, *args) -> str:
        """Execute a query without returning results."""
        if not self.is_connected:
            raise RuntimeError("Database not connected")
        async with self.acquire() as conn:
            return await conn.execute(query, *args)
    
    async def fetch(self, query: str, *args) -> List[Record]:
        """Execute a query and return all results."""
        if not self.is_connected:
            raise RuntimeError("Database not connected")
        async with self.acquire() as conn:
            return await conn.fetch(query, *args)
    
    async def fetchrow(self, query: str, *args) -> Optional[Record]:
        """Execute a query and return a single row."""
        if not self.is_connected:
            raise RuntimeError("Database not connected")
        async with self.acquire() as conn:
            return await conn.fetchrow(query, *args)
    
    async def fetchval(self, query: str, *args) -> Any:
        """Execute a query and return a single value."""
        if not self.is_connected:
            raise RuntimeError("Database not connected")
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args)


# Global database instance
db = Database()


# ============================================================
# 🏗️ Schema Initialization
# ============================================================

async def init_db(pool: Optional[Pool] = None) -> bool:
    """
    Initialize database schema - create tables if they don't exist.
    
    This function is idempotent - it can be run multiple times safely.
    It handles existing tables, constraints, and indexes gracefully.
    
    Args:
        pool: Optional asyncpg pool (uses global db if not provided)
        
    Returns:
        True if successful, False otherwise
    """
    if not db.is_connected:
        log_database("⚠️ Cannot initialize schema - database not connected")
        return False
    
    log_database("Initializing database schema...")
    
    try:
        # ========================================
        # 1. Create Users Table
        # ========================================
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username VARCHAR(255),
                first_name VARCHAR(255),
                last_name VARCHAR(255),
                coins INTEGER DEFAULT 0,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                is_banned BOOLEAN DEFAULT FALSE,
                ban_reason TEXT,
                total_catches INTEGER DEFAULT 0,
                daily_streak INTEGER DEFAULT 0,
                last_daily TIMESTAMP WITH TIME ZONE,
                favorite_card_id INTEGER,
                bio TEXT
            )
        """)
        log_database("✅ Users table ready")
        
        # ========================================
        # 2. Create Cards Table
        # ========================================
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cards (
                card_id SERIAL PRIMARY KEY,
                anime VARCHAR(255) NOT NULL,
                character_name VARCHAR(255) NOT NULL,
                rarity INTEGER NOT NULL CHECK (rarity BETWEEN 1 AND 11),
                photo_file_id TEXT NOT NULL,
                uploader_id BIGINT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                is_active BOOLEAN DEFAULT TRUE,
                total_caught INTEGER DEFAULT 0,
                description TEXT,
                tags TEXT[]
            )
        """)
        log_database("✅ Cards table ready")
        
        # ========================================
        # 3. Create Collections Table
        # ========================================
        await db.execute("""
            CREATE TABLE IF NOT EXISTS collections (
                collection_id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                card_id INTEGER NOT NULL,
                caught_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                caught_in_group BIGINT,
                is_favorite BOOLEAN DEFAULT FALSE,
                trade_locked BOOLEAN DEFAULT FALSE,
                quantity INTEGER DEFAULT 1
            )
        """)
        log_database("✅ Collections table ready")
        
        # ========================================
        # 4. Create Groups Table
        # ========================================
        await db.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                group_id BIGINT PRIMARY KEY,
                group_name VARCHAR(255),
                is_active BOOLEAN DEFAULT TRUE,
                spawn_enabled BOOLEAN DEFAULT TRUE,
                cooldown_seconds INTEGER DEFAULT 60,
                last_spawn TIMESTAMP WITH TIME ZONE,
                current_card_id INTEGER,
                current_card_message_id BIGINT,
                total_spawns INTEGER DEFAULT 0,
                total_catches INTEGER DEFAULT 0,
                joined_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                settings JSONB DEFAULT '{}'::jsonb
            )
        """)
        log_database("✅ Groups table ready")
        
        # ========================================
        # 5. Add Constraints (safely ignore if exist)
        # ========================================
        
        # Unique constraint: cards (anime + character_name)
        try:
            await db.execute("""
                ALTER TABLE cards 
                ADD CONSTRAINT cards_anime_character_unique 
                UNIQUE (anime, character_name)
            """)
        except (DuplicateTableError, DuplicateObjectError, PostgresError):
            pass  # Constraint already exists
        
        # Unique constraint: collections (user_id + card_id)
        try:
            await db.execute("""
                ALTER TABLE collections 
                ADD CONSTRAINT collections_user_card_unique 
                UNIQUE (user_id, card_id)
            """)
        except (DuplicateTableError, DuplicateObjectError, PostgresError):
            pass  # Constraint already exists
        
        # Foreign key: collections.user_id -> users.user_id
        try:
            await db.execute("""
                ALTER TABLE collections 
                ADD CONSTRAINT fk_collections_user 
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            """)
        except (DuplicateTableError, DuplicateObjectError, PostgresError):
            pass  # Constraint already exists
        
        # Foreign key: collections.card_id -> cards.card_id
        try:
            await db.execute("""
                ALTER TABLE collections 
                ADD CONSTRAINT fk_collections_card 
                FOREIGN KEY (card_id) REFERENCES cards(card_id) ON DELETE CASCADE
            """)
        except (DuplicateTableError, DuplicateObjectError, PostgresError):
            pass  # Constraint already exists
        
        log_database("✅ Constraints ready")
        
        # ========================================
        # 6. Create Indexes (IF NOT EXISTS handles duplicates)
        # ========================================
        
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_collections_user_id 
            ON collections(user_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_collections_card_id 
            ON collections(card_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_cards_rarity 
            ON cards(rarity)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_cards_anime 
            ON cards(anime)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_cards_active 
            ON cards(is_active) WHERE is_active = TRUE
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_groups_active 
            ON groups(is_active) WHERE is_active = TRUE
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_banned 
            ON users(is_banned) WHERE is_banned = FALSE
        """)
        
        log_database("✅ Indexes ready")
        log_database("✅ Database schema initialized successfully")
        return True
        
    except Exception as e:
        error_logger.error(f"Failed to initialize schema: {e}", exc_info=True)
        return False


# ============================================================
# 👤 User Operations
# ============================================================

async def ensure_user(
    pool: Optional[Pool],
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None
) -> Optional[Record]:
    """
    Ensure a user exists in the database, creating if necessary.
    
    Args:
        pool: Database pool (uses global db if None)
        user_id: Telegram user ID
        username: Telegram username (optional)
        first_name: User's first name
        last_name: User's last name
        
    Returns:
        The user record (existing or newly created)
    """
    if not db.is_connected:
        return None
    
    query = """
        INSERT INTO users (user_id, username, first_name, last_name)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id) DO UPDATE SET
            username = COALESCE($2, users.username),
            first_name = COALESCE($3, users.first_name),
            last_name = COALESCE($4, users.last_name),
            updated_at = NOW()
        RETURNING *
    """
    return await db.fetchrow(query, user_id, username, first_name, last_name)


async def get_user_by_id(
    pool: Optional[Pool],
    user_id: int
) -> Optional[Record]:
    """
    Get a user by their Telegram user ID.
    
    Args:
        pool: Database pool (uses global db if None)
        user_id: Telegram user ID
        
    Returns:
        User record if found, None otherwise
    """
    if not db.is_connected:
        return None
    
    query = "SELECT * FROM users WHERE user_id = $1"
    return await db.fetchrow(query, user_id)


async def update_user_stats(
    pool: Optional[Pool],
    user_id: int,
    coins_delta: int = 0,
    xp_delta: int = 0,
    catches_delta: int = 0
) -> Optional[Record]:
    """
    Update user statistics.
    
    Args:
        pool: Database pool
        user_id: User to update
        coins_delta: Amount to add to coins (can be negative)
        xp_delta: Amount to add to XP
        catches_delta: Amount to add to total catches
        
    Returns:
        Updated user record
    """
    if not db.is_connected:
        return None
    
    query = """
        UPDATE users SET
            coins = coins + $2,
            xp = xp + $3,
            total_catches = total_catches + $4,
            updated_at = NOW()
        WHERE user_id = $1
        RETURNING *
    """
    return await db.fetchrow(query, user_id, coins_delta, xp_delta, catches_delta)


async def get_user_leaderboard(
    pool: Optional[Pool],
    limit: int = 10,
    order_by: str = "total_catches"
) -> List[Record]:
    """
    Get the top users by various metrics.
    
    Args:
        pool: Database pool
        limit: Number of users to return
        order_by: Column to sort by (total_catches, coins, xp, level)
        
    Returns:
        List of user records
    """
    if not db.is_connected:
        return []
    
    valid_columns = {"total_catches", "coins", "xp", "level"}
    if order_by not in valid_columns:
        order_by = "total_catches"
    
    query = f"""
        SELECT user_id, username, first_name, {order_by}, level
        FROM users
        WHERE is_banned = FALSE
        ORDER BY {order_by} DESC
        LIMIT $1
    """
    return await db.fetch(query, limit)


async def get_all_users(pool: Optional[Pool]) -> List[Record]:
    """
    Get all non-banned users.
    
    Returns:
        List of user records
    """
    if not db.is_connected:
        return []
    
    query = "SELECT * FROM users WHERE is_banned = FALSE"
    return await db.fetch(query)


# ============================================================
# 🎴 Card Operations
# ============================================================

async def add_card(
    pool: Optional[Pool],
    anime: str,
    character: str,
    rarity: int,
    photo_file_id: str,
    uploader_id: int,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None
) -> Optional[Record]:
    """
    Add a new card to the database.
    
    Args:
        pool: Database pool
        anime: Anime/series name
        character: Character name
        rarity: Rarity level (1-11)
        photo_file_id: Telegram file ID for the photo
        uploader_id: User ID who uploaded the card
        description: Optional card description
        tags: Optional list of tags
        
    Returns:
        The created card record, or None if it already exists
    """
    if not db.is_connected:
        return None
    
    # Validate rarity
    if not 1 <= rarity <= 11:
        raise ValueError(f"Invalid rarity: {rarity}. Must be between 1 and 11.")
    
    query = """
        INSERT INTO cards (anime, character_name, rarity, photo_file_id, uploader_id, description, tags)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (anime, character_name) DO NOTHING
        RETURNING *
    """
    return await db.fetchrow(
        query, anime, character, rarity, photo_file_id, uploader_id, description, tags or []
    )


async def get_card_by_id(
    pool: Optional[Pool],
    card_id: int
) -> Optional[Record]:
    """
    Get a card by its ID.
    
    Args:
        pool: Database pool
        card_id: Card ID to look up
        
    Returns:
        Card record if found
    """
    if not db.is_connected:
        return None
    
    query = "SELECT * FROM cards WHERE card_id = $1 AND is_active = TRUE"
    return await db.fetchrow(query, card_id)


async def get_cards_by_ids(
    pool: Optional[Pool],
    card_ids: List[int]
) -> List[Record]:
    """
    Get multiple cards by their IDs.
    
    Args:
        pool: Database pool
        card_ids: List of card IDs to look up
        
    Returns:
        List of card records
    """
    if not db.is_connected or not card_ids:
        return []
    
    query = """
        SELECT * FROM cards 
        WHERE card_id = ANY($1) AND is_active = TRUE
        ORDER BY rarity DESC, character_name
    """
    return await db.fetch(query, card_ids)


async def get_random_card(
    pool: Optional[Pool],
    rarity: Optional[int] = None
) -> Optional[Record]:
    """
    Get a random active card, optionally filtered by rarity.
    
    Args:
        pool: Database pool
        rarity: Optional rarity filter
        
    Returns:
        Random card record
    """
    if not db.is_connected:
        return None
    
    if rarity:
        query = """
            SELECT * FROM cards 
            WHERE is_active = TRUE AND rarity = $1
            ORDER BY RANDOM() 
            LIMIT 1
        """
        return await db.fetchrow(query, rarity)
    else:
        query = """
            SELECT * FROM cards 
            WHERE is_active = TRUE
            ORDER BY RANDOM() 
            LIMIT 1
        """
        return await db.fetchrow(query)


async def search_cards(
    pool: Optional[Pool],
    search_term: str,
    limit: int = 20
) -> List[Record]:
    """
    Search cards by anime or character name.
    
    Args:
        pool: Database pool
        search_term: Search query
        limit: Maximum results
        
    Returns:
        List of matching cards
    """
    if not db.is_connected:
        return []
    
    query = """
        SELECT * FROM cards
        WHERE is_active = TRUE
          AND (
            anime ILIKE $1 
            OR character_name ILIKE $1
          )
        ORDER BY rarity DESC, character_name
        LIMIT $2
    """
    search_pattern = f"%{search_term}%"
    return await db.fetch(query, search_pattern, limit)


async def get_card_count(pool: Optional[Pool]) -> int:
    """Get total number of active cards."""
    if not db.is_connected:
        return 0
    
    query = "SELECT COUNT(*) FROM cards WHERE is_active = TRUE"
    result = await db.fetchval(query)
    return result or 0


async def increment_card_caught(
    pool: Optional[Pool],
    card_id: int
) -> None:
    """Increment the total_caught counter for a card."""
    if not db.is_connected:
        return
    
    query = "UPDATE cards SET total_caught = total_caught + 1 WHERE card_id = $1"
    await db.execute(query, card_id)


async def delete_card(
    pool: Optional[Pool],
    card_id: int
) -> bool:
    """
    Soft delete a card (set is_active = FALSE).
    
    Args:
        pool: Database pool
        card_id: Card to delete
        
    Returns:
        True if card was deleted
    """
    if not db.is_connected:
        return False
    
    query = "UPDATE cards SET is_active = FALSE WHERE card_id = $1 RETURNING card_id"
    result = await db.fetchrow(query, card_id)
    return result is not None


# ============================================================
# 📦 Collection Operations
# ============================================================

async def add_to_collection(
    pool: Optional[Pool],
    user_id: int,
    card_id: int,
    group_id: Optional[int] = None
) -> Optional[Record]:
    """
    Add a card to a user's collection or increment quantity.
    
    Args:
        pool: Database pool
        user_id: User who caught the card
        card_id: Card that was caught
        group_id: Group where the card was caught
        
    Returns:
        Collection record
    """
    if not db.is_connected:
        return None
    
    query = """
        INSERT INTO collections (user_id, card_id, caught_in_group)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id, card_id) DO UPDATE SET
            quantity = collections.quantity + 1,
            caught_at = NOW()
        RETURNING *
    """
    return await db.fetchrow(query, user_id, card_id, group_id)


async def get_user_collection(
    pool: Optional[Pool],
    user_id: int,
    page: int = 1,
    per_page: int = 10,
    rarity_filter: Optional[int] = None
) -> tuple[List[Record], int]:
    """
    Get a user's card collection with pagination.
    
    Args:
        pool: Database pool
        user_id: User ID
        page: Page number (1-indexed)
        per_page: Cards per page
        rarity_filter: Optional rarity filter
        
    Returns:
        Tuple of (cards list, total count)
    """
    if not db.is_connected:
        return [], 0
    
    offset = (page - 1) * per_page
    
    if rarity_filter:
        count_query = """
            SELECT COUNT(*) FROM collections c
            JOIN cards ca ON c.card_id = ca.card_id
            WHERE c.user_id = $1 AND ca.rarity = $2 AND ca.is_active = TRUE
        """
        main_query = """
            SELECT c.*, ca.anime, ca.character_name, ca.rarity, 
                   ca.photo_file_id, ca.description
            FROM collections c
            JOIN cards ca ON c.card_id = ca.card_id
            WHERE c.user_id = $1 AND ca.rarity = $4 AND ca.is_active = TRUE
            ORDER BY ca.rarity DESC, ca.character_name
            LIMIT $2 OFFSET $3
        """
        total = await db.fetchval(count_query, user_id, rarity_filter)
        cards = await db.fetch(main_query, user_id, per_page, offset, rarity_filter)
    else:
        count_query = """
            SELECT COUNT(*) FROM collections c
            JOIN cards ca ON c.card_id = ca.card_id
            WHERE c.user_id = $1 AND ca.is_active = TRUE
        """
        main_query = """
            SELECT c.*, ca.anime, ca.character_name, ca.rarity, 
                   ca.photo_file_id, ca.description
            FROM collections c
            JOIN cards ca ON c.card_id = ca.card_id
            WHERE c.user_id = $1 AND ca.is_active = TRUE
            ORDER BY ca.rarity DESC, ca.character_name
            LIMIT $2 OFFSET $3
        """
        total = await db.fetchval(count_query, user_id)
        cards = await db.fetch(main_query, user_id, per_page, offset)
    
    return cards, total or 0


async def get_user_collection_stats(
    pool: Optional[Pool],
    user_id: int
) -> dict:
    """
    Get statistics about a user's collection.
    
    Args:
        pool: Database pool
        user_id: User ID
        
    Returns:
        Dictionary with collection statistics
    """
    if not db.is_connected:
        return {
            "total_unique": 0,
            "total_cards": 0,
            "mythical_plus": 0,
            "legendary_count": 0,
        }
    
    query = """
        SELECT 
            COUNT(*) as total_unique,
            COALESCE(SUM(c.quantity), 0) as total_cards,
            COUNT(*) FILTER (WHERE ca.rarity >= 9) as mythical_plus,
            COUNT(*) FILTER (WHERE ca.rarity = 11) as legendary_count
        FROM collections c
        JOIN cards ca ON c.card_id = ca.card_id
        WHERE c.user_id = $1 AND ca.is_active = TRUE
    """
    
    row = await db.fetchrow(query, user_id)
    
    if row:
        return {
            "total_unique": row["total_unique"] or 0,
            "total_cards": int(row["total_cards"] or 0),
            "mythical_plus": row["mythical_plus"] or 0,
            "legendary_count": row["legendary_count"] or 0,
        }
    return {
        "total_unique": 0,
        "total_cards": 0,
        "mythical_plus": 0,
        "legendary_count": 0,
    }


async def check_user_has_card(
    pool: Optional[Pool],
    user_id: int,
    card_id: int
) -> bool:
    """Check if a user has a specific card in their collection."""
    if not db.is_connected:
        return False
    
    query = """
        SELECT EXISTS(
            SELECT 1 FROM collections 
            WHERE user_id = $1 AND card_id = $2
        )
    """
    return await db.fetchval(query, user_id, card_id)


async def toggle_favorite(
    pool: Optional[Pool],
    user_id: int,
    card_id: int
) -> Optional[bool]:
    """
    Toggle favorite status for a card in user's collection.
    
    Returns:
        New favorite status, or None if not in collection
    """
    if not db.is_connected:
        return None
    
    query = """
        UPDATE collections 
        SET is_favorite = NOT is_favorite
        WHERE user_id = $1 AND card_id = $2
        RETURNING is_favorite
    """
    return await db.fetchval(query, user_id, card_id)


# ============================================================
# 👥 Group Operations
# ============================================================

async def ensure_group(
    pool: Optional[Pool],
    group_id: int,
    group_name: Optional[str] = None
) -> Optional[Record]:
    """
    Ensure a group exists in the database.
    
    Args:
        pool: Database pool
        group_id: Telegram chat ID
        group_name: Group title
        
    Returns:
        Group record
    """
    if not db.is_connected:
        return None
    
    query = """
        INSERT INTO groups (group_id, group_name)
        VALUES ($1, $2)
        ON CONFLICT (group_id) DO UPDATE SET
            group_name = COALESCE($2, groups.group_name),
            is_active = TRUE
        RETURNING *
    """
    return await db.fetchrow(query, group_id, group_name)


async def get_all_groups(
    pool: Optional[Pool],
    active_only: bool = True
) -> List[Record]:
    """
    Get all registered groups.
    
    Args:
        pool: Database pool
        active_only: Only return active groups
        
    Returns:
        List of group records
    """
    if not db.is_connected:
        return []
    
    if active_only:
        query = "SELECT * FROM groups WHERE is_active = TRUE ORDER BY joined_at"
    else:
        query = "SELECT * FROM groups ORDER BY joined_at"
    
    return await db.fetch(query)


async def get_group_by_id(
    pool: Optional[Pool],
    group_id: int
) -> Optional[Record]:
    """Get a specific group by ID."""
    if not db.is_connected:
        return None
    
    query = "SELECT * FROM groups WHERE group_id = $1"
    return await db.fetchrow(query, group_id)


async def update_group_spawn(
    pool: Optional[Pool],
    group_id: int,
    card_id: int,
    message_id: int
) -> None:
    """
    Update the current spawned card in a group.
    
    Args:
        pool: Database pool
        group_id: Group where card spawned
        card_id: The spawned card
        message_id: Message ID of the spawn message
    """
    if not db.is_connected:
        return
    
    query = """
        UPDATE groups SET
            current_card_id = $2,
            current_card_message_id = $3,
            last_spawn = NOW(),
            total_spawns = total_spawns + 1
        WHERE group_id = $1
    """
    await db.execute(query, group_id, card_id, message_id)


async def clear_group_spawn(
    pool: Optional[Pool],
    group_id: int
) -> None:
    """Clear the current spawned card in a group after it's caught."""
    if not db.is_connected:
        return
    
    query = """
        UPDATE groups SET
            current_card_id = NULL,
            current_card_message_id = NULL,
            total_catches = total_catches + 1
        WHERE group_id = $1
    """
    await db.execute(query, group_id)


async def update_group_settings(
    pool: Optional[Pool],
    group_id: int,
    spawn_enabled: Optional[bool] = None,
    cooldown_seconds: Optional[int] = None
) -> Optional[Record]:
    """
    Update group settings.
    
    Args:
        pool: Database pool
        group_id: Group to update
        spawn_enabled: Enable/disable spawning
        cooldown_seconds: Cooldown between spawns
        
    Returns:
        Updated group record
    """
    if not db.is_connected:
        return None
    
    updates = []
    values = [group_id]
    param_count = 1
    
    if spawn_enabled is not None:
        param_count += 1
        updates.append(f"spawn_enabled = ${param_count}")
        values.append(spawn_enabled)
    
    if cooldown_seconds is not None:
        param_count += 1
        updates.append(f"cooldown_seconds = ${param_count}")
        values.append(cooldown_seconds)
    
    if not updates:
        return await get_group_by_id(pool, group_id)
    
    query = f"""
        UPDATE groups SET {', '.join(updates)}
        WHERE group_id = $1
        RETURNING *
    """
    return await db.fetchrow(query, *values)


async def deactivate_group(
    pool: Optional[Pool],
    group_id: int
) -> None:
    """Mark a group as inactive (bot left/kicked)."""
    if not db.is_connected:
        return
    
    query = "UPDATE groups SET is_active = FALSE WHERE group_id = $1"
    await db.execute(query, group_id)


# ============================================================
# 📊 Statistics & Analytics
# ============================================================

async def get_global_stats(pool: Optional[Pool]) -> dict:
    """
    Get global bot statistics.
    
    Returns:
        Dictionary with global stats
    """
    if not db.is_connected:
        return {
            "total_users": 0,
            "total_cards": 0,
            "total_catches": 0,
            "active_groups": 0,
        }
    
    try:
        stats = {}
        
        # Total users
        stats["total_users"] = await db.fetchval(
            "SELECT COUNT(*) FROM users"
        ) or 0
        
        # Total active cards
        stats["total_cards"] = await db.fetchval(
            "SELECT COUNT(*) FROM cards WHERE is_active = TRUE"
        ) or 0
        
        # Total catches
        stats["total_catches"] = int(await db.fetchval(
            "SELECT COALESCE(SUM(total_catches), 0) FROM users"
        ) or 0)
        
        # Active groups
        stats["active_groups"] = await db.fetchval(
            "SELECT COUNT(*) FROM groups WHERE is_active = TRUE"
        ) or 0
        
        return stats
        
    except Exception as e:
        error_logger.error(f"Error getting global stats: {e}")
        return {
            "total_users": 0,
            "total_cards": 0,
            "total_catches": 0,
            "active_groups": 0,
        }


async def get_rarity_distribution(pool: Optional[Pool]) -> List[Record]:
    """
    Get the distribution of cards by rarity.
    
    Returns:
        List of records with rarity and count
    """
    if not db.is_connected:
        return []
    
    query = """
        SELECT rarity, COUNT(*) as count
        FROM cards
        WHERE is_active = TRUE
        GROUP BY rarity
        ORDER BY rarity
    """
    return await db.fetch(query)


async def get_top_catchers(
    pool: Optional[Pool],
    limit: int = 10
) -> List[Record]:
    """
    Get top users by total catches.
    
    Returns:
        List of user records
    """
    if not db.is_connected:
        return []
    
    query = """
        SELECT user_id, username, first_name, total_catches, level, coins
        FROM users
        WHERE is_banned = FALSE AND total_catches > 0
        ORDER BY total_catches DESC
        LIMIT $1
    """
    return await db.fetch(query, limit)


async def get_rarest_cards(
    pool: Optional[Pool],
    limit: int = 10
) -> List[Record]:
    """
    Get the rarest cards in the database.
    
    Returns:
        List of card records
    """
    if not db.is_connected:
        return []
    
    query = """
        SELECT * FROM cards
        WHERE is_active = TRUE
        ORDER BY rarity DESC, total_caught ASC
        LIMIT $1
    """
    return await db.fetch(query, limit)


# ============================================================
# 🛠️ Maintenance Functions
# ============================================================

async def cleanup_inactive_groups(
    pool: Optional[Pool],
    days_inactive: int = 30
) -> int:
    """
    Mark groups as inactive if no activity for specified days.
    
    Args:
        pool: Database pool
        days_inactive: Days of inactivity threshold
        
    Returns:
        Number of groups marked inactive
    """
    if not db.is_connected:
        return 0
    
    query = f"""
        UPDATE groups SET is_active = FALSE
        WHERE last_spawn < NOW() - INTERVAL '{days_inactive} days'
          AND is_active = TRUE
        RETURNING group_id
    """
    result = await db.fetch(query)
    return len(result)


async def health_check(pool: Optional[Pool]) -> bool:
    """
    Perform a database health check.
    
    Returns:
        True if database is healthy
    """
    if not db.is_connected:
        return False
    
    try:
        await db.fetchval("SELECT 1")
        return True
    except Exception as e:
        error_logger.error(f"Database health check failed: {e}")
        return False


async def get_database_size(pool: Optional[Pool]) -> Optional[str]:
    """
    Get the total database size.
    
    Returns:
        Human-readable size string
    """
    if not db.is_connected:
        return None
    
    try:
        query = "SELECT pg_size_pretty(pg_database_size(current_database()))"
        return await db.fetchval(query)
    except Exception:
        return None


async def get_table_counts(pool: Optional[Pool]) -> dict:
    """
    Get row counts for all tables.
    
    Returns:
        Dictionary with table names and counts
    """
    if not db.is_connected:
        return {}
    
    try:
        return {
            "users": await db.fetchval("SELECT COUNT(*) FROM users") or 0,
            "cards": await db.fetchval("SELECT COUNT(*) FROM cards") or 0,
            "collections": await db.fetchval("SELECT COUNT(*) FROM collections") or 0,
            "groups": await db.fetchval("SELECT COUNT(*) FROM groups") or 0,
        }
    except Exception:
        return {}


-- ============================================================
-- Part 4: Database Migration SQL
-- Add to your PostgreSQL database
-- ============================================================

-- ========================================
-- 1. TRADES TABLE - Store trade requests
-- ========================================
CREATE TABLE IF NOT EXISTS trades (
    trade_id SERIAL PRIMARY KEY,
    from_user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    to_user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    offered_card_id INTEGER NOT NULL REFERENCES cards(card_id) ON DELETE CASCADE,
    requested_card_id INTEGER REFERENCES cards(card_id) ON DELETE SET NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    
    -- Constraints
    CONSTRAINT valid_status CHECK (status IN ('pending', 'accepted', 'rejected', 'cancelled', 'completed', 'failed')),
    CONSTRAINT no_self_trade CHECK (from_user_id != to_user_id)
);

-- ========================================
-- 2. STATS TABLE - Aggregated statistics
-- ========================================
CREATE TABLE IF NOT EXISTS stats (
    stat_id SERIAL PRIMARY KEY,
    stat_key VARCHAR(100) UNIQUE NOT NULL,
    stat_value BIGINT DEFAULT 0,
    description TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ========================================
-- 3. TRADE HISTORY TABLE - Completed trades log
-- ========================================
CREATE TABLE IF NOT EXISTS trade_history (
    history_id SERIAL PRIMARY KEY,
    trade_id INTEGER NOT NULL,
    from_user_id BIGINT NOT NULL,
    to_user_id BIGINT NOT NULL,
    offered_card_id INTEGER NOT NULL,
    requested_card_id INTEGER,
    completed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ========================================
-- 4. INDEXES for Performance
-- ========================================

-- Trades indexes
CREATE INDEX IF NOT EXISTS idx_trades_from_user ON trades(from_user_id);
CREATE INDEX IF NOT EXISTS idx_trades_to_user ON trades(to_user_id);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_pending ON trades(to_user_id, status) WHERE status = 'pending';

-- Stats index
CREATE INDEX IF NOT EXISTS idx_stats_key ON stats(stat_key);

-- ========================================
-- 5. INSERT DEFAULT STATS
-- ========================================
INSERT INTO stats (stat_key, stat_value, description) VALUES
    ('total_trades', 0, 'Total completed trades'),
    ('total_catches_today', 0, 'Cards caught today'),
    ('total_spawns_today', 0, 'Cards spawned today'),
    ('last_stats_update', 0, 'Timestamp of last stats update')
ON CONFLICT (stat_key) DO NOTHING;

-- ========================================
-- 6. FUNCTION: Update trade timestamp
-- ========================================
CREATE OR REPLACE FUNCTION update_trade_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for trades table
DROP TRIGGER IF EXISTS trigger_update_trade_timestamp ON trades;
CREATE TRIGGER trigger_update_trade_timestamp
    BEFORE UPDATE ON trades
    FOR EACH ROW
    EXECUTE FUNCTION update_trade_timestamp();