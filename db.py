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
    """Async database manager using asyncpg connection pool."""
    
    _pool: Optional[Pool] = None
    _instance: Optional["Database"] = None
    
    def __new__(cls) -> "Database":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @property
    def pool(self) -> Pool:
        if self._pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        return self._pool
    
    @property
    def is_connected(self) -> bool:
        return self._pool is not None
    
    def _parse_database_url(self) -> dict:
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
    
    async def connect(self, max_retries: int = 3, retry_delay: int = 2) -> bool:
        if self._pool is not None:
            log_database("Connection pool already exists")
            return True
        
        if not Config.DATABASE_URL or Config.DATABASE_URL == "postgresql://user:password@localhost:5432/cardbot":
            error_logger.warning("⚠️ DATABASE_URL not configured!")
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
                log_database(f"✅ Database connected!")
                return True
            except asyncpg.InvalidPasswordError as e:
                error_logger.error(f"❌ Database authentication failed: {e}")
                return False
            except asyncpg.InvalidCatalogNameError as e:
                error_logger.error(f"❌ Database does not exist: {e}")
                return False
            except Exception as e:
                error_logger.error(f"Connection attempt {attempt} failed: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(retry_delay)
                else:
                    return False
        return False
    
    async def disconnect(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            log_database("✅ Database pool closed")
    
    @asynccontextmanager
    async def acquire(self):
        if not self.is_connected:
            raise RuntimeError("Database not connected")
        async with self.pool.acquire() as connection:
            yield connection
    
    async def execute(self, query: str, *args) -> str:
        if not self.is_connected:
            raise RuntimeError("Database not connected")
        async with self.acquire() as conn:
            return await conn.execute(query, *args)
    
    async def fetch(self, query: str, *args) -> List[Record]:
        if not self.is_connected:
            raise RuntimeError("Database not connected")
        async with self.acquire() as conn:
            return await conn.fetch(query, *args)
    
    async def fetchrow(self, query: str, *args) -> Optional[Record]:
        if not self.is_connected:
            raise RuntimeError("Database not connected")
        async with self.acquire() as conn:
            return await conn.fetchrow(query, *args)
    
    async def fetchval(self, query: str, *args) -> Any:
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
    if not db.is_connected:
        log_database("⚠️ Cannot initialize schema - database not connected")
        return False
    
    log_database("Initializing database schema...")
    
    try:
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
                role VARCHAR(20) DEFAULT NULL,
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
        
        try:
            await db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT NULL")
        except Exception:
            pass
        
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
        
        # Trades Table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id SERIAL PRIMARY KEY,
                from_user BIGINT NOT NULL,
                to_user BIGINT NOT NULL,
                offered_card_id INTEGER NOT NULL,
                requested_card_id INTEGER,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        log_database("✅ Trades table ready")
        
        # Stats Table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                id SERIAL PRIMARY KEY,
                key TEXT UNIQUE NOT NULL,
                value BIGINT DEFAULT 0,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        log_database("✅ Stats table ready")
        
        # Constraints
        try:
            await db.execute("ALTER TABLE cards ADD CONSTRAINT cards_anime_character_unique UNIQUE (anime, character_name)")
        except (DuplicateTableError, DuplicateObjectError, PostgresError):
            pass
        
        try:
            await db.execute("ALTER TABLE collections ADD CONSTRAINT collections_user_card_unique UNIQUE (user_id, card_id)")
        except (DuplicateTableError, DuplicateObjectError, PostgresError):
            pass
        
        log_database("✅ Constraints ready")
        
        # Indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_collections_user_id ON collections(user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_collections_card_id ON collections(card_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_cards_rarity ON cards(rarity)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_cards_anime ON cards(anime)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role) WHERE role IS NOT NULL")
        log_database("✅ Indexes ready")
        
        # Default Stats
        await db.execute("""
            INSERT INTO stats (key, value) VALUES
                ('total_trades', 0),
                ('total_catches_today', 0),
                ('total_spawns_today', 0)
            ON CONFLICT (key) DO NOTHING
        """)
        
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


async def get_user_leaderboard(pool: Optional[Pool], limit: int = 10, order_by: str = "total_catches") -> List[Record]:
    if not db.is_connected:
        return []
    valid_columns = {"total_catches", "coins", "xp", "level"}
    if order_by not in valid_columns:
        order_by = "total_catches"
    query = f"""
        SELECT user_id, username, first_name, {order_by}, level
        FROM users WHERE is_banned = FALSE
        ORDER BY {order_by} DESC LIMIT $1
    """
    return await db.fetch(query, limit)


async def get_all_users(pool: Optional[Pool]) -> List[Record]:
    if not db.is_connected:
        return []
    return await db.fetch("SELECT * FROM users WHERE is_banned = FALSE")


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
    if not db.is_connected:
        return None
    return await db.fetchrow("SELECT * FROM cards WHERE card_id = $1 AND is_active = TRUE", card_id)


async def get_random_card(pool: Optional[Pool], rarity: Optional[int] = None) -> Optional[Record]:
    if not db.is_connected:
        return None
    if rarity:
        return await db.fetchrow("SELECT * FROM cards WHERE is_active = TRUE AND rarity = $1 ORDER BY RANDOM() LIMIT 1", rarity)
    return await db.fetchrow("SELECT * FROM cards WHERE is_active = TRUE ORDER BY RANDOM() LIMIT 1")


async def search_cards(pool: Optional[Pool], search_term: str, limit: int = 20) -> List[Record]:
    if not db.is_connected:
        return []
    query = """
        SELECT * FROM cards
        WHERE is_active = TRUE AND (anime ILIKE $1 OR character_name ILIKE $1)
        ORDER BY rarity DESC, character_name LIMIT $2
    """
    return await db.fetch(query, f"%{search_term}%", limit)


async def get_card_count(pool: Optional[Pool]) -> int:
    if not db.is_connected:
        return 0
    result = await db.fetchval("SELECT COUNT(*) FROM cards WHERE is_active = TRUE")
    return result or 0


async def increment_card_caught(pool: Optional[Pool], card_id: int) -> None:
    if not db.is_connected:
        return
    await db.execute("UPDATE cards SET total_caught = total_caught + 1 WHERE card_id = $1", card_id)


async def delete_card(pool: Optional[Pool], card_id: int) -> bool:
    if not db.is_connected:
        return False
    result = await db.fetchrow("UPDATE cards SET is_active = FALSE WHERE card_id = $1 RETURNING card_id", card_id)
    return result is not None


# ============================================================
# 📦 Collection Operations
# ============================================================

async def add_to_collection(pool: Optional[Pool], user_id: int, card_id: int, group_id: Optional[int] = None) -> Optional[Record]:
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


async def get_user_collection(pool: Optional[Pool], user_id: int, page: int = 1, per_page: int = 10, rarity_filter: Optional[int] = None) -> tuple:
    if not db.is_connected:
        return [], 0
    offset = (page - 1) * per_page
    if rarity_filter:
        count = await db.fetchval("SELECT COUNT(*) FROM collections c JOIN cards ca ON c.card_id = ca.card_id WHERE c.user_id = $1 AND ca.rarity = $2 AND ca.is_active = TRUE", user_id, rarity_filter)
        cards = await db.fetch("""
            SELECT c.*, ca.anime, ca.character_name, ca.rarity, ca.photo_file_id
            FROM collections c JOIN cards ca ON c.card_id = ca.card_id
            WHERE c.user_id = $1 AND ca.rarity = $4 AND ca.is_active = TRUE
            ORDER BY ca.rarity DESC LIMIT $2 OFFSET $3
        """, user_id, per_page, offset, rarity_filter)
    else:
        count = await db.fetchval("SELECT COUNT(*) FROM collections c JOIN cards ca ON c.card_id = ca.card_id WHERE c.user_id = $1 AND ca.is_active = TRUE", user_id)
        cards = await db.fetch("""
            SELECT c.*, ca.anime, ca.character_name, ca.rarity, ca.photo_file_id
            FROM collections c JOIN cards ca ON c.card_id = ca.card_id
            WHERE c.user_id = $1 AND ca.is_active = TRUE
            ORDER BY ca.rarity DESC LIMIT $2 OFFSET $3
        """, user_id, per_page, offset)
    return cards, count or 0


async def get_user_collection_stats(pool: Optional[Pool], user_id: int) -> dict:
    if not db.is_connected:
        return {"total_unique": 0, "total_cards": 0, "mythical_plus": 0, "legendary_count": 0}
    query = """
        SELECT 
            COUNT(*) as total_unique,
            COALESCE(SUM(c.quantity), 0) as total_cards,
            COUNT(*) FILTER (WHERE ca.rarity >= 9) as mythical_plus,
            COUNT(*) FILTER (WHERE ca.rarity = 11) as legendary_count
        FROM collections c JOIN cards ca ON c.card_id = ca.card_id
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
    return {"total_unique": 0, "total_cards": 0, "mythical_plus": 0, "legendary_count": 0}


async def check_user_has_card(pool: Optional[Pool], user_id: int, card_id: int) -> bool:
    if not db.is_connected:
        return False
    return await db.fetchval("SELECT EXISTS(SELECT 1 FROM collections WHERE user_id = $1 AND card_id = $2)", user_id, card_id)


# ============================================================
# 👥 Group Operations
# ============================================================

async def ensure_group(pool: Optional[Pool], group_id: int, group_name: Optional[str] = None) -> Optional[Record]:
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


async def get_group_by_id(pool: Optional[Pool], group_id: int) -> Optional[Record]:
    if not db.is_connected:
        return None
    return await db.fetchrow("SELECT * FROM groups WHERE group_id = $1", group_id)


async def get_all_groups(pool: Optional[Pool], active_only: bool = True) -> List[Record]:
    if not db.is_connected:
        return []
    if active_only:
        return await db.fetch("SELECT * FROM groups WHERE is_active = TRUE ORDER BY joined_at")
    return await db.fetch("SELECT * FROM groups ORDER BY joined_at")


async def update_group_spawn(pool: Optional[Pool], group_id: int, card_id: int, message_id: int) -> None:
    if not db.is_connected:
        return
    await db.execute("""
        UPDATE groups SET current_card_id = $2, current_card_message_id = $3,
        last_spawn = NOW(), total_spawns = total_spawns + 1 WHERE group_id = $1
    """, group_id, card_id, message_id)


async def clear_group_spawn(pool: Optional[Pool], group_id: int) -> None:
    if not db.is_connected:
        return
    await db.execute("""
        UPDATE groups SET current_card_id = NULL, current_card_message_id = NULL,
        total_catches = total_catches + 1 WHERE group_id = $1
    """, group_id)


# ============================================================
# 📊 Statistics
# ============================================================

async def get_global_stats(pool: Optional[Pool]) -> dict:
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
        error_logger.error(f"Error getting global stats: {e}")
        return {"total_users": 0, "total_cards": 0, "total_catches": 0, "active_groups": 0}


async def health_check(pool: Optional[Pool]) -> bool:
    if not db.is_connected:
        return False
    try:
        await db.fetchval("SELECT 1")
        return True
    except Exception:
        return False


# ============================================================
# 👑 Role Management
# ============================================================

async def add_role(pool: Optional[Pool], user_id: int, role: str) -> bool:
    if not db.is_connected:
        return False
    valid_roles = {'admin', 'dev', 'uploader'}
    if role.lower() not in valid_roles:
        return False
    try:
        await db.execute("""
            INSERT INTO users (user_id, role) VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET role = $2, updated_at = NOW()
        """, user_id, role.lower())
        return True
    except Exception as e:
        error_logger.error(f"Error adding role: {e}")
        return False


async def remove_role(pool: Optional[Pool], user_id: int) -> bool:
    if not db.is_connected:
        return False
    try:
        await db.execute("UPDATE users SET role = NULL, updated_at = NOW() WHERE user_id = $1", user_id)
        return True
    except Exception as e:
        error_logger.error(f"Error removing role: {e}")
        return False


async def get_user_role(pool: Optional[Pool], user_id: int) -> Optional[str]:
    if not db.is_connected:
        return None
    try:
        return await db.fetchval("SELECT role FROM users WHERE user_id = $1", user_id)
    except Exception as e:
        error_logger.error(f"Error getting role: {e}")
        return None


async def check_is_owner(user_id: int) -> bool:
    return user_id == Config.OWNER_ID


async def check_is_admin(user_id: int) -> bool:
    if await check_is_owner(user_id):
        return True
    role = await get_user_role(None, user_id)
    return role in ('admin', 'dev')


async def check_is_dev(user_id: int) -> bool:
    if await check_is_owner(user_id):
        return True
    role = await get_user_role(None, user_id)
    return role == 'dev'


async def check_is_uploader(user_id: int) -> bool:
    if await check_is_owner(user_id):
        return True
    role = await get_user_role(None, user_id)
    return role in ('admin', 'dev', 'uploader')


async def list_users_by_role(pool: Optional[Pool], role: str) -> List[Record]:
    if not db.is_connected:
        return []
    try:
        return await db.fetch("SELECT user_id, username, first_name, role FROM users WHERE role = $1", role.lower())
    except Exception as e:
        error_logger.error(f"Error listing users by role: {e}")
        return []