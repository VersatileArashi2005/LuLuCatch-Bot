# main.py

import os
import asyncio 
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Placeholder for database connection
async def init_db_connection():
    print("Database connection check completed.")
    pass

# Start command handler
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_text(f"Hello {user.first_name}! I am LuLuCatch Bot. I am running via Webhook.")

# Function that contains all async operations, declared as async
async def start_bot() -> None:
    # Load environment variables
    load_dotenv()
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

    if not TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not found in environment variables.")
        return

    # Call async database initialization
    await init_db_connection()
    
    # Initialize Application
    application = Application.builder().token(TOKEN).build()
    
    # Add Handlers
    application.add_handler(CommandHandler("start", start_command))
    
    print("LuLuCatch Bot is starting...")

    # Webhook setup for Railway
    PORT = int(os.environ.get('PORT', '8080'))
    WEBHOOK_URL = os.getenv("WEBHOOK_URL") 
    
    # Standard Webhook Path
    URL_PATH = "update"

    if WEBHOOK_URL is None:
        print("ERROR: WEBHOOK_URL environment variable is missing. Falling back to Polling.")
        await application.run_polling(poll_interval=3)
        return

    # 1. Set Webhook URL to Telegram
    await application.bot.set_webhook(url=f"{WEBHOOK_URL}/{URL_PATH}") 

    print(f"LuLuCatch Bot is running with Webhooks on port {PORT}...")

    # 2. Start the Webhook Server
    await application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=URL_PATH,
    )

# The main execution block starts the async function
if __name__ == "__main__":
    try:
        # Calls the async start_bot function using asyncio
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        print("Bot shutting down...")
    except Exception as e:
        print(f"An error occurred: {e}")
