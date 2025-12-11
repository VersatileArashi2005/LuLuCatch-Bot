# ============================================================
# 📁 File: commands/cardinfo.py
# 📍 Location: telegram_card_bot/commands/cardinfo.py
# 📝 Description: Detailed card information view with owners and actions
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
    ensure_user,
)
from utils.logger import app_logger, error_logger, log_command
from utils.rarity import rarity_to_text


# ============================================================
# 🎴 Card Info Command Handler
# ============================================================

async def cardinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /cardinfo <card_id> command.
    Shows detailed information about a specific card.
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

    # Check DB connection
    if not db.is_connected:
        await update.message.reply_text(
            "⚠️ Database is currently offline. Please try again later.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Check if card ID provided
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "📝 *Usage:* `/cardinfo <card_id>`\n\n"
            "Example: `/cardinfo 42`\n\n"
            "💡 Find card IDs in your collection or inline search.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    card_id = int(context.args[0])

    # Show card info
    await show_card_info(update, context, card_id, user.id)


async def show_card_info(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    card_id: int,
    viewer_user_id: int,
    from_callback: bool = False
) -> None:
    """
    Display detailed card information.
    
    Args:
        update: Telegram update
        context: Bot context
        card_id: Card ID to display
        viewer_user_id: User viewing the card
        from_callback: Whether this is from a callback query
    """
    # Get card with details
    card = await get_card_with_details(None, card_id)

    if not card:
        error_msg = f"❌ Card `#{card_id}` not found."
        
        if from_callback and update.callback_query:
            await update.callback_query.answer("Card not found!", show_alert=True)
        else:
            await update.message.reply_text(error_msg, parse_mode=ParseMode.MARKDOWN)
        return

    # Extract card info
    character = card.get("character_name", "Unknown")
    anime = card.get("anime", "Unknown")
    rarity = card.get("rarity", 1)
    photo_file_id = card.get("photo_file_id")
    total_caught = card.get("total_caught", 0)
    unique_owners = card.get("unique_owners", 0)
    total_in_circulation = card.get("total_in_circulation", 0)

    # Get rarity details
    rarity_name, rarity_prob, rarity_emoji = rarity_to_text(rarity)

    # Get top owners
    owners = await get_card_owners(None, card_id, limit=5)

    # Build owners list
    if owners:
        owners_text = "\n".join([
            f"  • {owner.get('first_name', 'Unknown')} (x{owner.get('quantity', 1)})"
            for owner in owners
        ])
    else:
        owners_text = "  • None yet!"

    # Check if viewer owns this card
    viewer_owns = await check_user_owns_card(None, viewer_user_id, card_id)

    # Build caption
    caption = (
        f"{rarity_emoji} *{character}*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎬 *Anime:* {anime}\n"
        f"🆔 *ID:* `#{card_id}`\n"
        f"✨ *Rarity:* {rarity_emoji} {rarity_name} ({rarity_prob}%)\n"
        f"📊 *Drop Rate:* {rarity_prob}%\n"
        f"🎯 *Times Caught:* {total_caught:,}\n"
        f"👥 *Unique Owners:* {unique_owners:,}\n"
        f"📦 *In Circulation:* {total_in_circulation:,}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 *Top Owners:*\n{owners_text}"
    )

    # Build keyboard
    keyboard = build_cardinfo_keyboard(card_id, viewer_user_id, viewer_owns)

    # Send message with photo if available
    if photo_file_id:
        if from_callback and update.callback_query:
            # Edit existing message (if possible)
            try:
                await update.callback_query.edit_message_caption(
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=keyboard
                )
                await update.callback_query.answer()
            except Exception:
                # If can't edit (different media), send new message
                await update.callback_query.message.reply_photo(
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
        # No photo - send text only
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


def build_cardinfo_keyboard(
    card_id: int,
    viewer_user_id: int,
    viewer_owns: bool
) -> InlineKeyboardMarkup:
    """
    Build action keyboard for card info view.
    
    Args:
        card_id: Card ID
        viewer_user_id: User viewing the card
        viewer_owns: Whether the viewer owns this card
        
    Returns:
        InlineKeyboardMarkup with action buttons
    """
    buttons = []

    # Row 1: Ownership status
    if viewer_owns:
        buttons.append([
            InlineKeyboardButton("✅ You own this card", callback_data="noop")
        ])
    else:
        buttons.append([
            InlineKeyboardButton("❌ You don't own this card", callback_data="noop")
        ])

    # Row 2: Actions
    action_buttons = []

    # Offer trade button
    action_buttons.append(
        InlineKeyboardButton("🔁 Offer Trade", callback_data=f"trade_start:{card_id}:{viewer_user_id}")
    )

    # View in bot button
    action_buttons.append(
        InlineKeyboardButton("🔍 Search Similar", callback_data=f"search_anime:{card_id}")
    )

    buttons.append(action_buttons)

    # Row 3: Close button
    buttons.append([
        InlineKeyboardButton("❌ Close", callback_data="close")
    ])

    return InlineKeyboardMarkup(buttons)


# ============================================================
# 🔘 Card Info Callback Handler
# ============================================================

async def cardinfo_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle card info callbacks.
    
    Patterns:
    - ci:{card_id} - View card info
    - close - Close the message
    """
    query = update.callback_query

    if not query or not query.data:
        return

    data = query.data

    # Handle close
    if data == "close":
        await query.message.delete()
        await query.answer("Closed")
        return

    # Handle noop
    if data == "noop":
        await query.answer()
        return

    # Handle card info view (ci:{card_id})
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

    # Handle search similar (placeholder)
    if data.startswith("search_anime:"):
        await query.answer(
            "💡 Use inline mode: @" + context.bot.username + " <anime name>",
            show_alert=True
        )
        return


# ============================================================
# 📦 Handler Registration
# ============================================================

def register_cardinfo_handlers(application: Application) -> None:
    """
    Register card info handlers.
    
    Args:
        application: Telegram bot application
    """
    # Command handler
    application.add_handler(CommandHandler("cardinfo", cardinfo_command))

    # Callback query handlers
    application.add_handler(
        CallbackQueryHandler(cardinfo_callback_handler, pattern=r"^ci:")
    )
    application.add_handler(
        CallbackQueryHandler(cardinfo_callback_handler, pattern=r"^close$")
    )
    application.add_handler(
        CallbackQueryHandler(cardinfo_callback_handler, pattern=r"^search_anime:")
    )

    app_logger.info("✅ Card info handlers registered")