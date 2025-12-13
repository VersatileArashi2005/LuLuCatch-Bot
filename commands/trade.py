# ============================================================
# 📁 File: commands/trade.py
# 📍 Location: telegram_card_bot/commands/trade.py
# 📝 Description: Modern reply-based trading system with clean UI
# ============================================================

from typing import Optional, List
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
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
    get_user_by_id,
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

# Notification channel for /offer command
# Set this in your .env file as TRADE_CHANNEL_ID
TRADE_CHANNEL_ID: Optional[int] = None
try:
    import os
    _channel = os.getenv("TRADE_CHANNEL_ID", "")
    if _channel.lstrip("-").isdigit():
        TRADE_CHANNEL_ID = int(_channel)
except Exception:
    pass


# ============================================================
# 🔧 Helper Functions
# ============================================================

def get_target_user_from_reply(message: Message) -> Optional[tuple[int, str, Optional[str]]]:
    """
    Extract target user from replied message.
    
    Returns:
        Tuple of (user_id, first_name, username) or None
    """
    if not message.reply_to_message:
        return None
    
    target = message.reply_to_message.from_user
    if not target or target.is_bot:
        return None
    
    return (target.id, target.first_name or "User", target.username)


def format_card_display(card: dict, show_id: bool = True) -> str:
    """Format card info for display."""
    rarity = card.get("rarity", 1)
    emoji = RARITY_EMOJIS.get(rarity, "❓")
    name = card.get("character_name", "Unknown")
    anime = card.get("anime", "Unknown")
    
    if show_id:
        card_id = card.get("card_id", 0)
        return f"{emoji} *{name}*\n└ {anime} • `#{card_id}`"
    return f"{emoji} *{name}*\n└ {anime}"


# ============================================================
# 🎁 Gift Command (Reply-based)
# ============================================================

async def gift_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /gift <card_id> command.
    Must reply to target user's message.
    """
    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    log_command(user.id, "gift", update.effective_chat.id)

    if not db.is_connected:
        await update.message.reply_text(format_error("database"))
        return

    # Check for reply
    target_info = get_target_user_from_reply(update.message)
    if not target_info:
        await update.message.reply_text(
            "🎁 *Gift a Card*\n\n"
            "Reply to someone's message and type:\n"
            "`/gift <card_id>`\n\n"
            "Example: `/gift 42`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    target_id, target_name, target_username = target_info

    # Can't gift to yourself
    if target_id == user.id:
        await update.message.reply_text("❌ You can't gift cards to yourself!")
        return

    # Parse card_id
    if not context.args:
        await update.message.reply_text(
            "❌ Please specify a card ID.\n"
            "Usage: `/gift <card_id>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        card_id = int(context.args[0].replace("#", ""))
    except ValueError:
        await update.message.reply_text("❌ Invalid card ID. Must be a number.")
        return

    # Ensure both users exist
    await ensure_user(None, user.id, user.username, user.first_name, user.last_name)
    await ensure_user(None, target_id, target_username, target_name, None)

    # Check ownership
    owns = await check_user_owns_card(None, user.id, card_id)
    if not owns:
        await update.message.reply_text(
            "❌ You don't own this card!\n"
            "Check your collection with /harem",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Get card info
    card = await get_card_by_id(None, card_id)
    if not card:
        await update.message.reply_text("❌ Card not found!")
        return

    char_name = card.get("character_name", "Unknown")
    anime = card.get("anime", "Unknown")
    rarity = card.get("rarity", 1)
    emoji = RARITY_EMOJIS.get(rarity, "❓")
    rarity_name, _, _ = rarity_to_text(rarity)

    # Build confirmation keyboard
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Confirm Gift",
                callback_data=f"gift_confirm:{card_id}:{target_id}"
            ),
            InlineKeyboardButton(
                "❌ Cancel",
                callback_data="gift_cancel"
            )
        ]
    ])

    await update.message.reply_text(
        f"🎁 *Confirm Gift*\n\n"
        f"You are about to give:\n"
        f"{emoji} *{char_name}*\n"
        f"└ {anime} • {rarity_name}\n\n"
        f"To: *{target_name}*\n\n"
        f"This action cannot be undone!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


async def gift_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle gift confirmation callback."""
    query = update.callback_query
    if not query or not query.data:
        return

    user_id = query.from_user.id

    try:
        parts = query.data.split(":")
        card_id = int(parts[1])
        target_id = int(parts[2])
    except (ValueError, IndexError):
        await query.answer("Error processing gift", show_alert=True)
        return

    # Verify ownership again
    owns = await check_user_owns_card(None, user_id, card_id)
    if not owns:
        await query.answer("You no longer own this card!", show_alert=True)
        await query.edit_message_text("❌ Gift cancelled - card not found in your collection.")
        return

    # Execute transfer
    success, msg = await transfer_card_between_users(None, user_id, target_id, card_id, 1)

    if not success:
        await query.answer(f"Failed: {msg}", show_alert=True)
        await query.edit_message_text(f"❌ Gift failed: {msg}")
        return

    # Get card info for message
    card = await get_card_by_id(None, card_id)
    char_name = card.get("character_name", "Unknown") if card else "Unknown"
    rarity = card.get("rarity", 1) if card else 1
    emoji = RARITY_EMOJIS.get(rarity, "❓")

    # Get target name
    target_user = await get_user_by_id(None, target_id)
    target_name = target_user.get("first_name", "User") if target_user else "User"

    await query.answer("Gift sent!", show_alert=True)
    await query.edit_message_text(
        f"🎁 *Gift Sent!*\n\n"
        f"You gave {emoji} *{char_name}* to *{target_name}*!",
        parse_mode=ParseMode.MARKDOWN
    )

    # Notify recipient
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                f"🎁 *You received a gift!*\n\n"
                f"From: *{query.from_user.first_name}*\n"
                f"Card: {emoji} *{char_name}*\n\n"
                f"Check your /harem!"
            ),
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        app_logger.warning(f"Failed to notify gift recipient: {e}")


async def gift_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle gift cancellation."""
    query = update.callback_query
    if query:
        await query.answer("Gift cancelled")
        await query.edit_message_text("❌ Gift cancelled.")


# ============================================================
# 🔄 Trade Command (Reply-based)
# ============================================================

async def trade_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /trade <give_card_id> <want_card_id> command.
    Must reply to target user's message.
    """
    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    log_command(user.id, "trade", update.effective_chat.id)

    if not db.is_connected:
        await update.message.reply_text(format_error("database"))
        return

    # Check for reply
    target_info = get_target_user_from_reply(update.message)
    if not target_info:
        await update.message.reply_text(
            "🔄 *Trade Cards*\n\n"
            "Reply to someone's message and type:\n"
            "`/trade <your_card_id> <their_card_id>`\n\n"
            "Example: `/trade 42 100`\n"
            "(Give card #42, want card #100)",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    target_id, target_name, target_username = target_info

    # Can't trade with yourself
    if target_id == user.id:
        await update.message.reply_text("❌ You can't trade with yourself!")
        return

    # Parse arguments
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Please specify both card IDs.\n"
            "Usage: `/trade <your_card_id> <their_card_id>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        give_card_id = int(context.args[0].replace("#", ""))
        want_card_id = int(context.args[1].replace("#", ""))
    except ValueError:
        await update.message.reply_text("❌ Invalid card IDs. Must be numbers.")
        return

    # Ensure both users exist
    await ensure_user(None, user.id, user.username, user.first_name, user.last_name)
    await ensure_user(None, target_id, target_username, target_name, None)

    # Check sender owns the card they're offering
    owns_give = await check_user_owns_card(None, user.id, give_card_id)
    if not owns_give:
        await update.message.reply_text(
            f"❌ You don't own card `#{give_card_id}`!\n"
            f"Check your collection with /harem",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Check target owns the card being requested
    owns_want = await check_user_owns_card(None, target_id, want_card_id)
    if not owns_want:
        await update.message.reply_text(
            f"❌ *{target_name}* doesn't own card `#{want_card_id}`!",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Check pending trade limit
    pending = await count_pending_trades(None, user.id)
    if pending >= MAX_PENDING_TRADES:
        await update.message.reply_text(
            f"⚠️ You have {MAX_PENDING_TRADES} pending trades.\n"
            f"Complete or cancel some first with /trades",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Get card info
    give_card = await get_card_by_id(None, give_card_id)
    want_card = await get_card_by_id(None, want_card_id)

    if not give_card or not want_card:
        await update.message.reply_text("❌ One or both cards not found!")
        return

    give_emoji = RARITY_EMOJIS.get(give_card.get("rarity", 1), "❓")
    want_emoji = RARITY_EMOJIS.get(want_card.get("rarity", 1), "❓")

    # Create trade
    trade_id = await create_trade(
        pool=None,
        from_user=user.id,
        to_user=target_id,
        offered_card_id=give_card_id,
        requested_card_id=want_card_id
    )

    if not trade_id:
        await update.message.reply_text("❌ Failed to create trade. Try again.")
        return

    # Send confirmation to sender
    await update.message.reply_text(
        f"✅ *Trade Proposal Sent!*\n\n"
        f"📤 You give: {give_emoji} *{give_card.get('character_name')}*\n"
        f"📥 You want: {want_emoji} *{want_card.get('character_name')}*\n\n"
        f"Waiting for *{target_name}* to respond.\n"
        f"Trade ID: `#{trade_id}`",
        parse_mode=ParseMode.MARKDOWN
    )

    # Notify recipient with action buttons
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Accept", callback_data=f"ta:{trade_id}"),
            InlineKeyboardButton("❌ Decline", callback_data=f"tr:{trade_id}")
        ],
        [
            InlineKeyboardButton("👁️ View Cards", callback_data=f"tv:{trade_id}")
        ]
    ])

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                f"🔄 *Trade Request!*\n\n"
                f"From: *{user.first_name}*\n\n"
                f"📥 They offer: {give_emoji} *{give_card.get('character_name')}*\n"
                f"📤 They want: {want_emoji} *{want_card.get('character_name')}*\n\n"
                f"Trade ID: `#{trade_id}`"
            ),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
    except Exception as e:
        app_logger.warning(f"Failed to notify trade recipient: {e}")


# ============================================================
# 📢 Offer Command (Global Notification)
# ============================================================

async def offer_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /offer <want_card_id> <give_card_id> command.
    Posts a trade request to the notification channel.
    """
    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    log_command(user.id, "offer", update.effective_chat.id)

    if not db.is_connected:
        await update.message.reply_text(format_error("database"))
        return

    # Check if notification channel is configured
    if not TRADE_CHANNEL_ID:
        await update.message.reply_text(
            "❌ Trade notification channel not configured.\n"
            "Contact the bot admin to set up `TRADE_CHANNEL_ID`.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Parse arguments
    if len(context.args) < 2:
        await update.message.reply_text(
            "📢 *Global Trade Offer*\n\n"
            "Post a trade request for everyone to see!\n\n"
            "Usage: `/offer <want_card_id> <give_card_id>`\n\n"
            "Example: `/offer 100 42`\n"
            "(Want card #100, offering card #42)",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        want_card_id = int(context.args[0].replace("#", ""))
        give_card_id = int(context.args[1].replace("#", ""))
    except ValueError:
        await update.message.reply_text("❌ Invalid card IDs. Must be numbers.")
        return

    # Ensure user exists
    await ensure_user(None, user.id, user.username, user.first_name, user.last_name)

    # Check ownership of offered card
    owns = await check_user_owns_card(None, user.id, give_card_id)
    if not owns:
        await update.message.reply_text(
            f"❌ You don't own card `#{give_card_id}`!\n"
            f"Check your collection with /harem",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Get card info
    want_card = await get_card_by_id(None, want_card_id)
    give_card = await get_card_by_id(None, give_card_id)

    if not want_card:
        await update.message.reply_text(f"❌ Card `#{want_card_id}` not found!")
        return

    if not give_card:
        await update.message.reply_text(f"❌ Card `#{give_card_id}` not found!")
        return

    want_emoji = RARITY_EMOJIS.get(want_card.get("rarity", 1), "❓")
    give_emoji = RARITY_EMOJIS.get(give_card.get("rarity", 1), "❓")
    want_rarity, _, _ = rarity_to_text(want_card.get("rarity", 1))
    give_rarity, _, _ = rarity_to_text(give_card.get("rarity", 1))

    # Build username mention
    if user.username:
        user_mention = f"@{user.username}"
    else:
        user_mention = f"[{user.first_name}](tg://user?id={user.id})"

    # Post to notification channel
    channel_message = (
        f"📢 *Trade Offer*\n\n"
        f"👤 *From:* {user_mention}\n\n"
        f"🔍 *Looking for:*\n"
        f"{want_emoji} *{want_card.get('character_name')}*\n"
        f"└ {want_card.get('anime')} • {want_rarity}\n"
        f"└ `#{want_card_id}`\n\n"
        f"💎 *Offering:*\n"
        f"{give_emoji} *{give_card.get('character_name')}*\n"
        f"└ {give_card.get('anime')} • {give_rarity}\n"
        f"└ `#{give_card_id}`\n\n"
        f"📩 DM {user_mention} if interested!"
    )

    try:
        # Send to channel with card image
        photo_id = give_card.get("photo_file_id")
        if photo_id:
            await context.bot.send_photo(
                chat_id=TRADE_CHANNEL_ID,
                photo=photo_id,
                caption=channel_message,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await context.bot.send_message(
                chat_id=TRADE_CHANNEL_ID,
                text=channel_message,
                parse_mode=ParseMode.MARKDOWN
            )

        await update.message.reply_text(
            f"✅ *Offer Posted!*\n\n"
            f"Your trade offer has been posted to the trading channel.\n\n"
            f"🔍 Want: {want_emoji} *{want_card.get('character_name')}*\n"
            f"💎 Offer: {give_emoji} *{give_card.get('character_name')}*",
            parse_mode=ParseMode.MARKDOWN
        )

    except Exception as e:
        error_logger.error(f"Failed to post trade offer: {e}")
        await update.message.reply_text(
            "❌ Failed to post offer. The bot may not have access to the trading channel."
        )


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
    lines = ["🔄 *Your Trades*\n"]

    # Received trades
    if received:
        lines.append(f"📥 *Incoming* ({len(received)})")
        for trade in received[:5]:
            trade_id = trade.get("id")
            from_name = trade.get("from_user_name", "Unknown")
            char = trade.get("offered_character", "Unknown")
            rarity = trade.get("offered_rarity", 1)
            emoji = RARITY_EMOJIS.get(rarity, "❓")

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
            emoji = RARITY_EMOJIS.get(rarity, "❓")

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

    # Quick action buttons for received trades
    if received:
        action_row = []
        for trade in received[:3]:
            trade_id = trade.get("id")
            rarity = trade.get("offered_rarity", 1)
            emoji = RARITY_EMOJIS.get(rarity, "❓")
            action_row.append(
                InlineKeyboardButton(
                    f"{emoji} #{trade_id}",
                    callback_data=f"tv:{trade_id}"
                )
            )
        if action_row:
            buttons.append(action_row)

    # Bottom buttons
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
    offered_char = trade.get("offered_character", "Unknown")
    offered_anime = trade.get("offered_anime", "Unknown")
    offered_rarity = trade.get("offered_rarity", 1)
    offered_emoji = RARITY_EMOJIS.get(offered_rarity, "❓")

    # Requested card
    requested_id = trade.get("requested_card_id")
    requested_char = trade.get("requested_character")
    requested_rarity = trade.get("requested_rarity")
    requested_emoji = RARITY_EMOJIS.get(requested_rarity, "❓") if requested_rarity else ""

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
        f"🔄 *Trade #{trade_id}*",
        f"{status_emoji} Status: {status.upper()}",
        "",
        f"👤 From: *{from_name}*",
        f"👤 To: *{to_name}*",
        "",
        f"📤 *Offering:*",
        f"{offered_emoji} *{offered_char}*",
        f"└ {offered_anime}",
    ]

    if requested_id and requested_char:
        lines.extend([
            "",
            f"📥 *Requesting:*",
            f"{requested_emoji} *{requested_char}*",
        ])
    else:
        lines.extend([
            "",
            f"📥 *Requesting:* 🎁 Gift (no return)",
        ])

    caption = "\n".join(lines)

    # Build keyboard based on viewer and status
    buttons = []

    if status == "pending":
        if viewer_user_id == to_user:
            buttons.append([
                InlineKeyboardButton("✅ Accept", callback_data=f"ta:{trade_id}"),
                InlineKeyboardButton("❌ Decline", callback_data=f"tr:{trade_id}")
            ])
        elif viewer_user_id == from_user:
            buttons.append([
                InlineKeyboardButton("🚫 Cancel", callback_data=f"tc:{trade_id}")
            ])

    buttons.append([
        InlineKeyboardButton("📋 All Trades", callback_data="trades_refresh"),
        InlineKeyboardButton(ButtonLabels.CLOSE, callback_data="trades_close")
    ])

    keyboard = InlineKeyboardMarkup(buttons)

    if from_callback and update.callback_query:
        try:
            await update.callback_query.edit_message_text(
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

    trade = await get_trade(None, trade_id)

    if not trade:
        await update.message.reply_text("❌ Trade not found.")
        return

    if trade["from_user"] != user.id:
        await update.message.reply_text("❌ Only the sender can cancel this trade.")
        return

    if trade["status"] != "pending":
        await update.message.reply_text(f"❌ Trade is already {trade['status']}.")
        return

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

    if data == "trades_close":
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.answer()
        return

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
    trade = await get_trade(None, trade_id)

    if not trade:
        await query.answer("Trade not found!", show_alert=True)
        return

    if trade["to_user"] != user_id:
        await query.answer("Only the recipient can accept!", show_alert=True)
        return

    if trade["status"] != "pending":
        await query.answer(f"Trade is {trade['status']}", show_alert=True)
        return

    # Execute transfer
    from_user = trade["from_user"]
    to_user = trade["to_user"]
    offered_card_id = trade["offered_card_id"]
    requested_card_id = trade.get("requested_card_id")

    # Transfer offered card
    success, msg = await transfer_card_between_users(None, from_user, to_user, offered_card_id, 1)

    if not success:
        await update_trade_status(None, trade_id, "failed")
        await query.answer(f"Failed: {msg}", show_alert=True)
        return

    # Transfer requested card if exists
    if requested_card_id:
        success2, msg2 = await transfer_card_between_users(None, to_user, from_user, requested_card_id, 1)
        if not success2:
            await update_trade_status(None, trade_id, "failed")
            await query.answer(f"Partial failure: {msg2}", show_alert=True)
            return

    # Complete trade
    await update_trade_status(None, trade_id, "completed")

    offered_char = trade.get("offered_character", "Card")
    offered_emoji = RARITY_EMOJIS.get(trade.get("offered_rarity", 1), "❓")

    await query.answer("Trade completed!", show_alert=True)

    await query.edit_message_text(
        f"✅ *Trade Completed!*\n\n"
        f"You received: {offered_emoji} *{offered_char}*\n\n"
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
                f"They received: {offered_emoji} *{offered_char}*"
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
    trade = await get_trade(None, trade_id)

    if not trade:
        await query.answer("Trade not found!", show_alert=True)
        return

    if trade["to_user"] != user_id:
        await query.answer("Only the recipient can decline!", show_alert=True)
        return

    await update_trade_status(None, trade_id, "rejected")
    await query.answer("Trade declined")

    await query.edit_message_text(
        f"❌ *Trade Declined*\n\n"
        f"Trade `#{trade_id}` has been declined.",
        parse_mode=ParseMode.MARKDOWN
    )

    # Notify sender
    try:
        await context.bot.send_message(
            chat_id=trade["from_user"],
            text=(
                f"❌ *Trade Declined*\n\n"
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
    trade = await get_trade(None, trade_id)

    if not trade:
        await query.answer("Trade not found!", show_alert=True)
        return

    if trade["from_user"] != user_id:
        await query.answer("Only the sender can cancel!", show_alert=True)
        return

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
    """Register all trade handlers."""

    # Commands
    application.add_handler(CommandHandler("gift", gift_command))
    application.add_handler(CommandHandler("trade", trade_command))
    application.add_handler(CommandHandler("offer", offer_command))
    application.add_handler(CommandHandler("trades", trades_command))
    application.add_handler(CommandHandler("canceltrade", canceltrade_command))

    # Gift callbacks
    application.add_handler(
        CallbackQueryHandler(gift_confirm_callback, pattern=r"^gift_confirm:")
    )
    application.add_handler(
        CallbackQueryHandler(gift_cancel_callback, pattern=r"^gift_cancel$")
    )

    # Trade list callbacks
    application.add_handler(
        CallbackQueryHandler(trades_callback_handler, pattern=r"^trades_")
    )

    # Trade action callbacks
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