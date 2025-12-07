# config.py
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g. https://your-app.up.railway.app (no trailing /webhook)
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# Postgres env names expected
PGHOST = os.getenv("PGHOST")
PGDATABASE = os.getenv("PGDATABASE")
PGUSER = os.getenv("PGUSER")
PGPASSWORD = os.getenv("PGPASSWORD")

# web server port (Railway sets PORT)
PORT = int(os.getenv("PORT", 8000))
