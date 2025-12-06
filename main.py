# main.py

import os
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

def main() -> None:
    # Load environment variables (dotenv is primarily for local)
    load_dotenv()
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

    if not TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not found in environment variables.")
        return

    # In an async environment, you need to run async functions within the loop
    # For simplicity, we skip init_db_connection call here and assume the setup is simple.
    
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    
    print("LuLuCatch Bot is running...")
    
    # Use run_polling for simple setups, or run_webhook for better performance.
    # We use run_forever() to let the system handle the loop for long running process
    application.run_polling(poll_interval=3)

if __name__ == "__main__":
    main() # Call main function directly without asyncio.run()
    
    # We use Polling for simplicity here, but Webhooks are better for Railway
    await application.run_polling(poll_interval=3)

if __name__ == "__main__":
    asyncio.run(main())
