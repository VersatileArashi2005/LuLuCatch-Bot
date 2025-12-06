# main.py

import os
import asyncio
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, ContextTypes, Update

# Placeholder for database connection (Assuming database.py will handle the actual connection)
async def init_db_connection():
    # Replace this with your actual database connection logic later
    print("Database connection check completed.")
    pass

# Start command handler
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_text(f"Hello {user.first_name}! I am LuLuCatch Bot.")

async def main():
    # Load environment variables from .env file (for local testing)
    # Railway will inject these variables directly, but this is good practice
    load_dotenv()
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

    if not TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not found.")
        return

    # Initialize Database Connection
    await init_db_connection()
    
    # Setup the Application
    application = Application.builder().token(TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    
    print("LuLuCatch Bot is running...")
    
    # Start Polling
    await application.run_polling(poll_interval=3)

if __name__ == "__main__":
    # The asyncio.run() function runs the main coroutine
    asyncio.run(main())