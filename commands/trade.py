# ============================================================
# 📁 File: commands/trade.py
# 📍 Location: telegram_card_bot/commands/trade.py
# 📝 Description: Modern trading system with clean UI
# ============================================================

from typing import Optional, List
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
    ensure_user,
    create_trade,
    get_trade,
    list_pending_trades_for_user,
    update_trade_status,
    check_user_owns_card,
    get_card_by_id,
    count_pending_trades,
    transfer_card_between_users,
    get_user_card_quantity,
)
from utils.logger import app_logger, error_logger, log_command
from utils.rarity import rarity_to_text
from utils.constants import (
    RARITY_EMOJIS,
    ButtonLabels,
    Pagination,
    format_number,
)
from utils.ui import format_error


# ============================================================
# 📊 Constants
# ============================================================

MAX_PENDING_TRADES = 10
TRADES_PER_PAGE = Pagination.TRADES_PER_PAGE


# ============================================================
# 🔁 Trades List Command
# ============================================================

async def trades_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /trades command - shows pending trades."""
    
    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    log_command(user.id, "trades", update.effective_chat.id)

    await ensure_user(
        pool=None,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

    if not db.is_connected:
        await update.message.reply_text(format_error("database"))
        return

    await show_trades_list(update, context, user.id)


async def show_trades_list(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    from_callback: bool = False
) -> None:
    """Display trades list with modern UI."""
    
    # Get pending trades
    received = await list_pending_trades_for_user(None, user_id, as_recipient=True, limit=10)
    sent = await list_pending_trades_for_user(None, user_id, as_recipient=False, limit=10)

    total_pending = len(received) + len(sent)

    # Build message
    lines = ["🔁 *Your Trades*\n"]

    # Received trades
    if received:
        lines.append(f"📥 *Incoming* ({len(received)})")
        for trade in received[:5]:
            trade_id = trade.get("id")
            from_name = trade.get("from_user_name", "Unknown")
            char = trade.get("offered_character", "Unknown")
            rarity = trade.get("offered_rarity", 1)
            emoji = RARITY_EMOJIS.get(rarity, "☘️")
            
            lines.append(f"  {emoji} {char}")
            lines.append(f"  └ from {from_name} • `#{trade_id}`")
        
        if len(received) > 5:
            lines.append(f"  _...and {len(received) - 5} more_")
    else:
        lines.append("📥 *Incoming:* None")

    lines.append("")

    # Sent trades
    if sent:
        lines.append(f"📤 *Outgoing* ({len(sent)})")
        for trade in sent[:5]:
            trade_id = trade.get("id")
            to_name = trade.get("to_user_name", "Unknown")
            char = trade.get("offered_character", "Unknown")
            rarity = trade.get("offered_rarity", 1)
            emoji = RARITY_EMOJIS.get(rarity, "☘️")
            
            lines.append(f"  {emoji} {char}")
            lines.append(f"  └ to {to_name} • `#{trade_id}`")
        
        if len(sent) > 5:
            lines.append(f"  _...and {len(sent) - 5} more_")
    else:
        lines.append("📤 *Outgoing:* None")

    # Footer
    lines.append(f"\n📊 {total_pending}/{MAX_PENDING_TRADES} active trades")

    text = "\n".join(lines)

    # Build keyboard
    buttons = []

    # Quick view buttons for received trades
    if received:
        view_row = []
        for trade in received[:4]:
            trade_id = trade.get("id")
            rarity = trade.get("offered_rarity", 1)
            emoji = RARITY_EMOJIS.get(rarity, "☘️")
            view_row.append(
                InlineKeyboardButton(
                    f"{emoji} #{trade_id}",
                    callback_data=f"tv:{trade_id}"
                )
            )
        if view_row:
            buttons.append(view_row)

    # Action buttons
    buttons.append([
        InlineKeyboardButton(
            "📦 My Collection",
            switch_inline_query_current_chat=f"collection.{user_id}"
        )
    ])

    buttons.append([
        InlineKeyboardButton(ButtonLabels.REFRESH, callback_data="trades_refresh"),
        InlineKeyboardButton(ButtonLabels.CLOSE, callback_data="trades_close")
    ])

    keyboard = InlineKeyboardMarkup(buttons)

    # Send or edit
    if from_callback and update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text=text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
        except Exception:
            pass
        await update.callback_query.answer()
    else:
        await update.message.reply_text(
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )


# ============================================================
# 🔍 View Trade Details
# ============================================================

async def show_trade_details(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    trade_id: int,
    viewer_user_id: int,
    from_callback: bool = False
) -> None:
    """Display detailed trade information."""
    
    trade = await get_trade(None, trade_id)

    if not trade:
        if from_callback and update.callback_query:
            await update.callback_query.answer("Trade not found!", show_alert=True)
        return

    # Extract info
    from_user = trade.get("from_user")
    to_user = trade.get("to_user")
    from_name = trade.get("from_user_name", "Unknown")
    to_name = trade.get("to_user_name", "Unknown")
    status = trade.get("status", "unknown")

    # Offered card
    offered_id = trade.get("offered_card_id")
    offered_char = trade.get("offered_character", "Unknown")
    offered_anime = trade.get("offered_anime", "Unknown")
    offered_rarity = trade.get("offered_rarity", 1)
    offered_photo = trade.get("offered_photo")
    
    offered_name, offered_prob, offered_emoji = rarity_to_text(offered_rarity)

    # Requested card (if any)
    requested_id = trade.get("requested_card_id")
    requested_char = trade.get("requested_character")
    requested_rarity = trade.get("requested_rarity")

    # Status emoji
    status_emojis = {
        "pending": "⏳",
        "accepted": "✅",
        "rejected": "❌",
        "cancelled": "🚫",
        "completed": "✅",
        "failed": "💥"
    }
    status_emoji = status_emojis.get(status, "❓")

    # Build caption
    lines = [
        f"🔁 *Trade #{trade_id}*",
        f"{status_emoji} Status: {status.upper()}",
        "",
        f"👤 *From:* {from_name}",
        f"👤 *To:* {to_name}",
        "",
        f"📤 *Offering:*",
        f"{offered_emoji} *{offered_char}*",
        f"└ {offered_anime} • {offered_name}",
    ]

    if requested_id and requested_char:
        req_name, _, req_emoji = rarity_to_text(requested_rarity)
        lines.extend([
            "",
            f"📥 *Requesting:*",
            f"{req_emoji} *{requested_char}*",
        ])
    else:
        lines.extend([
            "",
            f"📥 *Requesting:* 🎁 Gift (no return)",
        ])

    caption = "\n".join(lines)

    # Build keyboard based on viewer and status
    keyboard = build_trade_detail_keyboard(
        trade_id=trade_id,
        viewer_user_id=viewer_user_id,
        from_user=from_user,
        to_user=to_user,
        status=status
    )

    # Send with photo if available
    if offered_photo and not from_callback:
        await update.message.reply_photo(
            photo=offered_photo,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
    else:
        if from_callback and update.callback_query:
            try:
                await update.callback_query.edit_message_text(
                    text=caption,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=keyboard
                )
            except Exception:
                # If there was a photo, delete and send new
                try:
                    await update.callback_query.message.delete()
                    await context.bot.send_message(
                        chat_id=update.callback_query.message.chat_id,
                        text=caption,
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=keyboard
                    )
                except Exception:
                    pass
            await update.callback_query.answer()
        else:
            await update.message.reply_text(
                text=caption,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )


def build_trade_detail_keyboard(
    trade_id: int,
    viewer_user_id: int,
    from_user: int,
    to_user: int,
    status: str
) -> InlineKeyboardMarkup:
    """Build trade detail action keyboard."""
    
    buttons = []

    if status == "pending":
        # Recipient actions
        if viewer_user_id == to_user:
            buttons.append([
                InlineKeyboardButton(
                    "✅ Accept",
                    callback_data=f"ta:{trade_id}"
                ),
                InlineKeyboardButton(
                    "❌ Reject",
                    callback_data=f"tr:{trade_id}"
                )
            ])
        
        # Sender actions
        elif viewer_user_id == from_user:
            buttons.append([
                InlineKeyboardButton(
                    "🚫 Cancel Trade",
                    callback_data=f"tc:{trade_id}"
                )
            ])

    # Back to list
    buttons.append([
        InlineKeyboardButton(
            "📋 All Trades",
            callback_data="trades_refresh"
        ),
        InlineKeyboardButton(
            ButtonLabels.CLOSE,
            callback_data="trades_close"
        )
    ])

    return InlineKeyboardMarkup(buttons)


# ============================================================
# 🎁 Offer Trade Command
# ============================================================

async def offertrade_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /offertrade <card_id> <user_id> command."""
    
    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    log_command(user.id, "offertrade", update.effective_chat.id)

    if not db.is_connected:
        await update.message.reply_text(format_error("database"))
        return

    # Parse arguments
    if len(context.args) < 2:
        await update.message.reply_text(
            "🔁 *Offer Trade*\n\n"
            "Usage: `/offertrade <card_id> <user_id>`\n\n"
            "Examples:\n"
            "• `/offertrade 42 123456789`\n"
            "• `/offertrade 100 987654321`\n\n"
            "💡 Get user ID by replying to their message or from their profile.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        card_id = int(context.args[0].replace("#", ""))
        to_user_id = int(context.args[1])
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid card ID or user ID.\n"
            "Both must be numbers.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Can't trade with yourself
    if to_user_id == user.id:
        await update.message.reply_text("❌ You can't trade with yourself!")
        return

    # Check ownership
    owns = await check_user_owns_card(None, user.id, card_id)
    if not owns:
        await update.message.reply_text(
            "❌ You don't own this card!\n"
            "Check your collection with /harem",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Check quantity
    qty = await get_user_card_quantity(None, user.id, card_id)
    if qty < 1:
        await update.message.reply_text("❌ You don't have this card to trade!")
        return

    # Check pending limit
    pending = await count_pending_trades(None, user.id)
    if pending >= MAX_PENDING_TRADES:
        await update.message.reply_text(
            f"⚠️ You have {MAX_PENDING_TRADES} pending trades.\n"
            f"Complete or cancel some first.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Get card info
    card = await get_card_by_id(None, card_id)
    if not card:
        await update.message.reply_text("❌ Card not found!")
        return

    char_name = card.get("character_name", "Unknown")
    rarity = card.get("rarity", 1)
    _, _, emoji = rarity_to_text(rarity)

    # Create trade
    trade_id = await create_trade(
        pool=None,
        from_user=user.id,
        to_user=to_user_id,
        offered_card_id=card_id,
        requested_card_id=None
    )

    if trade_id:
        await update.message.reply_text(
            f"✅ *Trade Offered!*\n\n"
            f"{emoji} *{char_name}*\n"
            f"🆔 Trade ID: `#{trade_id}`\n\n"
            f"Waiting for user `{to_user_id}` to respond.\n"
            f"Use `/canceltrade {trade_id}` to cancel.",
            parse_mode=ParseMode.MARKDOWN
        )

        # Notify recipient
        try:
            await context.bot.send_message(
                chat_id=to_user_id,
                text=(
                    f"🔔 *New Trade Request!*\n\n"
                    f"From: {user.first_name}\n"
                    f"Offering: {emoji} {char_name}\n\n"
                    f"Use /trades to view and respond."
                ),
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            app_logger.warning(f"Failed to notify trade recipient: {e}")
    else:
        await update.message.reply_text("❌ Failed to create trade. Try again.")


# ============================================================
# 🚫 Cancel Trade Command
# ============================================================

async def canceltrade_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /canceltrade <trade_id> command."""
    
    if not update.message or not update.effective_user:
        return

    user = update.effective_user

    if not context.args:
        await update.message.reply_text(
            "Usage: `/canceltrade <trade_id>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        trade_id = int(context.args[0].replace("#", ""))
    except ValueError:
        await update.message.reply_text("❌ Invalid trade ID.")
        return

    # Get trade
    trade = await get_trade(None, trade_id)
    
    if not trade:
        await update.message.reply_text("❌ Trade not found.")
        return

    # Check ownership
    if trade["from_user"] != user.id:
        await update.message.reply_text("❌ Only the sender can cancel this trade.")
        return

    # Check status
    if trade["status"] != "pending":
        await update.message.reply_text(f"❌ Trade is already {trade['status']}.")
        return

    # Cancel
    success = await update_trade_status(None, trade_id, "cancelled")
    
    if success:
        await update.message.reply_text(f"🚫 Trade `#{trade_id}` cancelled.")
    else:
        await update.message.reply_text("❌ Failed to cancel trade.")


# ============================================================
# 🔘 Callback Handlers
# ============================================================

async def trades_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle trades list callbacks."""
    
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    user_id = query.from_user.id

    # Close
    if data == "trades_close":
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.answer()
        return

    # Refresh
    if data == "trades_refresh":
        await show_trades_list(update, context, user_id, from_callback=True)
        return


async def trade_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle trade view callback (tv:{id})."""
    
    query = update.callback_query
    if not query or not query.data:
        return

    try:
        trade_id = int(query.data.split(":")[1])
    except (ValueError, IndexError):
        await query.answer("Error", show_alert=True)
        return

    await show_trade_details(
        update=update,
        context=context,
        trade_id=trade_id,
        viewer_user_id=query.from_user.id,
        from_callback=True
    )


async def trade_accept_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle trade accept callback (ta:{id})."""
    
    query = update.callback_query
    if not query or not query.data:
        return

    try:
        trade_id = int(query.data.split(":")[1])
    except (ValueError, IndexError):
        await query.answer("Error", show_alert=True)
        return

    user_id = query.from_user.id

    # Get trade
    trade = await get_trade(None, trade_id)
    
    if not trade:
        await query.answer("Trade not found!", show_alert=True)
        return

    # Verify recipient
    if trade["to_user"] != user_id:
        await query.answer("Only the recipient can accept!", show_alert=True)
        return

    # Verify status
    if trade["status"] != "pending":
        await query.answer(f"Trade is {trade['status']}", show_alert=True)
        return

    # Execute transfer
    from_user = trade["from_user"]
    to_user = trade["to_user"]
    offered_card_id = trade["offered_card_id"]
    requested_card_id = trade.get("requested_card_id")

    # Transfer offered card
    success, msg = await transfer_card_between_users(
        None, from_user, to_user, offered_card_id, 1
    )

    if not success:
        await update_trade_status(None, trade_id, "failed")
        await query.answer(f"❌ Failed: {msg}", show_alert=True)
        return

    # Transfer requested card if exists
    if requested_card_id:
        success2, msg2 = await transfer_card_between_users(
            None, to_user, from_user, requested_card_id, 1
        )
        if not success2:
            await update_trade_status(None, trade_id, "failed")
            await query.answer(f"❌ Partial failure: {msg2}", show_alert=True)
            return

    # Complete trade
    await update_trade_status(None, trade_id, "completed")

    offered_char = trade.get("offered_character", "Card")
    _, _, emoji = rarity_to_text(trade.get("offered_rarity", 1))

    await query.answer("✅ Trade completed!", show_alert=True)

    # Update message
    await query.edit_message_text(
        f"✅ *Trade Completed!*\n\n"
        f"You received: {emoji} *{offered_char}*\n\n"
        f"Check your /harem!",
        parse_mode=ParseMode.MARKDOWN
    )

    # Notify sender
    try:
        await context.bot.send_message(
            chat_id=from_user,
            text=(
                f"✅ *Trade Accepted!*\n\n"
                f"{query.from_user.first_name} accepted your trade.\n"
                f"They received: {emoji} {offered_char}"
            ),
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception:
        pass


async def trade_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle trade reject callback (tr:{id})."""
    
    query = update.callback_query
    if not query or not query.data:
        return

    try:
        trade_id = int(query.data.split(":")[1])
    except (ValueError, IndexError):
        await query.answer("Error", show_alert=True)
        return

    user_id = query.from_user.id

    # Get trade
    trade = await get_trade(None, trade_id)
    
    if not trade:
        await query.answer("Trade not found!", show_alert=True)
        return

    if trade["to_user"] != user_id:
        await query.answer("Only the recipient can reject!", show_alert=True)
        return

    # Reject
    await update_trade_status(None, trade_id, "rejected")
    await query.answer("Trade rejected")

    await query.edit_message_text(
        f"❌ *Trade Rejected*\n\n"
        f"Trade `#{trade_id}` has been declined.",
        parse_mode=ParseMode.MARKDOWN
    )

    # Notify sender
    try:
        await context.bot.send_message(
            chat_id=trade["from_user"],
            text=(
                f"❌ *Trade Rejected*\n\n"
                f"{query.from_user.first_name} declined your trade offer."
            ),
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception:
        pass


async def trade_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle trade cancel callback (tc:{id})."""
    
    query = update.callback_query
    if not query or not query.data:
        return

    try:
        trade_id = int(query.data.split(":")[1])
    except (ValueError, IndexError):
        await query.answer("Error", show_alert=True)
        return

    user_id = query.from_user.id

    # Get trade
    trade = await get_trade(None, trade_id)
    
    if not trade:
        await query.answer("Trade not found!", show_alert=True)
        return

    if trade["from_user"] != user_id:
        await query.answer("Only the sender can cancel!", show_alert=True)
        return

    # Cancel
    await update_trade_status(None, trade_id, "cancelled")
    await query.answer("Trade cancelled")

    await query.edit_message_text(
        f"🚫 *Trade Cancelled*\n\n"
        f"Trade `#{trade_id}` has been cancelled.",
        parse_mode=ParseMode.MARKDOWN
    )


# ============================================================
# 📦 Handler Registration
# ============================================================

def register_trade_handlers(application: Application) -> None:
    """Register trade handlers."""
    
    # Commands
    application.add_handler(CommandHandler("trades", trades_command))
    application.add_handler(CommandHandler("offertrade", offertrade_command))
    application.add_handler(CommandHandler("trade", offertrade_command))  # Alias
    application.add_handler(CommandHandler("canceltrade", canceltrade_command))

    # Callbacks
    application.add_handler(
        CallbackQueryHandler(trades_callback_handler, pattern=r"^trades_")
    )
    application.add_handler(
        CallbackQueryHandler(trade_view_callback, pattern=r"^tv:")
    )
    application.add_handler(
        CallbackQueryHandler(trade_accept_callback, pattern=r"^ta:")
    )
    application.add_handler(
        CallbackQueryHandler(trade_reject_callback, pattern=r"^tr:")
    )
    application.add_handler(
        CallbackQueryHandler(trade_cancel_callback, pattern=r"^tc:")
    )

    app_logger.info("✅ Trade handlers registered")