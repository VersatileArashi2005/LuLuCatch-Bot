# ============================================================
# 📁 File: handlers/roles.py
# 📍 Location: telegram_card_bot/handlers/roles.py
# 📝 Description: Role management commands (Admin, Dev, Uploader)
# ============================================================

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
)

from db import (
    db,
    add_role,
    remove_role,
    get_user_role,
    check_is_owner,
    check_is_admin,
    list_users_by_role,
    get_user_by_id,
)
from config import Config
from utils.logger import app_logger, error_logger


# ============================================================
# 🔧 Helper Functions
# ============================================================

async def get_target_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[int | None, str | None]:
    """
    Get target user ID from reply or command argument.
    
    Returns:
        Tuple of (user_id, first_name) or (None, None) if not found
    """
    # Check if replying to a message
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        if target_user:
            return target_user.id, target_user.first_name
    
    # Check command arguments
    if context.args and len(context.args) > 0:
        try:
            user_id = int(context.args[0])
            # Try to get user info from database
            user = await get_user_by_id(None, user_id)
            if user:
                return user_id, user.get("first_name", "Unknown")
            return user_id, "Unknown"
        except ValueError:
            return None, None
    
    return None, None


def get_role_emoji(role: str) -> str:
    """Get emoji for a role."""
    role_emojis = {
        "admin": "👑",
        "dev": "⚙️",
        "uploader": "📤",
    }
    return role_emojis.get(role.lower(), "👤")


# ============================================================
# 👑 Add Admin Command
# ============================================================

async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /addadmin <reply> or <user_id>
    Assigns Admin role to a user. Only owner can use this.
    """
    if not update.message or not update.effective_user:
        return
    
    user_id = update.effective_user.id
    
    # Only owner can add admins
    if not await check_is_owner(user_id):
        await update.message.reply_text(
            "❌ *ᴀᴄᴄᴇꜱꜱ ᴅᴇɴɪᴇᴅ*\n\n"
            "Only the bot owner can assign Admin roles.",
            parse_mode="Markdown"
        )
        return
    
    # Get target user
    target_id, target_name = await get_target_user_id(update, context)
    
    if not target_id:
        await update.message.reply_text(
            "⚠️ *ᴜꜱᴀɢᴇ*\n\n"
            "Reply to a user's message or provide user ID:\n"
            "`/addadmin <user_id>`\n\n"
            "*Example:*\n"
            "• `/addadmin 123456789`\n"
            "• Reply to a message with `/addadmin`",
            parse_mode="Markdown"
        )
        return
    
    # Check if target is already owner
    if await check_is_owner(target_id):
        await update.message.reply_text(
            "ℹ️ This user is the bot owner!",
            parse_mode="Markdown"
        )
        return
    
    # Add admin role
    success = await add_role(None, target_id, "admin")
    
    if success:
        await update.message.reply_text(
            f"✅ *ᴀᴅᴍɪɴ ᴀꜱꜱɪɢɴᴇᴅ*\n\n"
            f"👑 *User:* {target_name}\n"
            f"🆔 *ID:* `{target_id}`\n"
            f"🎭 *Role:* Admin\n\n"
            f"_This user can now manage the bot!_",
            parse_mode="Markdown"
        )
        app_logger.info(f"👑 Admin role assigned to {target_id} by {user_id}")
    else:
        await update.message.reply_text(
            "❌ Failed to assign Admin role. Please try again.",
            parse_mode="Markdown"
        )


# ============================================================
# ⚙️ Add Dev Command
# ============================================================

async def add_dev_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /adddev <reply> or <user_id>
    Assigns Dev role to a user. Only owner can use this.
    """
    if not update.message or not update.effective_user:
        return
    
    user_id = update.effective_user.id
    
    # Only owner can add devs
    if not await check_is_owner(user_id):
        await update.message.reply_text(
            "❌ *ᴀᴄᴄᴇꜱꜱ ᴅᴇɴɪᴇᴅ*\n\n"
            "Only the bot owner can assign Dev roles.",
            parse_mode="Markdown"
        )
        return
    
    # Get target user
    target_id, target_name = await get_target_user_id(update, context)
    
    if not target_id:
        await update.message.reply_text(
            "⚠️ *ᴜꜱᴀɢᴇ*\n\n"
            "Reply to a user's message or provide user ID:\n"
            "`/adddev <user_id>`\n\n"
            "*Example:*\n"
            "• `/adddev 123456789`\n"
            "• Reply to a message with `/adddev`",
            parse_mode="Markdown"
        )
        return
    
    # Check if target is already owner
    if await check_is_owner(target_id):
        await update.message.reply_text(
            "ℹ️ This user is the bot owner!",
            parse_mode="Markdown"
        )
        return
    
    # Add dev role
    success = await add_role(None, target_id, "dev")
    
    if success:
        await update.message.reply_text(
            f"✅ *ᴅᴇᴠ ᴀꜱꜱɪɢɴᴇᴅ*\n\n"
            f"⚙️ *User:* {target_name}\n"
            f"🆔 *ID:* `{target_id}`\n"
            f"🎭 *Role:* Developer\n\n"
            f"_This user has developer access!_",
            parse_mode="Markdown"
        )
        app_logger.info(f"⚙️ Dev role assigned to {target_id} by {user_id}")
    else:
        await update.message.reply_text(
            "❌ Failed to assign Dev role. Please try again.",
            parse_mode="Markdown"
        )


# ============================================================
# 📤 Add Uploader Command
# ============================================================

async def add_uploader_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /adduploader <reply> or <user_id>
    Assigns Uploader role to a user. Owner and Admins can use this.
    """
    if not update.message or not update.effective_user:
        return
    
    user_id = update.effective_user.id
    
    # Owner and Admins can add uploaders
    if not await check_is_owner(user_id) and not await check_is_admin(user_id):
        await update.message.reply_text(
            "❌ *ᴀᴄᴄᴇꜱꜱ ᴅᴇɴɪᴇᴅ*\n\n"
            "Only the owner and admins can assign Uploader roles.",
            parse_mode="Markdown"
        )
        return
    
    # Get target user
    target_id, target_name = await get_target_user_id(update, context)
    
    if not target_id:
        await update.message.reply_text(
            "⚠️ *ᴜꜱᴀɢᴇ*\n\n"
            "Reply to a user's message or provide user ID:\n"
            "`/adduploader <user_id>`\n\n"
            "*Example:*\n"
            "• `/adduploader 123456789`\n"
            "• Reply to a message with `/adduploader`",
            parse_mode="Markdown"
        )
        return
    
    # Add uploader role
    success = await add_role(None, target_id, "uploader")
    
    if success:
        await update.message.reply_text(
            f"✅ *ᴜᴘʟᴏᴀᴅᴇʀ ᴀꜱꜱɪɢɴᴇᴅ*\n\n"
            f"📤 *User:* {target_name}\n"
            f"🆔 *ID:* `{target_id}`\n"
            f"🎭 *Role:* Uploader\n\n"
            f"_This user can now upload cards!_",
            parse_mode="Markdown"
        )
        app_logger.info(f"📤 Uploader role assigned to {target_id} by {user_id}")
    else:
        await update.message.reply_text(
            "❌ Failed to assign Uploader role. Please try again.",
            parse_mode="Markdown"
        )


# ============================================================
# 🚫 Remove Role Command
# ============================================================

async def remove_role_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /removerole <reply> or <user_id>
    Removes any role from a user. Only owner can use this.
    """
    if not update.message or not update.effective_user:
        return
    
    user_id = update.effective_user.id
    
    # Only owner can remove roles
    if not await check_is_owner(user_id):
        await update.message.reply_text(
            "❌ *ᴀᴄᴄᴇꜱꜱ ᴅᴇɴɪᴇᴅ*\n\n"
            "Only the bot owner can remove roles.",
            parse_mode="Markdown"
        )
        return
    
    # Get target user
    target_id, target_name = await get_target_user_id(update, context)
    
    if not target_id:
        await update.message.reply_text(
            "⚠️ *ᴜꜱᴀɢᴇ*\n\n"
            "Reply to a user's message or provide user ID:\n"
            "`/removerole <user_id>`\n\n"
            "*Example:*\n"
            "• `/removerole 123456789`\n"
            "• Reply to a message with `/removerole`",
            parse_mode="Markdown"
        )
        return
    
    # Get current role
    current_role = await get_user_role(None, target_id)
    
    if not current_role:
        await update.message.reply_text(
            f"ℹ️ *{target_name}* doesn't have any role.",
            parse_mode="Markdown"
        )
        return
    
    # Remove role
    success = await remove_role(None, target_id)
    
    if success:
        await update.message.reply_text(
            f"✅ *ʀᴏʟᴇ ʀᴇᴍᴏᴠᴇᴅ*\n\n"
            f"👤 *User:* {target_name}\n"
            f"🆔 *ID:* `{target_id}`\n"
            f"🎭 *Previous Role:* {current_role.title()}\n\n"
            f"_Role has been removed._",
            parse_mode="Markdown"
        )
        app_logger.info(f"🚫 Role removed from {target_id} by {user_id}")
    else:
        await update.message.reply_text(
            "❌ Failed to remove role. Please try again.",
            parse_mode="Markdown"
        )


# ============================================================
# 📋 List Roles Command
# ============================================================

async def list_roles_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /roles - List all users with roles
    """
    if not update.message or not update.effective_user:
        return
    
    user_id = update.effective_user.id
    
    # Only owner and admins can view roles
    if not await check_is_owner(user_id) and not await check_is_admin(user_id):
        await update.message.reply_text(
            "❌ *ᴀᴄᴄᴇꜱꜱ ᴅᴇɴɪᴇᴅ*\n\n"
            "Only the owner and admins can view roles.",
            parse_mode="Markdown"
        )
        return
    
    # Get users by role
    admins = await list_users_by_role(None, "admin")
    devs = await list_users_by_role(None, "dev")
    uploaders = await list_users_by_role(None, "uploader")
    
    # Build response
    response = "👑 *ʀᴏʟᴇ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ*\n\n"
    
    # Owner
    response += f"🌟 *ᴏᴡɴᴇʀ*\n"
    response += f"  └ `{Config.OWNER_ID}`\n\n"
    
    # Admins
    response += f"👑 *ᴀᴅᴍɪɴꜱ* ({len(admins)})\n"
    if admins:
        for admin in admins:
            name = admin.get("first_name") or admin.get("username") or "Unknown"
            response += f"  └ {name} (`{admin['user_id']}`)\n"
    else:
        response += "  └ _No admins_\n"
    response += "\n"
    
    # Devs
    response += f"⚙️ *ᴅᴇᴠᴇʟᴏᴘᴇʀꜱ* ({len(devs)})\n"
    if devs:
        for dev in devs:
            name = dev.get("first_name") or dev.get("username") or "Unknown"
            response += f"  └ {name} (`{dev['user_id']}`)\n"
    else:
        response += "  └ _No developers_\n"
    response += "\n"
    
    # Uploaders
    response += f"📤 *ᴜᴘʟᴏᴀᴅᴇʀꜱ* ({len(uploaders)})\n"
    if uploaders:
        for uploader in uploaders:
            name = uploader.get("first_name") or uploader.get("username") or "Unknown"
            response += f"  └ {name} (`{uploader['user_id']}`)\n"
    else:
        response += "  └ _No uploaders_\n"
    
    await update.message.reply_text(response, parse_mode="Markdown")


# ============================================================
# 🔍 My Role Command
# ============================================================

async def my_role_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /myrole - Check your own role
    """
    if not update.message or not update.effective_user:
        return
    
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    # Check if owner
    if await check_is_owner(user_id):
        await update.message.reply_text(
            f"🌟 *ʏᴏᴜʀ ʀᴏʟᴇ*\n\n"
            f"👤 *Name:* {user_name}\n"
            f"🆔 *ID:* `{user_id}`\n"
            f"🎭 *Role:* 🌟 Owner\n\n"
            f"_You have full access to all commands!_",
            parse_mode="Markdown"
        )
        return
    
    # Get role from database
    role = await get_user_role(None, user_id)
    
    if role:
        emoji = get_role_emoji(role)
        await update.message.reply_text(
            f"🎭 *ʏᴏᴜʀ ʀᴏʟᴇ*\n\n"
            f"👤 *Name:* {user_name}\n"
            f"🆔 *ID:* `{user_id}`\n"
            f"🎭 *Role:* {emoji} {role.title()}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"👤 *ʏᴏᴜʀ ʀᴏʟᴇ*\n\n"
            f"👤 *Name:* {user_name}\n"
            f"🆔 *ID:* `{user_id}`\n"
            f"🎭 *Role:* None\n\n"
            f"_You are a regular user._",
            parse_mode="Markdown"
        )


# ============================================================
# 📦 Handler Registration
# ============================================================

# Command handlers
add_admin_handler = CommandHandler("addadmin", add_admin_command)
add_dev_handler = CommandHandler("adddev", add_dev_command)
add_uploader_handler = CommandHandler("adduploader", add_uploader_command)
remove_role_handler = CommandHandler("removerole", remove_role_command)
list_roles_handler = CommandHandler("roles", list_roles_command)
my_role_handler = CommandHandler("myrole", my_role_command)


def register_role_handlers(application) -> None:
    """Register all role management handlers."""
    application.add_handler(add_admin_handler)
    application.add_handler(add_dev_handler)
    application.add_handler(add_uploader_handler)
    application.add_handler(remove_role_handler)
    application.add_handler(list_roles_handler)
    application.add_handler(my_role_handler)
    
    app_logger.info("✅ Role management handlers registered")