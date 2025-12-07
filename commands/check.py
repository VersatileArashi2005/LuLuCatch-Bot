from aiogram import Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db import get_card_info, get_card_top_owners, get_user_card_count

router = Router()

# /check <card_id>
@router.message(Command("check"))
async def check_card(message: types.Message):
    args = message.text.split()

    # Validate arguments
    if len(args) < 2:
        return await message.answer("❌ Usage: /check <card_id>")

    card_id = args[1]

    # Fetch card info
    card = await get_card_info(card_id)
    if not card:
        return await message.answer("❌ Card not found.")

    card_name = card["name"]
    anime = card["anime"]
    rarity = card["rarity"]
    image_url = card["image_url"]

    # Fetch top 5 owners
    top_owners = await get_card_top_owners(card_id)

    if top_owners:
        rank_text = "🏆 *Top Owners*\n"
        for i, owner in enumerate(top_owners, start=1):
            uid = owner["user_id"]
            count = owner["count"]
            username = f"[User](tg://user?id={uid})"
            rank_text += f"{i}. {username} — *{count}*\n"
    else:
        rank_text = "No owners yet."

    # Build caption
    caption = (
        f"🆔 *ID:* {card_id}\n"
        f"🎴 *Name:* {card_name}\n"
        f"📺 *Anime:* {anime}\n"
        f"💎 *Rarity:* {rarity}\n\n"
        f"{rank_text}"
    )

    # Build inline button
    kb = InlineKeyboardBuilder()
    kb.button(
        text="How Many I Have",
        callback_data=f"check_have:{card_id}"
    )
    kb.adjust(1)

    # Send image + caption
    await message.answer_photo(
        photo=image_url,
        caption=caption,
        reply_markup=kb.as_markup(),
        parse_mode="Markdown"
    )


# Callback — "How Many I Have"
@router.callback_query(lambda c: c.data.startswith("check_have:"))
async def check_have_callback(callback: types.CallbackQuery):
    card_id = callback.data.split(":")[1]
    user_id = callback.from_user.id

    count = await get_user_card_count(user_id, card_id)

    await callback.answer(
        f"You own {count} copies of this card.",
        show_alert=True
    )