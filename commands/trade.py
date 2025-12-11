# ============================================================
# 📁 File: commands/trade.py
# 📍 Location: telegram_card_bot/commands/trade.py
# 📝 Description: Trading system with request/accept/reject flows
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

from db import (
    db,
    ensure_user,
    create_trade,
    get_trade,
    list_pending_trades_for_user,
    update_trade_status,
    check_user_owns_card,
    get_card_by_id,
    count_pending_trades,
    transfer_card_between_users,
)
from utils.logger import app_logger, error_logger, log_command
from utils.rarity import rarity_to_text


# ============================================================
# 📊 Constants
# ============================================================

MAX_PENDING_TRADES_PER_USER = 5  # Limit active trades


# ============================================================
# 🔁 Trades List Command Handler
# ============================================================

async def trades_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /trades command.
    Shows pending trade requests (received and sent).
    """
    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    log_command(user.id, "trades", update.effective_chat.id)

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

    # Get pending trades received
    received_trades = await list_pending_trades_for_user(None, user.id, as_recipient=True, limit=10)

    # Get pending trades sent
    sent_trades = await list_pending_trades_for_user(None, user.id, as_recipient=False, limit=10)

    # Build message
    text_parts = ["🔁 *Your Trade Requests*\n"]

    # Received trades
    if received_trades:
        text_parts.append("\n📥 *Received* (tap to view):\n")
        for trade in received_trades[:5]:
            trade_id = trade.get("id")
            from_user_name = trade.get("from_user_name", "Unknown")
            offered_char = trade.get("offered_character", "Unknown")
            offered_rarity = trade.get("offered_rarity", 1)
            
            rarity_emoji = rarity_to_text(offered_rarity)[2]
            
            text_parts.append(
                f"  • From *{from_user_name}*: {rarity_emoji} {offered_char}\n"
                f"    `/viewtrade {trade_id}`"
            )
    else:
        text_parts.append("\n📥 *Received:* None\n")

    # Sent trades
    if sent_trades:
        text_parts.append("\n📤 *Sent* (waiting for reply):\n")
        for trade in sent_trades[:5]:
            trade_id = trade.get("id")
            to_user_name = trade.get("to_user_name", "Unknown")
            offered_char = trade.get("offered_character", "Unknown")
            offered_rarity = trade.get("offered_rarity", 1)
            
            rarity_emoji = rarity_to_text(offered_rarity)[2]
            
            text_parts.append(
                f"  • To *{to_user_name}*: {rarity_emoji} {offered_char}\n"
                f"    `/canceltrade {trade_id}`"
            )
    else:
        text_parts.append("\n📤 *Sent:* None\n")

    text_parts.append(
        "\n━━━━━━━━━━━━━━━━━━━━\n"
        "💡 Use `/viewtrade <id>` to view details\n"
        "💡 Offer trades from card info pages"
    )

    await update.message.reply_text(
        "".join(text_parts),
        parse_mode=ParseMode.MARKDOWN
    )


# ============================================================
# 🔍 View Trade Command Handler
# ============================================================

async def viewtrade_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /viewtrade <trade_id> command.
    Shows detailed trade information with accept/reject buttons.
    """
    if not update.message or not update.effective_user:
        return

    user = update.effective_user

    # Check DB connection
    if not db.is_connected:
        await update.message.reply_text(
            "⚠️ Database is currently offline.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Check if trade ID provided
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "📝 *Usage:* `/viewtrade <trade_id>`\n\n"
            "Example: `/viewtrade 42`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    trade_id = int(context.args[0])

    # Show trade details
    await show_trade_details(update, context, trade_id, user.id)


async def show_trade_details(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    trade_id: int,
    viewer_user_id: int,
    from_callback: bool = False
) -> None:
    """
    Display detailed trade information.
    
    Args:
        update: Telegram update
        context: Bot context
        trade_id: Trade ID to display
        viewer_user_id: User viewing the trade
        from_callback: Whether this is from a callback
    """
    # Get trade details
    trade = await get_trade(None, trade_id)

    if not trade:
        error_msg = f"❌ Trade `#{trade_id}` not found."
        
        if from_callback and update.callback_query:
            await update.callback_query.answer("Trade not found!", show_alert=True)
        else:
            await update.message.reply_text(error_msg, parse_mode=ParseMode.MARKDOWN)
        return

    # Extract trade info
    from_user = trade.get("from_user")
    to_user = trade.get("to_user")
    from_user_name = trade.get("from_user_name", "Unknown")
    to_user_name = trade.get("to_user_name", "Unknown")
    status = trade.get("status", "unknown")

    offered_card_id = trade.get("offered_card_id")
    offered_char = trade.get("offered_character", "Unknown")
    offered_anime = trade.get("offered_anime", "Unknown")
    offered_rarity = trade.get("offered_rarity", 1)
    offered_photo = trade.get("offered_photo")

    requested_card_id = trade.get("requested_card_id")
    requested_char = trade.get("requested_character")
    requested_anime = trade.get("requested_anime")
    requested_rarity = trade.get("requested_rarity")

    # Get rarity details
    offered_rarity_name, offered_rarity_prob, offered_rarity_emoji = rarity_to_text(offered_rarity)

    # Build message
    text_parts = [
        f"🔁 *Trade Request #{trade_id}*\n\n",
        f"━━━━━━━━━━━━━━━━━━━━\n",
        f"👤 *From:* {from_user_name}\n",
        f"👤 *To:* {to_user_name}\n",
        f"📊 *Status:* {status.upper()}\n\n",
        f"📤 *Offered:*\n",
        f"  {offered_rarity_emoji} *{offered_char}*\n",
        f"  🎬 _{offered_anime}_\n",
        f"  🆔 `#{offered_card_id}` • {offered_rarity_name} ({offered_rarity_prob}%)\n",
    ]

    if requested_card_id:
        requested_rarity_name, requested_rarity_prob, requested_rarity_emoji = rarity_to_text(requested_rarity)
        text_parts.append(
            f"\n📥 *Requested:*\n"
            f"  {requested_rarity_emoji} *{requested_char}*\n"
            f"  🎬 _{requested_anime}_\n"
            f"  🆔 `#{requested_card_id}` • {requested_rarity_name} ({requested_rarity_prob}%)\n"
        )
    else:
        text_parts.append("\n📥 *Requested:* Any card (gift)\n")

    text_parts.append(f"━━━━━━━━━━━━━━━━━━━━\n")

    caption = "".join(text_parts)

    # Build keyboard based on viewer role and status
    keyboard = build_trade_keyboard(trade_id, viewer_user_id, from_user, to_user, status)

    # Send with photo if available
    if offered_photo and not from_callback:
        await update.message.reply_photo(
            photo=offered_photo,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
    else:
        # Text only or callback edit
        if from_callback and update.callback_query:
            try:
                await update.callback_query.edit_message_text(
                    text=caption,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=keyboard
                )
                await update.callback_query.answer()
            except Exception:
                await update.callback_query.message.reply_text(
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


def build_trade_keyboard(
    trade_id: int,
    viewer_user_id: int,
    from_user: int,
    to_user: int,
    status: str
) -> InlineKeyboardMarkup:
    """
    Build action keyboard for trade view.
    
    Args:
        trade_id: Trade ID
        viewer_user_id: User viewing
        from_user: Trade sender
        to_user: Trade recipient
        status: Trade status
        
    Returns:
        InlineKeyboardMarkup with appropriate action buttons
    """
    buttons = []

    if status == "pending":
        # Recipient can accept/reject
        if viewer_user_id == to_user:
            buttons.append([
                InlineKeyboardButton("✅ Accept", callback_data=f"trade_accept:{trade_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"trade_reject:{trade_id}"),
            ])
        
        # Sender can cancel
        elif viewer_user_id == from_user:
            buttons.append([
                InlineKeyboardButton("🚫 Cancel Trade", callback_data=f"trade_cancel:{trade_id}"),
            ])
    
    # Close button for everyone
    buttons.append([
        InlineKeyboardButton("❌ Close", callback_data="close")
    ])

    return InlineKeyboardMarkup(buttons)


# ============================================================
# 🔁 Trade Start Callback Handler
# ============================================================

async def trade_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle trade_start:{card_id}:{viewer_user_id} callback.
    Initiates a trade offer for a card.
    """
    query = update.callback_query

    if not query or not query.data:
        return

    try:
        parts = query.data.split(":")
        card_id = int(parts[1])
        viewer_user_id = int(parts[2])
        
    except (ValueError, IndexError):
        await query.answer("Invalid data", show_alert=True)
        return

    # For now, we'll create a simple gift trade (no requested card)
    # In a full implementation, you'd ask the user to select a card to request

    # Check if user owns the card
    owns_card = await check_user_owns_card(None, query.from_user.id, card_id)

    if not owns_card:
        await query.answer(
            "❌ You don't own this card!\nYou can only trade cards you own.",
            show_alert=True
        )
        return

    # Check pending trade limit
    pending_count = await count_pending_trades(None, query.from_user.id)

    if pending_count >= MAX_PENDING_TRADES_PER_USER:
        await query.answer(
            f"⚠️ You have reached the limit of {MAX_PENDING_TRADES_PER_USER} pending trades.\n"
            "Please complete or cancel some trades first.",
            show_alert=True
        )
        return

    # For this simple implementation, we'll assume the viewer_user_id is the recipient
    # In a full implementation, you'd let the user select the recipient

    # Get card info
    card = await get_card_by_id(None, card_id)
    if not card:
        await query.answer("Card not found!", show_alert=True)
        return

    character = card.get("character_name", "Unknown")

    # Ask for confirmation (simplified - in real implementation, use ConversationHandler)
    await query.answer(
        f"🔁 To offer {character}, use:\n/offertrade {card_id} @username",
        show_alert=True
    )


# ============================================================
# 🎁 Offer Trade Command (Simplified)
# ============================================================

async def offertrade_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /offertrade <card_id> <@username|user_id> command.
    Creates a trade offer.
    """
    if not update.message or not update.effective_user:
        return

    user = update.effective_user

    if not db.is_connected:
        await update.message.reply_text("⚠️ Database offline.")
        return

    # Parse arguments
    if len(context.args) < 2:
        await update.message.reply_text(
            "📝 *Usage:* `/offertrade <card_id> <user_id>`\n\n"
            "Example: `/offertrade 42 123456789`\n\n"
            "💡 Get user IDs from their profile or replies.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        card_id = int(context.args[0])
        to_user_id = int(context.args[1].replace("@", ""))
    except ValueError:
        await update.message.reply_text("❌ Invalid card ID or user ID.")
        return

    # Validate ownership
    owns_card = await check_user_owns_card(None, user.id, card_id)
    if not owns_card:
        await update.message.reply_text("❌ You don't own this card!")
        return

    # Check limit
    pending_count = await count_pending_trades(None, user.id)
    if pending_count >= MAX_PENDING_TRADES_PER_USER:
        await update.message.reply_text(
            f"⚠️ You have {MAX_PENDING_TRADES_PER_USER} pending trades already.\n"
            "Complete or cancel some first."
        )
        return

    # Create trade (gift - no requested card)
    trade_id = await create_trade(
        pool=None,
        from_user=user.id,
        to_user=to_user_id,
        offered_card_id=card_id,
        requested_card_id=None
    )

    if trade_id:
        card = await get_card_by_id(None, card_id)
        character = card.get("character_name", "Card") if card else "Card"
        
        await update.message.reply_text(
            f"✅ *Trade Offered!*\n\n"
            f"🎁 Offering *{character}* to user `{to_user_id}`\n"
            f"🆔 Trade ID: `{trade_id}`\n\n"
            f"They will be notified. Use `/canceltrade {trade_id}` to cancel.",
            parse_mode=ParseMode.MARKDOWN
        )

        # Try to notify recipient
        try:
            await context.bot.send_message(
                chat_id=to_user_id,
                text=(
                    f"🔁 *New Trade Request!*\n\n"
                    f"From: {user.first_name}\n"
                    f"Offering: {character}\n\n"
                    f"Use `/viewtrade {trade_id}` to view and accept/reject."
                ),
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            app_logger.warning(f"Failed to notify trade recipient: {e}")
    else:
        await update.message.reply_text("❌ Failed to create trade. Please try again.")


# ============================================================
# ✅ Trade Accept Callback Handler
# ============================================================

async def trade_accept_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle trade_accept:{trade_id} callback.
    Accepts a trade and executes the transfer.
    """
    query = update.callback_query

    if not query or not query.data:
        return

    try:
        trade_id = int(query.data.split(":")[1])
    except (ValueError, IndexError):
        await query.answer("Invalid trade ID", show_alert=True)
        return

    user_id = query.from_user.id

    # Get trade details
    trade = await get_trade(None, trade_id)

    if not trade:
        await query.answer("Trade not found!", show_alert=True)
        return

    # Validate user is recipient
    if trade["to_user"] != user_id:
        await query.answer("Only the recipient can accept this trade!", show_alert=True)
        return

    # Validate status
    if trade["status"] != "pending":
        await query.answer(f"Trade is {trade['status']}, cannot accept.", show_alert=True)
        return

    # Execute the trade
    from_user = trade["from_user"]
    to_user = trade["to_user"]
    offered_card_id = trade["offered_card_id"]
    requested_card_id = trade.get("requested_card_id")

    # Transfer offered card
    success1, msg1 = await transfer_card_between_users(None, from_user, to_user, offered_card_id, 1)

    if not success1:
        await update_trade_status(None, trade_id, "failed")
        await query.answer(f"❌ Trade failed: {msg1}", show_alert=True)
        return

    # If requested card exists, transfer it back
    if requested_card_id:
        success2, msg2 = await transfer_card_between_users(None, to_user, from_user, requested_card_id, 1)
        
        if not success2:
            # Rollback? (Complex - needs transaction handling)
            await update_trade_status(None, trade_id, "failed")
            await query.answer(f"❌ Trade partially failed: {msg2}", show_alert=True)
            return

    # Mark as completed
    await update_trade_status(None, trade_id, "completed")

    # Notify both users
    offered_char = trade.get("offered_character", "Card")
    
    await query.answer("✅ Trade completed!", show_alert=True)
    await query.message.reply_text(
        f"🎉 *Trade Completed!*\n\n"
        f"You received: {offered_char}\n\n"
        f"Check your collection!",
        parse_mode=ParseMode.MARKDOWN
    )

    # Notify sender
    try:
        await context.bot.send_message(
            chat_id=from_user,
            text=(
                f"✅ *Trade Accepted!*\n\n"
                f"Your trade for {offered_char} was accepted by {query.from_user.first_name}!"
            ),
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception:
        pass


# ============================================================
# ❌ Trade Reject Callback Handler
# ============================================================

async def trade_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle trade_reject:{trade_id} callback.
    Rejects a trade request.
    """
    query = update.callback_query

    if not query or not query.data:
        return

    try:
        trade_id = int(query.data.split(":")[1])
    except (ValueError, IndexError):
        await query.answer("Invalid trade ID", show_alert=True)
        return

    user_id = query.from_user.id

    # Get trade details
    trade = await get_trade(None, trade_id)

    if not trade:
        await query.answer("Trade not found!", show_alert=True)
        return

    # Validate user is recipient
    if trade["to_user"] != user_id:
        await query.answer("Only the recipient can reject this trade!", show_alert=True)
        return

    # Update status
    success = await update_trade_status(None, trade_id, "rejected")

    if success:
        await query.answer("❌ Trade rejected", show_alert=True)
        
        # Notify sender
        try:
            offered_char = trade.get("offered_character", "your card")
            await context.bot.send_message(
                chat_id=trade["from_user"],
                text=(
                    f"❌ *Trade Rejected*\n\n"
                    f"Your offer for {offered_char} was declined by {query.from_user.first_name}."
                ),
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            pass
    else:
        await query.answer("Failed to reject trade.", show_alert=True)


# ============================================================
# 🚫 Trade Cancel Callback Handler
# ============================================================

async def trade_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle trade_cancel:{trade_id} callback.
    Cancels a trade (by sender only).
    """
    query = update.callback_query

    if not query or not query.data:
        return

    try:
        trade_id = int(query.data.split(":")[1])
    except (ValueError, IndexError):
        await query.answer("Invalid trade ID", show_alert=True)
        return

    user_id = query.from_user.id

    # Get trade details
    trade = await get_trade(None, trade_id)

    if not trade:
        await query.answer("Trade not found!", show_alert=True)
        return

    # Validate user is sender
    if trade["from_user"] != user_id:
        await query.answer("Only the sender can cancel this trade!", show_alert=True)
        return

    # Update status
    success = await update_trade_status(None, trade_id, "cancelled")

    if success:
        await query.answer("🚫 Trade cancelled", show_alert=True)
    else:
        await query.answer("Failed to cancel trade.", show_alert=True)


# ============================================================
# 📦 Handler Registration
# ============================================================

def register_trade_handlers(application: Application) -> None:
    """
    Register trade-related handlers.
    
    Args:
        application: Telegram bot application
    """
    # Command handlers
    application.add_handler(CommandHandler("trades", trades_command))
    application.add_handler(CommandHandler("viewtrade", viewtrade_command))
    application.add_handler(CommandHandler("offertrade", offertrade_command))

    # Callback query handlers
    application.add_handler(
        CallbackQueryHandler(trade_start_callback, pattern=r"^trade_start:")
    )
    application.add_handler(
        CallbackQueryHandler(trade_accept_callback, pattern=r"^trade_accept:")
    )
    application.add_handler(
        CallbackQueryHandler(trade_reject_callback, pattern=r"^trade_reject:")
    )
    application.add_handler(
        CallbackQueryHandler(trade_cancel_callback, pattern=r"^trade_cancel:")
    )

    app_logger.info("✅ Trade handlers registered")