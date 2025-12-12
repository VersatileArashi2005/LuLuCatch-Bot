# ============================================================
# 📁 File: handlers/roles.py
# 📍 Location: telegram_card_bot/handlers/roles.py
# 📝 Description: Professional Role Management System
# 
# Role Hierarchy:
#   🌟 Owner (Full access - from config)
#   ⚙️ Dev (Full access, sensitive actions need owner approval)
#   👑 Admin (Can ban/unban, grant uploader role)
#   📤 Uploader (Can upload cards)
# ============================================================

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes

from config import Config
from db import db, ensure_user, get_user_by_id
from utils.logger import app_logger, error_logger


# ============================================================
# 👑 Role Check Functions
# ============================================================

async def get_user_role(user_id: int) -> str | None:
    """Get user's role from database."""
    if not db.is_connected:
        return None
    try:
        return await db.fetchval("SELECT role FROM users WHERE user_id = $1", user_id)
    except Exception as e:
        error_logger.error(f"Error getting role: {e}")
        return None


async def is_owner(user_id: int) -> bool:
    """Check if user is the bot owner."""
    return user_id == Config.OWNER_ID


async def is_dev(user_id: int) -> bool:
    """Check if user is dev or higher."""
    if await is_owner(user_id):
        return True
    role = await get_user_role(user_id)
    return role == "dev"


async def is_admin(user_id: int) -> bool:
    """Check if user is admin or higher."""
    if await is_owner(user_id):
        return True
    role = await get_user_role(user_id)
    return role in ("dev", "admin")


async def is_uploader(user_id: int) -> bool:
    """Check if user can upload cards."""
    if await is_owner(user_id):
        return True
    role = await get_user_role(user_id)
    return role in ("dev", "admin", "uploader")


async def can_manage_role(manager_id: int, target_role: str) -> bool:
    """Check if manager can assign/remove a specific role."""
    if await is_owner(manager_id):
        return True
    
    manager_role = await get_user_role(manager_id)
    
    # Dev can manage admin and uploader
    if manager_role == "dev" and target_role in ("admin", "uploader"):
        return True
    
    # Admin can only manage uploader
    if manager_role == "admin" and target_role == "uploader":
        return True
    
    return False


# ============================================================
# 🔧 Role Management Functions
# ============================================================

async def set_user_role(user_id: int, role: str | None) -> bool:
    """Set a user's role in the database."""
    if not db.is_connected:
        return False
    
    valid_roles = {"dev", "admin", "uploader", None}
    if role not in valid_roles:
        return False
    
    try:
        # Ensure user exists first
        await db.execute(
            """
            INSERT INTO users (user_id, role)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET
                role = $2,
                updated_at = NOW()
            """,
            user_id, role
        )
        return True
    except Exception as e:
        error_logger.error(f"Error setting role: {e}")
        return False


async def get_users_by_role(role: str) -> list:
    """Get all users with a specific role."""
    if not db.is_connected:
        return []
    try:
        return await db.fetch(
            "SELECT user_id, username, first_name FROM users WHERE role = $1",
            role
        )
    except Exception as e:
        error_logger.error(f"Error getting users by role: {e}")
        return []


# ============================================================
# 🎯 Helper Functions
# ============================================================

async def get_target_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple:
    """Get target user from reply or args. Returns (user_id, name) or (None, None)."""
    
    # From reply
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        if user:
            return user.id, user.first_name
    
    # From args
    if context.args:
        try:
            user_id = int(context.args[0])
            # Try to get name from database
            user_data = await get_user_by_id(None, user_id)
            name = user_data.get("first_name", "Unknown") if user_data else "Unknown"
            return user_id, name
        except ValueError:
            pass
    
    return None, None


def get_role_emoji(role: str | None) -> str:
    """Get emoji for a role."""
    emojis = {
        "dev": "⚙️",
        "admin": "👑",
        "uploader": "📤",
        None: "👤"
    }
    return emojis.get(role, "👤")


def get_role_display(role: str | None) -> str:
    """Get display name for a role."""
    names = {
        "dev": "Developer",
        "admin": "Admin",
        "uploader": "Uploader",
        None: "User"
    }
    return names.get(role, "User")


# ============================================================
# 📤 /adduploader Command
# ============================================================

async def add_uploader_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /adduploader <reply> or <user_id>
    Assigns Uploader role. Admins and above can use.
    """
    user = update.effective_user
    
    if not await is_admin(user.id):
        await update.message.reply_text(
            "❌ *ᴀᴄᴄᴇꜱꜱ ᴅᴇɴɪᴇᴅ*\n\n"
            "Only Admins can assign Uploader roles.",
            parse_mode="Markdown"
        )
        return
    
    target_id, target_name = await get_target_user(update, context)
    
    if not target_id:
        await update.message.reply_text(
            "📤 *ᴀᴅᴅ ᴜᴘʟᴏᴀᴅᴇʀ*\n\n"
            "*Usage:*\n"
            "• Reply to user: `/adduploader`\n"
            "• With ID: `/adduploader 123456789`",
            parse_mode="Markdown"
        )
        return
    
    if await is_owner(target_id):
        await update.message.reply_text("ℹ️ This user is the bot owner!")
        return
    
    success = await set_user_role(target_id, "uploader")
    
    if success:
        await update.message.reply_text(
            f"✅ *ᴜᴘʟᴏᴀᴅᴇʀ ᴀꜱꜱɪɢɴᴇᴅ*\n\n"
            f"📤 *User:* {target_name}\n"
            f"🆔 *ID:* `{target_id}`\n"
            f"🎭 *Role:* Uploader\n\n"
            f"_This user can now upload cards!_",
            parse_mode="Markdown"
        )
        app_logger.info(f"📤 Uploader role assigned to {target_id} by {user.id}")
    else:
        await update.message.reply_text("❌ Failed to assign role.")


# ============================================================
# 👑 /addadmin Command
# ============================================================

async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /addadmin <reply> or <user_id>
    Assigns Admin role. Only Owner and Devs can use.
    """
    user = update.effective_user
    
    if not await is_dev(user.id):
        await update.message.reply_text(
            "❌ *ᴀᴄᴄᴇꜱꜱ ᴅᴇɴɪᴇᴅ*\n\n"
            "Only Owner and Developers can assign Admin roles.",
            parse_mode="Markdown"
        )
        return
    
    target_id, target_name = await get_target_user(update, context)
    
    if not target_id:
        await update.message.reply_text(
            "👑 *ᴀᴅᴅ ᴀᴅᴍɪɴ*\n\n"
            "*Usage:*\n"
            "• Reply to user: `/addadmin`\n"
            "• With ID: `/addadmin 123456789`",
            parse_mode="Markdown"
        )
        return
    
    if await is_owner(target_id):
        await update.message.reply_text("ℹ️ This user is the bot owner!")
        return
    
    success = await set_user_role(target_id, "admin")
    
    if success:
        await update.message.reply_text(
            f"✅ *ᴀᴅᴍɪɴ ᴀꜱꜱɪɢɴᴇᴅ*\n\n"
            f"👑 *User:* {target_name}\n"
            f"🆔 *ID:* `{target_id}`\n"
            f"🎭 *Role:* Admin\n\n"
            f"_This user can now manage the bot!_",
            parse_mode="Markdown"
        )
        app_logger.info(f"👑 Admin role assigned to {target_id} by {user.id}")
    else:
        await update.message.reply_text("❌ Failed to assign role.")


# ============================================================
# ⚙️ /adddev Command
# ============================================================

async def add_dev_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /adddev <reply> or <user_id>
    Assigns Developer role. Only Owner can use.
    """
    user = update.effective_user
    
    if not await is_owner(user.id):
        await update.message.reply_text(
            "❌ *ᴀᴄᴄᴇꜱꜱ ᴅᴇɴɪᴇᴅ*\n\n"
            "Only the bot Owner can assign Developer roles.",
            parse_mode="Markdown"
        )
        return
    
    target_id, target_name = await get_target_user(update, context)
    
    if not target_id:
        await update.message.reply_text(
            "⚙️ *ᴀᴅᴅ ᴅᴇᴠᴇʟᴏᴘᴇʀ*\n\n"
            "*Usage:*\n"
            "• Reply to user: `/adddev`\n"
            "• With ID: `/adddev 123456789`",
            parse_mode="Markdown"
        )
        return
    
    if await is_owner(target_id):
        await update.message.reply_text("ℹ️ This user is the bot owner!")
        return
    
    success = await set_user_role(target_id, "dev")
    
    if success:
        await update.message.reply_text(
            f"✅ *ᴅᴇᴠᴇʟᴏᴘᴇʀ ᴀꜱꜱɪɢɴᴇᴅ*\n\n"
            f"⚙️ *User:* {target_name}\n"
            f"🆔 *ID:* `{target_id}`\n"
            f"🎭 *Role:* Developer\n\n"
            f"_This user has developer access!_",
            parse_mode="Markdown"
        )
        app_logger.info(f"⚙️ Dev role assigned to {target_id} by {user.id}")
    else:
        await update.message.reply_text("❌ Failed to assign role.")


# ============================================================
# 🚫 /removerole Command
# ============================================================

async def remove_role_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /removerole <reply> or <user_id>
    Removes any role from a user.
    """
    user = update.effective_user
    
    if not await is_admin(user.id):
        await update.message.reply_text("❌ *Access Denied*", parse_mode="Markdown")
        return
    
    target_id, target_name = await get_target_user(update, context)
    
    if not target_id:
        await update.message.reply_text(
            "🚫 *ʀᴇᴍᴏᴠᴇ ʀᴏʟᴇ*\n\n"
            "*Usage:*\n"
            "• Reply to user: `/removerole`\n"
            "• With ID: `/removerole 123456789`",
            parse_mode="Markdown"
        )
        return
    
    # Check permissions
    target_role = await get_user_role(target_id)
    
    if not target_role:
        await update.message.reply_text(f"ℹ️ *{target_name}* doesn't have any role.", parse_mode="Markdown")
        return
    
    # Check if user can remove this role
    if not await can_manage_role(user.id, target_role):
        await update.message.reply_text(
            f"❌ You cannot remove the *{get_role_display(target_role)}* role.",
            parse_mode="Markdown"
        )
        return
    
    success = await set_user_role(target_id, None)
    
    if success:
        await update.message.reply_text(
            f"✅ *ʀᴏʟᴇ ʀᴇᴍᴏᴠᴇᴅ*\n\n"
            f"👤 *User:* {target_name}\n"
            f"🆔 *ID:* `{target_id}`\n"
            f"🎭 *Previous:* {get_role_display(target_role)}",
            parse_mode="Markdown"
        )
        app_logger.info(f"🚫 Role removed from {target_id} by {user.id}")
    else:
        await update.message.reply_text("❌ Failed to remove role.")


# ============================================================
# 📋 /roles Command
# ============================================================

async def list_roles_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/roles - List all users with roles."""
    user = update.effective_user
    
    if not await is_admin(user.id):
        await update.message.reply_text("❌ *Access Denied*", parse_mode="Markdown")
        return
    
    devs = await get_users_by_role("dev")
    admins = await get_users_by_role("admin")
    uploaders = await get_users_by_role("uploader")
    
    response = "👑 *ʀᴏʟᴇ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ*\n\n"
    
    # Owner
    response += f"🌟 *ᴏᴡɴᴇʀ*\n"
    response += f"  └ `{Config.OWNER_ID}`\n\n"
    
    # Devs
    response += f"⚙️ *ᴅᴇᴠᴇʟᴏᴘᴇʀꜱ* ({len(devs)})\n"
    if devs:
        for d in devs:
            name = d.get("first_name") or d.get("username") or "Unknown"
            response += f"  └ {name} (`{d['user_id']}`)\n"
    else:
        response += "  └ _None_\n"
    response += "\n"
    
    # Admins
    response += f"👑 *ᴀᴅᴍɪɴꜱ* ({len(admins)})\n"
    if admins:
        for a in admins:
            name = a.get("first_name") or a.get("username") or "Unknown"
            response += f"  └ {name} (`{a['user_id']}`)\n"
    else:
        response += "  └ _None_\n"
    response += "\n"
    
    # Uploaders
    response += f"📤 *ᴜᴘʟᴏᴀᴅᴇʀꜱ* ({len(uploaders)})\n"
    if uploaders:
        for u in uploaders:
            name = u.get("first_name") or u.get("username") or "Unknown"
            response += f"  └ {name} (`{u['user_id']}`)\n"
    else:
        response += "  └ _None_\n"
    
    await update.message.reply_text(response, parse_mode="Markdown")


# ============================================================
# 🔍 /myrole Command
# ============================================================

async def my_role_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/myrole - Check your own role."""
    user = update.effective_user
    
    if await is_owner(user.id):
        role_text = "🌟 Owner"
        desc = "_You have full access to all commands!_"
    else:
        role = await get_user_role(user.id)
        emoji = get_role_emoji(role)
        role_text = f"{emoji} {get_role_display(role)}"
        
        if role == "dev":
            desc = "_You have developer access!_"
        elif role == "admin":
            desc = "_You can manage users and uploaders!_"
        elif role == "uploader":
            desc = "_You can upload cards!_"
        else:
            desc = "_You are a regular user._"
    
    await update.message.reply_text(
        f"🎭 *ʏᴏᴜʀ ʀᴏʟᴇ*\n\n"
        f"👤 *Name:* {user.first_name}\n"
        f"🆔 *ID:* `{user.id}`\n"
        f"🎭 *Role:* {role_text}\n\n"
        f"{desc}",
        parse_mode="Markdown"
    )


# ============================================================
# 📦 Handler Registration
# ============================================================

add_uploader_handler = CommandHandler("adduploader", add_uploader_command)
add_admin_handler = CommandHandler("addadmin", add_admin_command)
add_dev_handler = CommandHandler("adddev", add_dev_command)
remove_role_handler = CommandHandler("removerole", remove_role_command)
list_roles_handler = CommandHandler("roles", list_roles_command)
my_role_handler = CommandHandler("myrole", my_role_command)


def register_role_handlers(application) -> None:
    """Register all role management handlers."""
    application.add_handler(add_uploader_handler)
    application.add_handler(add_admin_handler)
    application.add_handler(add_dev_handler)
    application.add_handler(remove_role_handler)
    application.add_handler(list_roles_handler)
    application.add_handler(my_role_handler)
    
    app_logger.info("✅ Role management handlers registered")