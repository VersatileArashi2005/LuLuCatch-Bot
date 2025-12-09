# ============================================================
# 📁 File: db.py
# 📍 Location: telegram_card_bot/db.py
# 📝 Description: AsyncPG database operations for the card bot
# ============================================================

import asyncio
from datetime import datetime
from typing import Optional, Any
from contextlib import asynccontextmanager

import asyncpg
from asyncpg import Pool, Connection, Record

from config import Config
from utils.logger import app_logger, error_logger, log_database


# ============================================================
# 🗄️ Database Pool Management
# ============================================================

class Database:
    """
    Async database manager using asyncpg connection pool.
    
    Provides methods for all database operations needed by the bot.
    Uses connection pooling for efficient resource management.
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
    
    async def connect(self) -> None:
        """
        Initialize the database connection pool.
        
        Creates a connection pool with the configured min/max connections.
        Should be called during application startup.
        """
        if self._pool is not None:
            log_database("Connection pool already exists")
            return
        
        try:
            log_database(f"Connecting to database...")
            
            self._pool = await asyncpg.create_pool(
                dsn=Config.DATABASE_URL,
                min_size=Config.DB_MIN_CONNECTIONS,
                max_size=Config.DB_MAX_CONNECTIONS,
                command_timeout=60,
                # Custom type converters can be added here
            )
            
            log_database(f"✅ Database pool created (min={Config.DB_MIN_CONNECTIONS}, max={Config.DB_MAX_CONNECTIONS})")
            
        except Exception as e:
            error_logger.error(f"Failed to create database pool: {e}", exc_info=True)
            raise
    
    async def disconnect(self) -> None:
        """
        Close the database connection pool.
        
        Should be called during application shutdown.
        """
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
        async with self.pool.acquire() as connection:
            yield connection
    
    async def execute(self, query: str, *args) -> str:
        """Execute a query without returning results."""
        async with self.acquire() as conn:
            return await conn.execute(query, *args)
    
    async def fetch(self, query: str, *args) -> list[Record]:
        """Execute a query and return all results."""
        async with self.acquire() as conn:
            return await conn.fetch(query, *args)
    
    async def fetchrow(self, query: str, *args) -> Optional[Record]:
        """Execute a query and return a single row."""
        async with self.acquire() as conn:
            return await conn.fetchrow(query, *args)
    
    async def fetchval(self, query: str, *args) -> Any:
        """Execute a query and return a single value."""
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args)


# Global database instance
db = Database()


# ============================================================
# 🏗️ Schema Initialization
# ============================================================

async def init_db(pool: Optional[Pool] = None) -> None:
    """
    Initialize database schema - create tables if they don't exist.
    
    Args:
        pool: Optional asyncpg pool (uses global db if not provided)
        
    Creates the following tables:
        - users: Store user information
        - cards: Store card definitions
        - collections: Store user card collections
        - groups: Store group settings
    """
    log_database("Initializing database schema...")
    
    # Use provided pool or global database
    if pool:
        execute = pool.execute
    else:
        execute = db.execute
    
    # ========================================
    # Users Table
    # ========================================
    await execute("""
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
    
    # ========================================
    # Cards Table (Card Definitions)
    # ========================================
    await execute("""
        CREATE TABLE IF NOT EXISTS cards (
            card_id SERIAL PRIMARY KEY,
            anime VARCHAR(255) NOT NULL,
            character_name VARCHAR(255) NOT NULL,
            rarity INTEGER NOT NULL CHECK (rarity BETWEEN 1 AND 11),
            photo_file_id TEXT NOT NULL,
            uploader_id BIGINT REFERENCES users(user_id),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            is_active BOOLEAN DEFAULT TRUE,
            total_caught INTEGER DEFAULT 0,
            description TEXT,
            tags TEXT[],
            UNIQUE(anime, character_name)
        )
    """)
    
    # ========================================
    # Collections Table (User's Cards)
    # ========================================
    await execute("""
        CREATE TABLE IF NOT EXISTS collections (
            collection_id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            card_id INTEGER NOT NULL REFERENCES cards(card_id) ON DELETE CASCADE,
            caught_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            caught_in_group BIGINT,
            is_favorite BOOLEAN DEFAULT FALSE,
            trade_locked BOOLEAN DEFAULT FALSE,
            quantity INTEGER DEFAULT 1,
            UNIQUE(user_id, card_id)
        )
    """)
    
    # ========================================
    # Groups Table
    # ========================================
    await execute("""
        CREATE TABLE IF NOT EXISTS groups (
            group_id BIGINT PRIMARY KEY,
            group_name VARCHAR(255),
            is_active BOOLEAN DEFAULT TRUE,
            spawn_enabled BOOLEAN DEFAULT TRUE,
            cooldown_seconds INTEGER DEFAULT 60,
            last_spawn TIMESTAMP WITH TIME ZONE,
            current_card_id INTEGER REFERENCES cards(card_id),
            current_card_message_id BIGINT,
            total_spawns INTEGER DEFAULT 0,
            total_catches INTEGER DEFAULT 0,
            joined_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            settings JSONB DEFAULT '{}'::jsonb
        )
    """)
    
    # ========================================
    # Indexes for Performance
    # ========================================
    
    # Index on collections for faster user lookups
    await execute("""
        CREATE INDEX IF NOT EXISTS idx_collections_user_id 
        ON collections(user_id)
    """)
    
    # Index on collections for card lookups
    await execute("""
        CREATE INDEX IF NOT EXISTS idx_collections_card_id 
        ON collections(card_id)
    """)
    
    # Index on cards for rarity-based queries
    await execute("""
        CREATE INDEX IF NOT EXISTS idx_cards_rarity 
        ON cards(rarity)
    """)
    
    # Index on cards for anime lookups
    await execute("""
        CREATE INDEX IF NOT EXISTS idx_cards_anime 
        ON cards(anime)
    """)
    
    # Index on groups for active groups
    await execute("""
        CREATE INDEX IF NOT EXISTS idx_groups_active 
        ON groups(is_active) WHERE is_active = TRUE
    """)
    
    log_database("✅ Database schema initialized successfully")


# ============================================================
# 👤 User Operations
# ============================================================

async def ensure_user(
    pool: Optional[Pool],
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None
) -> Record:
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
    
    if pool:
        return await pool.fetchrow(query, user_id, username, first_name, last_name)
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
    query = "SELECT * FROM users WHERE user_id = $1"
    
    if pool:
        return await pool.fetchrow(query, user_id)
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
    query = """
        UPDATE users SET
            coins = coins + $2,
            xp = xp + $3,
            total_catches = total_catches + $4,
            updated_at = NOW()
        WHERE user_id = $1
        RETURNING *
    """
    
    if pool:
        return await pool.fetchrow(query, user_id, coins_delta, xp_delta, catches_delta)
    return await db.fetchrow(query, user_id, coins_delta, xp_delta, catches_delta)


async def get_user_leaderboard(
    pool: Optional[Pool],
    limit: int = 10,
    order_by: str = "total_catches"
) -> list[Record]:
    """
    Get the top users by various metrics.
    
    Args:
        pool: Database pool
        limit: Number of users to return
        order_by: Column to sort by (total_catches, coins, xp, level)
        
    Returns:
        List of user records
    """
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
    
    if pool:
        return await pool.fetch(query, limit)
    return await db.fetch(query, limit)


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
    tags: Optional[list[str]] = None
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
    # Validate rarity
    if not 1 <= rarity <= 11:
        raise ValueError(f"Invalid rarity: {rarity}. Must be between 1 and 11.")
    
    query = """
        INSERT INTO cards (anime, character_name, rarity, photo_file_id, uploader_id, description, tags)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (anime, character_name) DO NOTHING
        RETURNING *
    """
    
    if pool:
        return await pool.fetchrow(
            query, anime, character, rarity, photo_file_id, uploader_id, description, tags or []
        )
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
    query = "SELECT * FROM cards WHERE card_id = $1 AND is_active = TRUE"
    
    if pool:
        return await pool.fetchrow(query, card_id)
    return await db.fetchrow(query, card_id)


async def get_cards_by_ids(
    pool: Optional[Pool],
    card_ids: list[int]
) -> list[Record]:
    """
    Get multiple cards by their IDs.
    
    Args:
        pool: Database pool
        card_ids: List of card IDs to look up
        
    Returns:
        List of card records
    """
    if not card_ids:
        return []
    
    query = """
        SELECT * FROM cards 
        WHERE card_id = ANY($1) AND is_active = TRUE
        ORDER BY rarity DESC, character_name
    """
    
    if pool:
        return await pool.fetch(query, card_ids)
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
    if rarity:
        query = """
            SELECT * FROM cards 
            WHERE is_active = TRUE AND rarity = $1
            ORDER BY RANDOM() 
            LIMIT 1
        """
        if pool:
            return await pool.fetchrow(query, rarity)
        return await db.fetchrow(query, rarity)
    else:
        query = """
            SELECT * FROM cards 
            WHERE is_active = TRUE
            ORDER BY RANDOM() 
            LIMIT 1
        """
        if pool:
            return await pool.fetchrow(query)
        return await db.fetchrow(query)


async def search_cards(
    pool: Optional[Pool],
    search_term: str,
    limit: int = 20
) -> list[Record]:
    """
    Search cards by anime or character name.
    
    Args:
        pool: Database pool
        search_term: Search query
        limit: Maximum results
        
    Returns:
        List of matching cards
    """
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
    
    if pool:
        return await pool.fetch(query, search_pattern, limit)
    return await db.fetch(query, search_pattern, limit)


async def get_card_count(pool: Optional[Pool]) -> int:
    """Get total number of active cards."""
    query = "SELECT COUNT(*) FROM cards WHERE is_active = TRUE"
    
    if pool:
        return await pool.fetchval(query)
    return await db.fetchval(query)


async def increment_card_caught(
    pool: Optional[Pool],
    card_id: int
) -> None:
    """Increment the total_caught counter for a card."""
    query = "UPDATE cards SET total_caught = total_caught + 1 WHERE card_id = $1"
    
    if pool:
        await pool.execute(query, card_id)
    else:
        await db.execute(query, card_id)


# ============================================================
# 📦 Collection Operations
# ============================================================

async def add_to_collection(
    pool: Optional[Pool],
    user_id: int,
    card_id: int,
    group_id: Optional[int] = None
) -> Record:
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
    query = """
        INSERT INTO collections (user_id, card_id, caught_in_group)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id, card_id) DO UPDATE SET
            quantity = collections.quantity + 1,
            caught_at = NOW()
        RETURNING *
    """
    
    if pool:
        return await pool.fetchrow(query, user_id, card_id, group_id)
    return await db.fetchrow(query, user_id, card_id, group_id)


async def get_user_collection(
    pool: Optional[Pool],
    user_id: int,
    page: int = 1,
    per_page: int = 10,
    rarity_filter: Optional[int] = None
) -> tuple[list[Record], int]:
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
    offset = (page - 1) * per_page
    
    # Base query with join to get card details
    if rarity_filter:
        count_query = """
            SELECT COUNT(*) FROM collections c
            JOIN cards ca ON c.card_id = ca.card_id
            WHERE c.user_id = $1 AND ca.rarity = $2
        """
        main_query = """
            SELECT c.*, ca.anime, ca.character_name, ca.rarity, 
                   ca.photo_file_id, ca.description
            FROM collections c
            JOIN cards ca ON c.card_id = ca.card_id
            WHERE c.user_id = $1 AND ca.rarity = $4
            ORDER BY ca.rarity DESC, ca.character_name
            LIMIT $2 OFFSET $3
        """
        
        if pool:
            total = await pool.fetchval(count_query, user_id, rarity_filter)
            cards = await pool.fetch(main_query, user_id, per_page, offset, rarity_filter)
        else:
            total = await db.fetchval(count_query, user_id, rarity_filter)
            cards = await db.fetch(main_query, user_id, per_page, offset, rarity_filter)
    else:
        count_query = """
            SELECT COUNT(*) FROM collections WHERE user_id = $1
        """
        main_query = """
            SELECT c.*, ca.anime, ca.character_name, ca.rarity, 
                   ca.photo_file_id, ca.description
            FROM collections c
            JOIN cards ca ON c.card_id = ca.card_id
            WHERE c.user_id = $1
            ORDER BY ca.rarity DESC, ca.character_name
            LIMIT $2 OFFSET $3
        """
        
        if pool:
            total = await pool.fetchval(count_query, user_id)
            cards = await pool.fetch(main_query, user_id, per_page, offset)
        else:
            total = await db.fetchval(count_query, user_id)
            cards = await db.fetch(main_query, user_id, per_page, offset)
    
    return cards, total


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
    query = """
        SELECT 
            COUNT(*) as total_unique,
            SUM(c.quantity) as total_cards,
            COUNT(*) FILTER (WHERE ca.rarity >= 9) as mythical_plus,
            COUNT(*) FILTER (WHERE ca.rarity = 11) as legendary_count
        FROM collections c
        JOIN cards ca ON c.card_id = ca.card_id
        WHERE c.user_id = $1
    """
    
    if pool:
        row = await pool.fetchrow(query, user_id)
    else:
        row = await db.fetchrow(query, user_id)
    
    if row:
        return {
            "total_unique": row["total_unique"] or 0,
            "total_cards": row["total_cards"] or 0,
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
    query = """
        SELECT EXISTS(
            SELECT 1 FROM collections 
            WHERE user_id = $1 AND card_id = $2
        )
    """
    
    if pool:
        return await pool.fetchval(query, user_id, card_id)
    return await db.fetchval(query, user_id, card_id)


# ============================================================
# 👥 Group Operations
# ============================================================

async def ensure_group(
    pool: Optional[Pool],
    group_id: int,
    group_name: Optional[str] = None
) -> Record:
    """
    Ensure a group exists in the database.
    
    Args:
        pool: Database pool
        group_id: Telegram chat ID
        group_name: Group title
        
    Returns:
        Group record
    """
    query = """
        INSERT INTO groups (group_id, group_name)
        VALUES ($1, $2)
        ON CONFLICT (group_id) DO UPDATE SET
            group_name = COALESCE($2, groups.group_name),
            is_active = TRUE
        RETURNING *
    """
    
    if pool:
        return await pool.fetchrow(query, group_id, group_name)
    return await db.fetchrow(query, group_id, group_name)


async def get_all_groups(
    pool: Optional[Pool],
    active_only: bool = True
) -> list[Record]:
    """
    Get all registered groups.
    
    Args:
        pool: Database pool
        active_only: Only return active groups
        
    Returns:
        List of group records
    """
    if active_only:
        query = "SELECT * FROM groups WHERE is_active = TRUE ORDER BY joined_at"
    else:
        query = "SELECT * FROM groups ORDER BY joined_at"
    
    if pool:
        return await pool.fetch(query)
    return await db.fetch(query)


async def get_group_by_id(
    pool: Optional[Pool],
    group_id: int
) -> Optional[Record]:
    """Get a specific group by ID."""
    query = "SELECT * FROM groups WHERE group_id = $1"
    
    if pool:
        return await pool.fetchrow(query, group_id)
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
    query = """
        UPDATE groups SET
            current_card_id = $2,
            current_card_message_id = $3,
            last_spawn = NOW(),
            total_spawns = total_spawns + 1
        WHERE group_id = $1
    """
    
    if pool:
        await pool.execute(query, group_id, card_id, message_id)
    else:
        await db.execute(query, group_id, card_id, message_id)


async def clear_group_spawn(
    pool: Optional[Pool],
    group_id: int
) -> None:
    """Clear the current spawned card in a group after it's caught."""
    query = """
        UPDATE groups SET
            current_card_id = NULL,
            current_card_message_id = NULL,
            total_catches = total_catches + 1
        WHERE group_id = $1
    """
    
    if pool:
        await pool.execute(query, group_id)
    else:
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
    
    if pool:
        return await pool.fetchrow(query, *values)
    return await db.fetchrow(query, *values)


# ============================================================
# 📊 Statistics & Analytics
# ============================================================

async def get_global_stats(pool: Optional[Pool]) -> dict:
    """
    Get global bot statistics.
    
    Returns:
        Dictionary with global stats
    """
    queries = {
        "total_users": "SELECT COUNT(*) FROM users",
        "total_cards": "SELECT COUNT(*) FROM cards WHERE is_active = TRUE",
        "total_catches": "SELECT COALESCE(SUM(total_catches), 0) FROM users",
        "active_groups": "SELECT COUNT(*) FROM groups WHERE is_active = TRUE",
    }
    
    stats = {}
    for key, query in queries.items():
        if pool:
            stats[key] = await pool.fetchval(query)
        else:
            stats[key] = await db.fetchval(query)
    
    return stats


async def get_rarity_distribution(pool: Optional[Pool]) -> list[Record]:
    """
    Get the distribution of cards by rarity.
    
    Returns:
        List of records with rarity and count
    """
    query = """
        SELECT rarity, COUNT(*) as count
        FROM cards
        WHERE is_active = TRUE
        GROUP BY rarity
        ORDER BY rarity
    """
    
    if pool:
        return await pool.fetch(query)
    return await db.fetch(query)


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
    query = """
        UPDATE groups SET is_active = FALSE
        WHERE last_spawn < NOW() - INTERVAL '$1 days'
          AND is_active = TRUE
        RETURNING group_id
    """
    
    if pool:
        result = await pool.fetch(query.replace("$1", str(days_inactive)))
    else:
        result = await db.fetch(query.replace("$1", str(days_inactive)))
    
    return len(result)


async def health_check(pool: Optional[Pool]) -> bool:
    """
    Perform a database health check.
    
    Returns:
        True if database is healthy
    """
    try:
        query = "SELECT 1"
        if pool:
            await pool.fetchval(query)
        else:
            await db.fetchval(query)
        return True
    except Exception as e:
        error_logger.error(f"Database health check failed: {e}")
        return False