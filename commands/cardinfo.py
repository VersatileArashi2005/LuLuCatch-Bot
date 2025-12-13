# ============================================================
# 📁 File: commands/cardinfo.py
# 📍 Location: telegram_card_bot/commands/cardinfo.py
# 📝 Description: Modern card info view with actions
# ============================================================

from typing import Optional
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode

from config import Config
from db import (
    db,
    get_card_with_details,
    get_card_owners,
    check_user_owns_card,
    get_user_card_quantity,
    ensure_user,
)
from utils.logger import app_logger, error_logger, log_command
from utils.rarity import rarity_to_text, get_rarity, is_rare_plus
from utils.constants import (
    RARITY_EMOJIS,
    RARITY_NAMES,
    ButtonLabels,
    Templates,
)
from utils.ui import format_card_caption, format_error


# ============================================================
# 🎴 Card Info Command
# ============================================================

async def cardinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /cardinfo <card_id> command.
    Shows detailed card information with owner stats and actions.
    """
    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    chat = update.effective_chat

    log_command(user.id, "cardinfo", chat.id)

    # Ensure user exists
    await ensure_user(
        pool=None,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

    # Check database
    if not db.is_connected:
        await update.message.reply_text(
            format_error("database"),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Check arguments
    if not context.args:
        bot_username = context.bot.username or Config.BOT_USERNAME
        await update.message.reply_text(
            f"🔍 *Card Info*\n\n"
            f"Usage: `/cardinfo <card_id>`\n\n"
            f"Examples:\n"
            f"• `/cardinfo 42`\n"
            f"• `/cardinfo 100`\n\n"
            f"💡 Find card IDs:\n"
            f"• In your /harem\n"
            f"• Via inline: `@{bot_username} naruto`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Parse card ID
    try:
        card_id = int(context.args[0].replace("#", ""))
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid card ID. Use a number like `/cardinfo 42`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Show card info
    await show_card_info(
        update=update,
        context=context,
        card_id=card_id,
        viewer_user_id=user.id
    )


# ============================================================
# 📄 Display Card Info
# ============================================================

async def show_card_info(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    card_id: int,
    viewer_user_id: int,
    from_callback: bool = False
) -> None:
    """Display detailed card information with modern UI."""
    
    # Get card details
    card = await get_card_with_details(None, card_id)

    if not card:
        error_msg = f"❌ Card `#{card_id}` not found."
        
        if from_callback and update.callback_query:
            await update.callback_query.answer("Card not found!", show_alert=True)
        else:
            await update.message.reply_text(error_msg, parse_mode=ParseMode.MARKDOWN)
        return

    # Extract info
    character = card.get("character_name", "Unknown")
    anime = card.get("anime", "Unknown")
    rarity = card.get("rarity", 1)
    photo_file_id = card.get("photo_file_id")
    total_caught = card.get("total_caught", 0)
    unique_owners = card.get("unique_owners", 0)
    total_circulation = card.get("total_in_circulation", 0)

    # Rarity details
    rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity)
    rarity_obj = get_rarity(rarity)

    # Check viewer ownership
    viewer_owns = await check_user_owns_card(None, viewer_user_id, card_id)
    viewer_qty = 0
    if viewer_owns:
        viewer_qty = await get_user_card_quantity(None, viewer_user_id, card_id)

    # Get top owners
    owners = await get_card_owners(None, card_id, limit=5)

    # Build owners text
    if owners:
        owner_lines = []
        for i, owner in enumerate(owners, 1):
            name = owner.get("first_name", "Unknown")
            qty = owner.get("quantity", 1)
            is_fav = "❤️" if owner.get("is_favorite") else ""
            owner_lines.append(f"{i}. {name} ×{qty} {is_fav}")
        owners_text = "\n".join(owner_lines)
    else:
        owners_text = "_No owners yet_"

    # Ownership status
    if viewer_owns:
        ownership_text = f"✅ You own ×{viewer_qty}"
    else:
        ownership_text = "❌ Not in your collection"

    # Build caption
    caption = (
        f"{rarity_emoji} *{character}*\n\n"
        f"🎬 *Anime:* {anime}\n"
        f"{rarity_emoji} *Rarity:* {rarity_name}\n"
        f"📊 *Drop Rate:* {rarity_prob}%\n"
        f"🆔 *ID:* `#{card_id}`\n\n"
        f"📈 *Statistics*\n"
        f"├ Caught: {total_caught:,} times\n"
        f"├ Owners: {unique_owners:,} unique\n"
        f"└ Circulation: {total_circulation:,}\n\n"
        f"👥 *Top Owners*\n"
        f"{owners_text}\n\n"
        f"{ownership_text}"
    )

    # Build keyboard
    keyboard = build_cardinfo_keyboard(
        card_id=card_id,
        viewer_user_id=viewer_user_id,
        viewer_owns=viewer_owns,
        anime=anime,
        bot_username=context.bot.username or Config.BOT_USERNAME
    )

    # Send message
    if photo_file_id:
        if from_callback and update.callback_query:
            try:
                # Try to edit media
                await update.callback_query.edit_message_caption(
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=keyboard
                )
                await update.callback_query.answer()
            except Exception:
                # Delete and send new if can't edit
                try:
                    await update.callback_query.message.delete()
                except Exception:
                    pass
                await context.bot.send_photo(
                    chat_id=update.callback_query.message.chat_id,
                    photo=photo_file_id,
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=keyboard
                )
                await update.callback_query.answer()
        else:
            await update.message.reply_photo(
                photo=photo_file_id,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
    else:
        # No photo
        if from_callback and update.callback_query:
            await update.callback_query.edit_message_text(
                text=caption,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
            await update.callback_query.answer()
        else:
            await update.message.reply_text(
                text=caption,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )


# ============================================================
# ⌨️ Keyboard Builder
# ============================================================

def build_cardinfo_keyboard(
    card_id: int,
    viewer_user_id: int,
    viewer_owns: bool,
    anime: str,
    bot_username: str
) -> InlineKeyboardMarkup:
    """Build action keyboard for card info."""
    
    buttons = []

    # Row 1: Actions based on ownership
    action_row = []
    
    if viewer_owns:
        action_row.append(
            InlineKeyboardButton(
                "🔄 Offer Trade",
                callback_data=f"ci_trade:{card_id}"
            )
        )
    
    # Search similar (same anime)
    action_row.append(
        InlineKeyboardButton(
            "🔍 Same Anime",
            switch_inline_query_current_chat=anime[:30]
        )
    )
    
    if action_row:
        buttons.append(action_row)

    # Row 2: View in collection / Share
    buttons.append([
        InlineKeyboardButton(
            "📦 My Collection",
            switch_inline_query_current_chat=f"collection.{viewer_user_id}"
        ),
        InlineKeyboardButton(
            "📤 Share",
            switch_inline_query=f"#{card_id}"
        )
    ])

    # Row 3: Close
    buttons.append([
        InlineKeyboardButton(ButtonLabels.CLOSE, callback_data="ci_close")
    ])

    return InlineKeyboardMarkup(buttons)


# ============================================================
# 🔘 Callback Handlers
# ============================================================

async def cardinfo_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle card info callbacks."""
    
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data

    # Close
    if data == "ci_close":
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.answer()
        return

    # Noop
    if data == "noop":
        await query.answer()
        return

    # View card info: ci:{card_id}
    if data.startswith("ci:"):
        try:
            card_id = int(data.split(":")[1])
            viewer_user_id = query.from_user.id

            await show_card_info(
                update=update,
                context=context,
                card_id=card_id,
                viewer_user_id=viewer_user_id,
                from_callback=True
            )
        except (ValueError, IndexError):
            await query.answer("Invalid card ID", show_alert=True)
        return

    # Trade from cardinfo: ci_trade:{card_id}
    if data.startswith("ci_trade:"):
        try:
            card_id = int(data.split(":")[1])
            await query.answer(
                f"💡 To trade card #{card_id}:\n/offertrade {card_id} <user_id>",
                show_alert=True
            )
        except (ValueError, IndexError):
            await query.answer("Error", show_alert=True)
        return


# ============================================================
# 🔗 Quick Card View (from other modules)
# ============================================================

async def quick_card_view(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    card_id: int,
    viewer_user_id: int
) -> None:
    """
    Quick card view function for use by other modules.
    Sends card info to specified chat.
    """
    card = await get_card_with_details(None, card_id)
    
    if not card:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Card `#{card_id}` not found.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    character = card.get("character_name", "Unknown")
    anime = card.get("anime", "Unknown")
    rarity = card.get("rarity", 1)
    photo_file_id = card.get("photo_file_id")
    
    rarity_name, prob, emoji = rarity_to_text(rarity)
    
    caption = (
        f"{emoji} *{character}*\n\n"
        f"🎬 {anime}\n"
        f"{emoji} {rarity_name} ({prob}%)\n"
        f"🆔 `#{card_id}`"
    )
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "📋 Full Details",
            callback_data=f"ci:{card_id}"
        )
    ]])
    
    if photo_file_id:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=photo_file_id,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )


# ============================================================
# 📦 Handler Registration
# ============================================================

def register_cardinfo_handlers(application: Application) -> None:
    """Register card info handlers."""
    
    # Command
    application.add_handler(CommandHandler("cardinfo", cardinfo_command))
    application.add_handler(CommandHandler("card", cardinfo_command))  # Alias

    # Callbacks
    application.add_handler(
        CallbackQueryHandler(cardinfo_callback_handler, pattern=r"^ci:")
    )
    application.add_handler(
        CallbackQueryHandler(cardinfo_callback_handler, pattern=r"^ci_")
    )

    app_logger.info("✅ Card info handlers registered")