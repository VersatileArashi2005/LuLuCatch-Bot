"""
Database module for the Telegram Card Bot.
Handles PostgreSQL connection pool and all database operations.
"""

import asyncpg
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from config import config
from utils.logger import logger


class Database:
    """
    Async database handler using asyncpg connection pool.
    Provides all database operations for the card bot.
    """
    
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """Initialize the connection pool."""
        try:
            self.pool = await asyncpg.create_pool(
                config.DATABASE_URL,
                min_size=config.DB_POOL_MIN_SIZE,
                max_size=config.DB_POOL_MAX_SIZE,
                command_timeout=60
            )
            logger.info("✅ Database connection pool created successfully")
            
            # Initialize tables
            await self._init_tables()
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to database: {e}")
            raise
    
    async def disconnect(self):
        """Close the connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("🔌 Database connection pool closed")
    
    @asynccontextmanager
    async def acquire(self):
        """Acquire a connection from the pool."""
        async with self.pool.acquire() as connection:
            yield connection
    
    async def _init_tables(self):
        """Initialize database tables if they don't exist."""
        async with self.acquire() as conn:
            # Users table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    role VARCHAR(50) DEFAULT 'user',
                    last_catch TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Anime table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS anime (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Characters table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS characters (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    anime_id INTEGER REFERENCES anime(id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(name, anime_id)
                )
            """)
            
            # Cards table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS cards (
                    id SERIAL PRIMARY KEY,
                    character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
                    rarity_id INTEGER NOT NULL DEFAULT 1,
                    file_id VARCHAR(255) NOT NULL,
                    added_by BIGINT REFERENCES users(user_id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Harem/Collections table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS harem (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                    card_id INTEGER REFERENCES cards(id) ON DELETE CASCADE,
                    caught_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, card_id)
                )
            """)
            
            # Groups table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS groups (
                    group_id BIGINT PRIMARY KEY,
                    title VARCHAR(255),
                    catch_cooldown INTEGER DEFAULT 24,
                    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Catch log table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS catch_log (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES users(user_id),
                    card_id INTEGER REFERENCES cards(id),
                    group_id BIGINT,
                    caught_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Bot settings table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS bot_settings (
                    key VARCHAR(100) PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for better performance
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_harem_user_id ON harem(user_id);
                CREATE INDEX IF NOT EXISTS idx_cards_character_id ON cards(character_id);
                CREATE INDEX IF NOT EXISTS idx_characters_anime_id ON characters(anime_id);
                CREATE INDEX IF NOT EXISTS idx_catch_log_caught_at ON catch_log(caught_at);
            """)
            
            logger.info("✅ Database tables initialized")
    
    # ===== User Operations =====
    
    async def ensure_user(self, user_id: int, name: str) -> Dict[str, Any]:
        """
        Ensure user exists in database, create if not.
        
        Args:
            user_id: Telegram user ID
            name: User's display name
            
        Returns:
            User data dictionary
        """
        async with self.acquire() as conn:
            # Try to get existing user
            user = await conn.fetchrow(
                "SELECT * FROM users WHERE user_id = $1",
                user_id
            )
            
            if user:
                # Update name if changed
                if user['name'] != name:
                    await conn.execute(
                        "UPDATE users SET name = $1, updated_at = CURRENT_TIMESTAMP WHERE user_id = $2",
                        name, user_id
                    )
                return dict(user)
            
            # Create new user
            await conn.execute(
                "INSERT INTO users (user_id, name) VALUES ($1, $2)",
                user_id, name
            )
            
            return {
                'user_id': user_id,
                'name': name,
                'role': 'user',
                'last_catch': None
            }
    
    async def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        async with self.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT * FROM users WHERE user_id = $1",
                user_id
            )
            return dict(user) if user else None
    
    async def update_user_role(self, user_id: int, role: str) -> bool:
        """Update user's role."""
        async with self.acquire() as conn:
            result = await conn.execute(
                "UPDATE users SET role = $1, updated_at = CURRENT_TIMESTAMP WHERE user_id = $2",
                role, user_id
            )
            return result == "UPDATE 1"
    
    async def update_last_catch(self, user_id: int) -> bool:
        """Update user's last catch timestamp."""
        async with self.acquire() as conn:
            result = await conn.execute(
                "UPDATE users SET last_catch = CURRENT_TIMESTAMP WHERE user_id = $1",
                user_id
            )
            return result == "UPDATE 1"
    
    async def get_user_cooldown(self, user_id: int, cooldown_hours: int) -> Optional[timedelta]:
        """
        Check if user is on cooldown.
        
        Args:
            user_id: User ID
            cooldown_hours: Cooldown duration in hours
            
        Returns:
            Remaining cooldown time or None if no cooldown
        """
        async with self.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT last_catch FROM users WHERE user_id = $1",
                user_id
            )
            
            if not user or not user['last_catch']:
                return None
            
            last_catch = user['last_catch']
            cooldown_end = last_catch + timedelta(hours=cooldown_hours)
            now = datetime.utcnow()
            
            if now < cooldown_end:
                return cooldown_end - now
            
            return None
    
    # ===== Anime Operations =====
    
    async def get_all_anime(self) -> List[Tuple[int, str]]:
        """Get all anime as (id, name) tuples."""
        async with self.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, name FROM anime ORDER BY name"
            )
            return [(row['id'], row['name']) for row in rows]
    
    async def add_anime(self, name: str) -> int:
        """Add new anime and return its ID."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO anime (name) VALUES ($1) ON CONFLICT (name) DO UPDATE SET name = $1 RETURNING id",
                name
            )
            return row['id']
    
    async def get_anime_by_id(self, anime_id: int) -> Optional[Dict[str, Any]]:
        """Get anime by ID."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM anime WHERE id = $1",
                anime_id
            )
            return dict(row) if row else None
    
    # ===== Character Operations =====
    
    async def get_characters_by_anime(self, anime_id: int) -> List[Tuple[int, str]]:
        """Get all characters for an anime."""
        async with self.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, name FROM characters WHERE anime_id = $1 ORDER BY name",
                anime_id
            )
            return [(row['id'], row['name']) for row in rows]
    
    async def add_character(self, name: str, anime_id: int) -> int:
        """Add new character and return its ID."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO characters (name, anime_id) 
                   VALUES ($1, $2) 
                   ON CONFLICT (name, anime_id) DO UPDATE SET name = $1 
                   RETURNING id""",
                name, anime_id
            )
            return row['id']
    
    async def get_character_by_id(self, char_id: int) -> Optional[Dict[str, Any]]:
        """Get character by ID with anime info."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT c.*, a.name as anime_name 
                   FROM characters c 
                   JOIN anime a ON c.anime_id = a.id 
                   WHERE c.id = $1""",
                char_id
            )
            return dict(row) if row else None
    
    # ===== Card Operations =====
    
    async def add_card(self, character_id: int, rarity_id: int, 
                       file_id: str, added_by: int) -> int:
        """Add new card and return its ID."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO cards (character_id, rarity_id, file_id, added_by)
                   VALUES ($1, $2, $3, $4) RETURNING id""",
                character_id, rarity_id, file_id, added_by
            )
            logger.info(f"✅ Card added: ID={row['id']}, Character={character_id}")
            return row['id']
    
    async def get_card_by_id(self, card_id: int) -> Optional[Dict[str, Any]]:
        """Get card by ID with full details."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT c.*, ch.name as character, a.name as anime
                   FROM cards c
                   JOIN characters ch ON c.character_id = ch.id
                   JOIN anime a ON ch.anime_id = a.id
                   WHERE c.id = $1""",
                card_id
            )
            return dict(row) if row else None
    
    async def get_random_card(self, rarity_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Get a random card, optionally filtered by rarity."""
        async with self.acquire() as conn:
            if rarity_id:
                row = await conn.fetchrow(
                    """SELECT c.*, ch.name as character, a.name as anime
                       FROM cards c
                       JOIN characters ch ON c.character_id = ch.id
                       JOIN anime a ON ch.anime_id = a.id
                       WHERE c.rarity_id = $1
                       ORDER BY RANDOM() LIMIT 1""",
                    rarity_id
                )
            else:
                row = await conn.fetchrow(
                    """SELECT c.*, ch.name as character, a.name as anime
                       FROM cards c
                       JOIN characters ch ON c.character_id = ch.id
                       JOIN anime a ON ch.anime_id = a.id
                       ORDER BY RANDOM() LIMIT 1"""
                )
            return dict(row) if row else None
    
    async def update_card(self, card_id: int, **kwargs) -> bool:
        """Update card fields."""
        if not kwargs:
            return False
        
        async with self.acquire() as conn:
            set_clauses = []
            values = []
            i = 1
            
            for key, value in kwargs.items():
                set_clauses.append(f"{key} = ${i}")
                values.append(value)
                i += 1
            
            values.append(card_id)
            query = f"UPDATE cards SET {', '.join(set_clauses)} WHERE id = ${i}"
            
            result = await conn.execute(query, *values)
            return result == "UPDATE 1"
    
    async def delete_card(self, card_id: int) -> bool:
        """Delete a card."""
        async with self.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM cards WHERE id = $1",
                card_id
            )
            return result == "DELETE 1"
    
    async def search_cards(self, query: str) -> List[Dict[str, Any]]:
        """Search cards by character, anime, or rarity."""
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """SELECT c.id, ch.name as character, a.name as anime, c.rarity_id
                   FROM cards c
                   JOIN characters ch ON c.character_id = ch.id
                   JOIN anime a ON ch.anime_id = a.id
                   WHERE LOWER(ch.name) LIKE LOWER($1) 
                      OR LOWER(a.name) LIKE LOWER($1)
                   ORDER BY c.rarity_id DESC
                   LIMIT 50""",
                f"%{query}%"
            )
            return [dict(row) for row in rows]
    
    async def get_card_owner_count(self, card_id: int) -> int:
        """Get number of users who own a card."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(*) as count FROM harem WHERE card_id = $1",
                card_id
            )
            return row['count'] if row else 0
    
    async def get_card_owners(self, card_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get list of users who own a card."""
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """SELECT u.user_id, u.name, h.caught_at
                   FROM harem h
                   JOIN users u ON h.user_id = u.user_id
                   WHERE h.card_id = $1
                   ORDER BY h.caught_at
                   LIMIT $2""",
                card_id, limit
            )
            return [dict(row) for row in rows]
    
    async def get_cards_by_ids(self, card_ids: List[int]) -> List[Dict[str, Any]]:
        """Get multiple cards by their IDs."""
        if not card_ids:
            return []
        
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """SELECT c.*, ch.name as character, a.name as anime
                   FROM cards c
                   JOIN characters ch ON c.character_id = ch.id
                   JOIN anime a ON ch.anime_id = a.id
                   WHERE c.id = ANY($1)""",
                card_ids
            )
            return [dict(row) for row in rows]
    
    async def get_total_cards(self) -> int:
        """Get total number of cards."""
        async with self.acquire() as conn:
            row = await conn.fetchrow("SELECT COUNT(*) as count FROM cards")
            return row['count'] if row else 0
    
    # ===== Harem/Collection Operations =====
    
    async def give_card_to_user(self, user_id: int, card_id: int) -> bool:
        """Give a card to a user (add to their collection)."""
        async with self.acquire() as conn:
            try:
                await conn.execute(
                    """INSERT INTO harem (user_id, card_id) 
                       VALUES ($1, $2) 
                       ON CONFLICT (user_id, card_id) DO NOTHING""",
                    user_id, card_id
                )
                return True
            except Exception as e:
                logger.error(f"Error giving card to user: {e}")
                return False
    
    async def get_user_harem(self, user_id: int, rarity_filter: Optional[int] = None,
                             page: int = 0, per_page: int = 10) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get user's card collection with pagination.
        
        Returns:
            Tuple of (cards list, total count)
        """
        async with self.acquire() as conn:
            # Build query based on filter
            if rarity_filter:
                count_row = await conn.fetchrow(
                    """SELECT COUNT(*) as count FROM harem h
                       JOIN cards c ON h.card_id = c.id
                       WHERE h.user_id = $1 AND c.rarity_id = $2""",
                    user_id, rarity_filter
                )
                
                rows = await conn.fetch(
                    """SELECT c.*, ch.name as character, a.name as anime, h.caught_at
                       FROM harem h
                       JOIN cards c ON h.card_id = c.id
                       JOIN characters ch ON c.character_id = ch.id
                       JOIN anime a ON ch.anime_id = a.id
                       WHERE h.user_id = $1 AND c.rarity_id = $2
                       ORDER BY c.rarity_id DESC, h.caught_at DESC
                       LIMIT $3 OFFSET $4""",
                    user_id, rarity_filter, per_page, page * per_page
                )
            else:
                count_row = await conn.fetchrow(
                    "SELECT COUNT(*) as count FROM harem WHERE user_id = $1",
                    user_id
                )
                
                rows = await conn.fetch(
                    """SELECT c.*, ch.name as character, a.name as anime, h.caught_at
                       FROM harem h
                       JOIN cards c ON h.card_id = c.id
                       JOIN characters ch ON c.character_id = ch.id
                       JOIN anime a ON ch.anime_id = a.id
                       WHERE h.user_id = $1
                       ORDER BY c.rarity_id DESC, h.caught_at DESC
                       LIMIT $2 OFFSET $3""",
                    user_id, per_page, page * per_page
                )
            
            total = count_row['count'] if count_row else 0
            return [dict(row) for row in rows], total
    
    async def get_user_card_count(self, user_id: int) -> int:
        """Get total cards owned by user."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(*) as count FROM harem WHERE user_id = $1",
                user_id
            )
            return row['count'] if row else 0
    
    async def user_has_card(self, user_id: int, card_id: int) -> bool:
        """Check if user owns a specific card."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM harem WHERE user_id = $1 AND card_id = $2",
                user_id, card_id
            )
            return row is not None
    
    # ===== Group Operations =====
    
    async def register_group(self, group_id: int, title: str) -> bool:
        """Register or update a group."""
        async with self.acquire() as conn:
            await conn.execute(
                """INSERT INTO groups (group_id, title) 
                   VALUES ($1, $2)
                   ON CONFLICT (group_id) DO UPDATE SET title = $2""",
                group_id, title
            )
            return True
    
    async def get_all_groups(self) -> List[Dict[str, Any]]:
        """Get all registered groups."""
        async with self.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM groups ORDER BY registered_at")
            return [dict(row) for row in rows]
    
    async def get_group_cooldown(self, group_id: int) -> int:
        """Get catch cooldown for a group."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT catch_cooldown FROM groups WHERE group_id = $1",
                group_id
            )
            return row['catch_cooldown'] if row else config.DEFAULT_CATCH_COOLDOWN
    
    async def set_group_cooldown(self, group_id: int, hours: int) -> bool:
        """Set catch cooldown for a group."""
        async with self.acquire() as conn:
            result = await conn.execute(
                "UPDATE groups SET catch_cooldown = $1 WHERE group_id = $2",
                hours, group_id
            )
            return result == "UPDATE 1"
    
    # ===== Catch Log Operations =====
    
    async def log_catch(self, user_id: int, card_id: int, group_id: Optional[int] = None):
        """Log a card catch."""
        async with self.acquire() as conn:
            await conn.execute(
                "INSERT INTO catch_log (user_id, card_id, group_id) VALUES ($1, $2, $3)",
                user_id, card_id, group_id
            )
    
    async def get_catches_today(self) -> int:
        """Get number of catches today."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT COUNT(*) as count FROM catch_log 
                   WHERE caught_at >= CURRENT_DATE"""
            )
            return row['count'] if row else 0
    
    async def get_total_catches(self) -> int:
        """Get total number of catches."""
        async with self.acquire() as conn:
            row = await conn.fetchrow("SELECT COUNT(*) as count FROM catch_log")
            return row['count'] if row else 0
    
    # ===== Statistics Operations =====
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive bot statistics."""
        async with self.acquire() as conn:
            # Total users
            users = await conn.fetchrow("SELECT COUNT(*) as count FROM users")
            
            # Active users today
            active = await conn.fetchrow(
                """SELECT COUNT(DISTINCT user_id) as count FROM catch_log 
                   WHERE caught_at >= CURRENT_DATE"""
            )
            
            # Total cards
            cards = await conn.fetchrow("SELECT COUNT(*) as count FROM cards")
            
            # Total anime
            anime = await conn.fetchrow("SELECT COUNT(*) as count FROM anime")
            
            # Total characters
            characters = await conn.fetchrow("SELECT COUNT(*) as count FROM characters")
            
            # Catches today
            catches_today = await conn.fetchrow(
                "SELECT COUNT(*) as count FROM catch_log WHERE caught_at >= CURRENT_DATE"
            )
            
            # Total catches
            total_catches = await conn.fetchrow("SELECT COUNT(*) as count FROM catch_log")
            
            # Total groups
            groups = await conn.fetchrow("SELECT COUNT(*) as count FROM groups")
            
            return {
                'total_users': users['count'] if users else 0,
                'active_today': active['count'] if active else 0,
                'total_cards': cards['count'] if cards else 0,
                'total_anime': anime['count'] if anime else 0,
                'total_characters': characters['count'] if characters else 0,
                'catches_today': catches_today['count'] if catches_today else 0,
                'total_catches': total_catches['count'] if total_catches else 0,
                'total_groups': groups['count'] if groups else 0
            }
    
    # ===== Settings Operations =====
    
    async def get_setting(self, key: str, default: str = "") -> str:
        """Get a bot setting."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value FROM bot_settings WHERE key = $1",
                key
            )
            return row['value'] if row else default
    
    async def set_setting(self, key: str, value: str):
        """Set a bot setting."""
        async with self.acquire() as conn:
            await conn.execute(
                """INSERT INTO bot_settings (key, value, updated_at)
                   VALUES ($1, $2, CURRENT_TIMESTAMP)
                   ON CONFLICT (key) DO UPDATE SET value = $2, updated_at = CURRENT_TIMESTAMP""",
                key, value
            )
    
    # ===== Health Check =====
    
    async def check_connection(self) -> bool:
        """Check if database connection is healthy."""
        try:
            async with self.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False


# Global database instance
db = Database()