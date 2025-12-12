# ============================================================
# 📁 File: handlers/notifications.py
# 📍 Location: telegram_card_bot/handlers/notifications.py
# 📝 Description: Upload notifications & channel archiving
# ============================================================

import asyncio
from typing import Optional, Dict, Any

from telegram import Bot
from telegram.error import TelegramError, Forbidden, BadRequest

from config import Config
from db import db, get_all_groups
from utils.logger import app_logger, error_logger
from utils.rarity import rarity_to_text


# ============================================================
# 📢 Notify All Groups About New Card
# ============================================================

async def notify_groups_new_card(
    bot: Bot,
    card: Dict[str, Any],
    uploader_name: str,
    uploader_id: int
) -> Dict[str, int]:
    """
    Notify all active groups about a new card upload.
    
    Args:
        bot: Telegram bot instance
        card: Card data dictionary
        uploader_name: Name of the uploader
        uploader_id: User ID of the uploader
    
    Returns:
        Dict with success/fail counts
    """
    if not Config.NOTIFY_GROUPS_ON_UPLOAD:
        return {"success": 0, "failed": 0, "total": 0}
    
    # Get card info
    card_id = card.get("card_id")
    character = card.get("character_name", "Unknown")
    anime = card.get("anime", "Unknown")
    rarity = card.get("rarity", 1)
    photo_file_id = card.get("photo_file_id")
    
    rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity)
    
    # Build notification message
    caption = (
        f"🆕 *ɴᴇᴡ ᴄᴀʀᴅ ᴀᴅᴅᴇᴅ!*\n\n"
        f"✨ *ʟᴏᴏᴋ ᴀᴛ ᴛʜɪꜱ ᴄʜᴀʀᴀᴄᴛᴇʀ!*\n\n"
        f"*{card_id}: {character}*\n"
        f"*{anime}*\n"
        f"*ʀᴀʀɪᴛʏ:* {rarity_emoji} *{rarity_name}*\n\n"
        f"📤 *ᴜᴘʟᴏᴀᴅᴇᴅ ʙʏ:* [{uploader_name}](tg://user?id={uploader_id})"
    )
    
    # Get all active groups
    groups = await get_all_groups(None, active_only=True)
    
    if not groups:
        return {"success": 0, "failed": 0, "total": 0}
    
    success_count = 0
    fail_count = 0
    
    app_logger.info(f"📢 Notifying {len(groups)} groups about card #{card_id}")
    
    for group in groups:
        group_id = group["group_id"]
        
        try:
            if photo_file_id:
                await bot.send_photo(
                    chat_id=group_id,
                    photo=photo_file_id,
                    caption=caption,
                    parse_mode="Markdown"
                )
            else:
                await bot.send_message(
                    chat_id=group_id,
                    text=caption,
                    parse_mode="Markdown"
                )
            
            success_count += 1
            
            # Rate limiting
            if success_count % 20 == 0:
                await asyncio.sleep(1)
                
        except Forbidden:
            # Bot was kicked from group
            fail_count += 1
            try:
                await db.execute(
                    "UPDATE groups SET is_active = FALSE WHERE group_id = $1",
                    group_id
                )
            except Exception:
                pass
                
        except BadRequest as e:
            fail_count += 1
            error_logger.warning(f"Failed to notify group {group_id}: {e}")
            
        except TelegramError as e:
            fail_count += 1
            error_logger.warning(f"Failed to notify group {group_id}: {e}")
            
        except Exception as e:
            fail_count += 1
            error_logger.error(f"Unexpected error notifying group {group_id}: {e}")
    
    app_logger.info(
        f"📢 Notification complete: {success_count} sent, {fail_count} failed"
    )
    
    return {
        "success": success_count,
        "failed": fail_count,
        "total": len(groups)
    }


# ============================================================
# 📺 Archive Card to Database Channel
# ============================================================

async def archive_card_to_channel(
    bot: Bot,
    card: Dict[str, Any],
    uploader_name: str,
    uploader_id: int
) -> bool:
    """
    Post card to the database channel for archiving.
    
    Args:
        bot: Telegram bot instance
        card: Card data dictionary
        uploader_name: Name of the uploader
        uploader_id: User ID of the uploader
    
    Returns:
        True if successful, False otherwise
    """
    channel_id = Config.DATABASE_CHANNEL_ID
    
    if not channel_id:
        app_logger.warning("📺 DATABASE_CHANNEL_ID not configured, skipping archive")
        return False
    
    # Get card info
    card_id = card.get("card_id")
    character = card.get("character_name", "Unknown")
    anime = card.get("anime", "Unknown")
    rarity = card.get("rarity", 1)
    photo_file_id = card.get("photo_file_id")
    
    rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity)
    
    # Build archive message
    caption = (
        f"🎴 *ᴄᴀʀᴅ ᴅᴀᴛᴀʙᴀꜱᴇ*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 *ᴄᴀʀᴅ ɪᴅ:* `#{card_id}`\n"
        f"👤 *ᴄʜᴀʀᴀᴄᴛᴇʀ:* *{character}*\n"
        f"🎬 *ᴀɴɪᴍᴇ:* *{anime}*\n"
        f"✨ *ʀᴀʀɪᴛʏ:* {rarity_emoji} *{rarity_name}*\n"
        f"📊 *ᴅʀᴏᴘ ʀᴀᴛᴇ:* `{rarity_prob}%`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📤 *ᴜᴘʟᴏᴀᴅᴇᴅ ʙʏ:* [{uploader_name}](tg://user?id={uploader_id})\n\n"
        f"#card{card_id} #{anime.replace(' ', '_')[:20]}"
    )
    
    try:
        if photo_file_id:
            await bot.send_photo(
                chat_id=channel_id,
                photo=photo_file_id,
                caption=caption,
                parse_mode="Markdown"
            )
        else:
            await bot.send_message(
                chat_id=channel_id,
                text=caption,
                parse_mode="Markdown"
            )
        
        app_logger.info(f"📺 Card #{card_id} archived to channel")
        return True
        
    except Forbidden:
        error_logger.error(
            f"📺 Cannot post to channel {channel_id} - Bot is not admin or channel doesn't exist"
        )
        return False
        
    except BadRequest as e:
        error_logger.error(f"📺 Bad request posting to channel: {e}")
        return False
        
    except TelegramError as e:
        error_logger.error(f"📺 Error posting to channel: {e}")
        return False
        
    except Exception as e:
        error_logger.error(f"📺 Unexpected error posting to channel: {e}", exc_info=True)
        return False


# ============================================================
# 🔔 Combined Notification Function
# ============================================================

async def send_upload_notifications(
    bot: Bot,
    card: Dict[str, Any],
    uploader_name: str,
    uploader_id: int
) -> Dict[str, Any]:
    """
    Send all notifications for a new card upload.
    
    This function:
    1. Archives the card to the database channel
    2. Notifies all active groups
    
    Args:
        bot: Telegram bot instance
        card: Card data dictionary
        uploader_name: Name of the uploader
        uploader_id: User ID of the uploader
    
    Returns:
        Dict with notification results
    """
    results = {
        "channel_archived": False,
        "groups_notified": 0,
        "groups_failed": 0,
        "groups_total": 0
    }
    
    # 1. Archive to channel
    results["channel_archived"] = await archive_card_to_channel(
        bot, card, uploader_name, uploader_id
    )
    
    # 2. Notify groups
    group_results = await notify_groups_new_card(
        bot, card, uploader_name, uploader_id
    )
    
    results["groups_notified"] = group_results["success"]
    results["groups_failed"] = group_results["failed"]
    results["groups_total"] = group_results["total"]
    
    return results