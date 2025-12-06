# main.py

import os
import asyncio # New: Need asyncio for running the async function
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
    await update.message.reply_text(f"Hello {user.first_name}! I am LuLuCatch Bot.")

# Function that contains all async operations, declared as async
async def start_bot() -> None:
    # Load environment variables
    load_dotenv()
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

    if not TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not found in environment variables.")
        return

    # Call async database initialization (Needs await)
    await init_db_connection()
    
    # Initialize Application
    application = Application.builder().token(TOKEN).build()
    
    # Add Handlers
    application.add_handler(CommandHandler("start", start_command))
    
    print("LuLuCatch Bot is running...")
    
    # Start polling using await
    await application.run_polling(poll_interval=3)

# The main execution block starts the async function
if __name__ == "__main__":
    try:
        # Calls the async start_bot function using asyncio
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        print("Bot shutting down...")
    except Exception as e:
        print(f"An error occurred: {e}")
