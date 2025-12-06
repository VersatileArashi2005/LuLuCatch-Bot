from telegram.ext import Application, CommandHandler, MessageHandler, filters
from commands.upload import upload_start, upload_anime, upload_character, upload_rarity, upload_photo
from commands.check import check_card

app = Application.builder().token("BOT_TOKEN").build()

from telegram.ext import ConversationHandler
upload_conv = ConversationHandler(
    entry_points=[CommandHandler('upload', upload_start)],
    states={
        ANIME: [CallbackQueryHandler(upload_anime, pattern="^anime_")],
        CHARACTER: [CallbackQueryHandler(upload_character, pattern="^char_")],
        RARITY: [CallbackQueryHandler(upload_rarity, pattern="^rar_")],
        PHOTO: [MessageHandler(filters.PHOTO, upload_photo)]
    },
    fallbacks=[]
)

app.add_handler(upload_conv)
app.add_handler(CommandHandler("check", check_card))

app.run_polling()
