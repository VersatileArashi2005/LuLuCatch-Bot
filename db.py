# ============================================================
# 👑 Role Management
# ============================================================

async def add_role(
    pool: Optional[Pool],
    user_id: int,
    role: str
) -> bool:
    """
    Add a role to a user.
    
    Args:
        pool: Database pool
        user_id: User ID
        role: Role name (admin, dev, uploader)
    
    Returns:
        True if successful
    """
    if not db.is_connected:
        return False
    
    valid_roles = {'admin', 'dev', 'uploader'}
    if role.lower() not in valid_roles:
        return False
    
    try:
        await db.execute(
            """
            INSERT INTO users (user_id, role)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET
                role = $2,
                updated_at = NOW()
            """,
            user_id, role.lower()
        )
        return True
    except Exception as e:
        error_logger.error(f"Error adding role: {e}")
        return False


async def remove_role(
    pool: Optional[Pool],
    user_id: int
) -> bool:
    """
    Remove role from a user (set to NULL).
    """
    if not db.is_connected:
        return False
    
    try:
        await db.execute(
            """
            UPDATE users SET role = NULL, updated_at = NOW()
            WHERE user_id = $1
            """,
            user_id
        )
        return True
    except Exception as e:
        error_logger.error(f"Error removing role: {e}")
        return False


async def get_user_role(
    pool: Optional[Pool],
    user_id: int
) -> Optional[str]:
    """
    Get a user's role.
    
    Returns:
        Role name or None
    """
    if not db.is_connected:
        return None
    
    try:
        result = await db.fetchval(
            "SELECT role FROM users WHERE user_id = $1",
            user_id
        )
        return result
    except Exception as e:
        error_logger.error(f"Error getting role: {e}")
        return None


async def check_is_owner(user_id: int) -> bool:
    """Check if user is bot owner (from config)."""
    from config import Config
    return user_id == Config.OWNER_ID


async def check_is_admin(user_id: int) -> bool:
    """Check if user is admin or higher."""
    if await check_is_owner(user_id):
        return True
    role = await get_user_role(None, user_id)
    return role in ('admin', 'dev')


async def check_is_dev(user_id: int) -> bool:
    """Check if user is dev or higher."""
    if await check_is_owner(user_id):
        return True
    role = await get_user_role(None, user_id)
    return role == 'dev'


async def check_is_uploader(user_id: int) -> bool:
    """Check if user can upload cards."""
    if await check_is_owner(user_id):
        return True
    role = await get_user_role(None, user_id)
    return role in ('admin', 'dev', 'uploader')


async def list_users_by_role(
    pool: Optional[Pool],
    role: str
) -> List[Record]:
    """Get all users with a specific role."""
    if not db.is_connected:
        return []
    
    try:
        return await db.fetch(
            "SELECT user_id, username, first_name, role FROM users WHERE role = $1",
            role.lower()
        )
    except Exception as e:
        error_logger.error(f"Error listing users by role: {e}")
        return []