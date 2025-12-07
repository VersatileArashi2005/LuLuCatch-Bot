# main.py
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext
from commands.start import start
from commands.help import help_command
from commands.profile import profile
from commands.catch import catch
from commands.harem import harem
from commands.trade import trade
from commands.smash import smash
from commands.setfav import setfav
from commands.admin import admin_commands
from commands.upload import upload_handlers
from commands.check import check_card

TOKEN = "YOUR_BOT_TOKEN"

app = ApplicationBuilder().token(TOKEN).build()

# User Commands
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("profile", profile))
app.add_handler(CommandHandler("catch", catch))
app.add_handler(CommandHandler("harem", harem))
app.add_handler(CommandHandler("trade", trade))
app.add_handler(CommandHandler("smash", smash))
app.add_handler(CommandHandler("setfav", setfav))
app.add_handler(CommandHandler("check", check_card))

# Admin / Owner Commands
admin_commands(app)

# Upload handlers (Step 1-3)
upload_handlers(app)

app.run_polling()
