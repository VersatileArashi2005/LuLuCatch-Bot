# ============================================================
# 📁 File: db.py
# 📍 Location: telegram_card_bot/db.py
# 📝 Description: AsyncPG database operations with Railway support
# ============================================================

import asyncio
import ssl
from datetime import datetime
from typing import Optional, Any
from contextlib import asynccontextmanager
from urllib.parse import urlparse, parse_qs

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
    Includes Railway-compatible SSL handling and retry logic.
    """
    
    _pool: Optional[Pool] = None
    _instance: Optional["Database"] = None
    
    def __new__(cls) -> "Database":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @property
    def pool(self) -> Pool:
        """Get the connection pool."""
        if self._pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        return self._pool
    
    @property
    def is_connected(self) -> bool:
        """Check if database is connected."""
        return self._pool is not None
    
    def _parse_database_url(self) -> dict:
        """Parse DATABASE_URL and extract connection parameters."""
        url = Config.DATABASE_URL
        
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
    
    async def connect(self, max_retries: int = 5, retry_delay: int = 3) -> bool:
        """Initialize the database connection pool with retry logic."""
        if self._pool is not None:
            log_database("Connection pool already exists")
            return True
        
        if not Config.DATABASE_URL or Config.DATABASE_URL == "postgresql://user:password@localhost:5432/cardbot":
            error_logger.warning(
                "⚠️ DATABASE_URL not configured! Please add a PostgreSQL database on Railway."
            )
            return False
        
        db_params = self._parse_database_url()
        log_database(f"Connecting to database at {db_params['host']}:{db_params['port']}...")
        
        ssl_context = None
        if db_params.get("ssl") or "railway" in str(db_params.get("host", "")):
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            log_database("Using SSL connection")
        
        dsn = Config.DATABASE_URL
        if dsn.startswith("postgres://"):
            dsn = dsn.replace("postgres://", "postgresql://", 1)
        
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
                
                async with self._pool.acquire() as conn:
                    await conn.execute("SELECT 1")
                
                log_database(
                    f"✅ Database connected! (pool: {Config.DB_MIN_CONNECTIONS}-{Config.DB_MAX_CONNECTIONS})"
                )
                return True
                
            except asyncpg.InvalidPasswordError as e:
                error_logger.error(f"❌ Database authentication failed: {e}")
                return False
                
            except asyncpg.InvalidCatalogNameError as e:
                error_logger.error(f"❌ Database does not exist: {e}")
                return False
                
            except Exception as e:
                error_logger.error(f"Connection attempt {attempt} failed: {type(e).__name__}: {e}")
                
                if attempt < max_retries:
                    log_database(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                else:
                    error_logger.error(f"❌ Failed to connect after {max_retries} attempts.")
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
        """Context manager for acquiring a connection."""
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
    
    async def fetch(self, query: str, *args) -> list[Record]:
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
    Creates tables in correct order to avoid foreign key issues.
    """
    if not db.is_connected:
        log_database("⚠️ Cannot initialize schema - database not connected")
        return False
    
    log_database("Initializing database schema...")
    
    try:
        # ========================================
        # Step 1: Create tables WITHOUT foreign keys
        # ========================================
        
        # Users Table
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
        
        # Cards Table
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
        
        # Add unique constraint on cards
        try:
            await db.execute("""
                ALTER TABLE cards 
                ADD CONSTRAINT cards_anime_character_unique 
                UNIQUE (anime, character_name)
            """)
        except asyncpg.DuplicateObjectError:
            pass  # Constraint already exists
        
        # Collections Table
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
        
        # Add unique constraint on collections
        try:
            await db.execute("""
                ALTER TABLE collections 
                ADD CONSTRAINT collections_user_card_unique 
                UNIQUE (user_id, card_id)
            """)
        except asyncpg.DuplicateObjectError:
            pass  # Constraint already exists
        
        # Groups Table
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
        # Step 2: Add foreign keys (ignore errors if exist)
        # ========================================
        
        try:
            await db.execute("""
                ALTER TABLE collections 
                ADD CONSTRAINT fk_collections_user 
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            """)
        except asyncpg.DuplicateObjectError:
            pass
        
        try:
            await db.execute("""
                ALTER TABLE collections 
                ADD CONSTRAINT fk_collections_card 
                FOREIGN KEY (card_id) REFERENCES cards(card_id) ON DELETE CASCADE
            """)
        except asyncpg.DuplicateObjectError:
            pass
        
        log_database("✅ Foreign keys configured")
        
        # ========================================
        # Step 3: Create indexes
        # ========================================
        
        await db.execute("CREATE INDEX IF NOT EXISTS idx_collections_user_id ON collections(user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_collections_card_id ON collections(card_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_cards_rarity ON cards(rarity)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_cards_anime ON cards(anime)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_groups_active ON groups(is_active) WHERE is_active = TRUE")
        
        log_database("✅ Indexes created")
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
    """Ensure a user exists in the database."""
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


async def get_user_by_id(pool: Optional[Pool], user_id: int) -> Optional[Record]:
    """Get a user by their Telegram user ID."""
    if not db.is_connected:
        return None
    return await db.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)


async def update_user_stats(
    pool: Optional[Pool],
    user_id: int,
    coins_delta: int = 0,
    xp_delta: int = 0,
    catches_delta: int = 0
) -> Optional[Record]:
    """Update user statistics."""
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
    """Add a new card to the database."""
    if not db.is_connected:
        return None
    
    if not 1 <= rarity <= 11:
        raise ValueError(f"Invalid rarity: {rarity}")
    
    query = """
        INSERT INTO cards (anime, character_name, rarity, photo_file_id, uploader_id, description, tags)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (anime, character_name) DO NOTHING
        RETURNING *
    """
    return await db.fetchrow(query, anime, character, rarity, photo_file_id, uploader_id, description, tags or [])


async def get_card_by_id(pool: Optional[Pool], card_id: int) -> Optional[Record]:
    """Get a card by its ID."""
    if not db.is_connected:
        return None
    return await db.fetchrow("SELECT * FROM cards WHERE card_id = $1 AND is_active = TRUE", card_id)


async def get_cards_by_ids(pool: Optional[Pool], card_ids: list[int]) -> list[Record]:
    """Get multiple cards by their IDs."""
    if not db.is_connected or not card_ids:
        return []
    return await db.fetch(
        "SELECT * FROM cards WHERE card_id = ANY($1) AND is_active = TRUE ORDER BY rarity DESC",
        card_ids
    )


async def get_random_card(pool: Optional[Pool], rarity: Optional[int] = None) -> Optional[Record]:
    """Get a random active card."""
    if not db.is_connected:
        return None
    
    if rarity:
        return await db.fetchrow(
            "SELECT * FROM cards WHERE is_active = TRUE AND rarity = $1 ORDER BY RANDOM() LIMIT 1",
            rarity
        )
    return await db.fetchrow("SELECT * FROM cards WHERE is_active = TRUE ORDER BY RANDOM() LIMIT 1")


async def get_card_count(pool: Optional[Pool]) -> int:
    """Get total number of active cards."""
    if not db.is_connected:
        return 0
    result = await db.fetchval("SELECT COUNT(*) FROM cards WHERE is_active = TRUE")
    return result or 0


async def increment_card_caught(pool: Optional[Pool], card_id: int) -> None:
    """Increment the total_caught counter for a card."""
    if not db.is_connected:
        return
    await db.execute("UPDATE cards SET total_caught = total_caught + 1 WHERE card_id = $1", card_id)


# ============================================================
# 📦 Collection Operations
# ============================================================

async def add_to_collection(
    pool: Optional[Pool],
    user_id: int,
    card_id: int,
    group_id: Optional[int] = None
) -> Optional[Record]:
    """Add a card to user's collection or increment quantity."""
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
) -> tuple[list[Record], int]:
    """Get a user's card collection with pagination."""
    if not db.is_connected:
        return [], 0
    
    offset = (page - 1) * per_page
    
    if rarity_filter:
        count_query = """
            SELECT COUNT(*) FROM collections c
            JOIN cards ca ON c.card_id = ca.card_id
            WHERE c.user_id = $1 AND ca.rarity = $2
        """
        main_query = """
            SELECT c.*, ca.anime, ca.character_name, ca.rarity, ca.photo_file_id
            FROM collections c
            JOIN cards ca ON c.card_id = ca.card_id
            WHERE c.user_id = $1 AND ca.rarity = $4
            ORDER BY ca.rarity DESC
            LIMIT $2 OFFSET $3
        """
        total = await db.fetchval(count_query, user_id, rarity_filter)
        cards = await db.fetch(main_query, user_id, per_page, offset, rarity_filter)
    else:
        total = await db.fetchval("SELECT COUNT(*) FROM collections WHERE user_id = $1", user_id)
        cards = await db.fetch("""
            SELECT c.*, ca.anime, ca.character_name, ca.rarity, ca.photo_file_id
            FROM collections c
            JOIN cards ca ON c.card_id = ca.card_id
            WHERE c.user_id = $1
            ORDER BY ca.rarity DESC
            LIMIT $2 OFFSET $3
        """, user_id, per_page, offset)
    
    return cards, total or 0


async def get_user_collection_stats(pool: Optional[Pool], user_id: int) -> dict:
    """Get statistics about a user's collection."""
    if not db.is_connected:
        return {"total_unique": 0, "total_cards": 0, "mythical_plus": 0, "legendary_count": 0}
    
    row = await db.fetchrow("""
        SELECT 
            COUNT(*) as total_unique,
            COALESCE(SUM(c.quantity), 0) as total_cards,
            COUNT(*) FILTER (WHERE ca.rarity >= 9) as mythical_plus,
            COUNT(*) FILTER (WHERE ca.rarity = 11) as legendary_count
        FROM collections c
        JOIN cards ca ON c.card_id = ca.card_id
        WHERE c.user_id = $1
    """, user_id)
    
    if row:
        return {
            "total_unique": row["total_unique"] or 0,
            "total_cards": int(row["total_cards"] or 0),
            "mythical_plus": row["mythical_plus"] or 0,
            "legendary_count": row["legendary_count"] or 0,
        }
    return {"total_unique": 0, "total_cards": 0, "mythical_plus": 0, "legendary_count": 0}


# ============================================================
# 👥 Group Operations
# ============================================================

async def ensure_group(pool: Optional[Pool], group_id: int, group_name: Optional[str] = None) -> Optional[Record]:
    """Ensure a group exists in the database."""
    if not db.is_connected:
        return None
    
    return await db.fetchrow("""
        INSERT INTO groups (group_id, group_name)
        VALUES ($1, $2)
        ON CONFLICT (group_id) DO UPDATE SET
            group_name = COALESCE($2, groups.group_name),
            is_active = TRUE
        RETURNING *
    """, group_id, group_name)


async def get_all_groups(pool: Optional[Pool], active_only: bool = True) -> list[Record]:
    """Get all registered groups."""
    if not db.is_connected:
        return []
    
    if active_only:
        return await db.fetch("SELECT * FROM groups WHERE is_active = TRUE ORDER BY joined_at")
    return await db.fetch("SELECT * FROM groups ORDER BY joined_at")


async def get_group_by_id(pool: Optional[Pool], group_id: int) -> Optional[Record]:
    """Get a specific group by ID."""
    if not db.is_connected:
        return None
    return await db.fetchrow("SELECT * FROM groups WHERE group_id = $1", group_id)


async def update_group_spawn(pool: Optional[Pool], group_id: int, card_id: int, message_id: int) -> None:
    """Update the current spawned card in a group."""
    if not db.is_connected:
        return
    await db.execute("""
        UPDATE groups SET
            current_card_id = $2,
            current_card_message_id = $3,
            last_spawn = NOW(),
            total_spawns = total_spawns + 1
        WHERE group_id = $1
    """, group_id, card_id, message_id)


async def clear_group_spawn(pool: Optional[Pool], group_id: int) -> None:
    """Clear the current spawned card in a group."""
    if not db.is_connected:
        return
    await db.execute("""
        UPDATE groups SET
            current_card_id = NULL,
            current_card_message_id = NULL,
            total_catches = total_catches + 1
        WHERE group_id = $1
    """, group_id)


# ============================================================
# 📊 Statistics
# ============================================================

async def get_global_stats(pool: Optional[Pool]) -> dict:
    """Get global bot statistics."""
    if not db.is_connected:
        return {"total_users": 0, "total_cards": 0, "total_catches": 0, "active_groups": 0}
    
    try:
        return {
            "total_users": await db.fetchval("SELECT COUNT(*) FROM users") or 0,
            "total_cards": await db.fetchval("SELECT COUNT(*) FROM cards WHERE is_active = TRUE") or 0,
            "total_catches": int(await db.fetchval("SELECT COALESCE(SUM(total_catches), 0) FROM users") or 0),
            "active_groups": await db.fetchval("SELECT COUNT(*) FROM groups WHERE is_active = TRUE") or 0,
        }
    except Exception as e:
        error_logger.error(f"Error getting stats: {e}")
        return {"total_users": 0, "total_cards": 0, "total_catches": 0, "active_groups": 0}


async def get_rarity_distribution(pool: Optional[Pool]) -> list[Record]:
    """Get the distribution of cards by rarity."""
    if not db.is_connected:
        return []
    return await db.fetch("""
        SELECT rarity, COUNT(*) as count
        FROM cards WHERE is_active = TRUE
        GROUP BY rarity ORDER BY rarity
    """)


async def health_check(pool: Optional[Pool]) -> bool:
    """Perform a database health check."""
    if not db.is_connected:
        return False
    try:
        await db.fetchval("SELECT 1")
        return True
    except Exception:
        return False