import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Bir nechta API kalitlarni o'qish (.env dagi vergul bilan ajratilgan kalitlar)
raw_keys = os.getenv("GEMINI_API_KEYS", GEMINI_API_KEY or "")
GEMINI_API_KEYS = [k.strip() for k in raw_keys.split(",") if k.strip()]

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN topilmadi! .env faylini tekshiring.")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY topilmadi! .env faylini tekshiring.")
