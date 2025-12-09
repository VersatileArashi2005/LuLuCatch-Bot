import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g. https://your-app.up.railway.app
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

PGHOST = os.getenv("PGHOST")
PGPORT = int(os.getenv("PGPORT", "5432"))
PGDATABASE = os.getenv("PGDATABASE")
PGUSER = os.getenv("PGUSER")
PGPASSWORD = os.getenv("PGPASSWORD")

PORT = int(os.getenv("PORT", "8000"))

# default cooldown hours for /lulucatch
DEFAULT_COOLDOWN_HOURS = int(os.getenv("DEFAULT_COOLDOWN_HOURS", "24"))