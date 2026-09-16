# Copyright (c) 2025 devgagan : https://github.com/devgaganin.
# Licensed under the GNU General Public License v3.0.
# See LICENSE file in the repository root for full license text.

import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass



API_ID       = int(os.getenv("API_ID", "32324370"))
API_HASH     = os.getenv("API_HASH", "744f8b1e73b6b3262c3c8c1ea577229c")
BOT_TOKEN    = os.getenv("BOT_TOKEN", "7566739138:AAFqGisV6TH6_RZhEX_wHixT5WRzG7mpnlw")
MONGO_DB     = os.getenv("MONGO_DB", "mongodb+srv://nik9076:kNjKz9fkP6IeZrsC@nik.aft4fcq.mongodb.net/?appName=nik")
DB_NAME      = os.getenv("DB_NAME", "telegram_downloader")

SETTINGS_MONGO_URI = os.getenv("SETTINGS_MONGO_URI", "mongodb+srv://nikhil_database:Nikhil9076%40123@nikhil.7fokdnr.mongodb.net/?appName=nikhil")
SETTINGS_DB_NAME   = os.getenv("SETTINGS_DB_NAME", "telegram_settings_db")

OWNER_ID     = list(map(int, os.getenv("OWNER_ID", "8693484744").split()))
ADMINS       = OWNER_ID
STRING       = os.getenv("STRING", "AQHtOxIAuJyJhLh1EUsu42IhSSdGvY081xQhalJOSxCNvOuVZIUKQYmWK1WgxF2kND6vf4OdkL9HuVQm4Dv83MXB3vQvUG2gc0i4BD-j2cqPeeLjqH-6MekWGVAC8X3nB8RnfwWYXqZ3TU7NX4VHtQ0673gYI9E-ITJFN_Uf8VAsC3smPEQoaT4qe9R_WCutv6l2dIpZH3XxHOHlDfKbNRshz-J_R8lM_li9pJ3Hgn9LyTr0sSxeN0q-RDo8Wyf4lhzgcX287w6JvhD95EbmssdheQnQZV7aLv_WUXU_h5ymoMXOJqOccSgKm_aNDM5ofKu980JekcPoHYrv67x38Wtp3H-mggAAAAIGLAzIAA")
LOG_GROUP    = int(os.getenv("LOG_GROUP", "-1003716177168"))

FORCE_SUB_CHANNELS = [
    {"name": "💬 Support Group", "url": "https://t.me/niksupportgroup", "chat": "niksupportgroup"},
    {"name": "📢 Updates Channel", "url": "https://t.me/nikbotchannel", "chat": "nikbotchannel"}
]
FORCE_SUB_CHANNEL = "nikbotchannel"
FORCE_SUB = FORCE_SUB_CHANNEL

MASTER_KEY   = os.getenv("MASTER_KEY", "gK8HzLfT9QpViJcYeB5wRa3DmN7P2xUq")
SECRET_KEY   = MASTER_KEY
IV_KEY       = os.getenv("IV_KEY", "s7Yx5CpVmE3F")


DEFAULT_THUMB = os.getenv("DEFAULT_THUMB", "default_thumb.jpg")
DEFAULT_THUMB_URL = "https://i.postimg.cc/2ysJtXKC/nikhil.png"
THUMB_DIR = os.path.join(os.path.dirname(__file__), "thumbnails")
os.makedirs(THUMB_DIR, exist_ok=True)

FREEMIUM_LIMIT = int(os.getenv("FREEMIUM_LIMIT", "1"))
PREMIUM_LIMIT  = int(os.getenv("PREMIUM_LIMIT", "50000"))
MAX_BATCH_SIZE = int(os.getenv("MAX_BATCH_SIZE", "100"))

JOIN_LINK     = os.getenv("JOIN_LINK", "https://t.me/nikbotchannel")
ADMIN_CONTACT = os.getenv("ADMIN_CONTACT", "https://t.me/ananomusbro")

VIP_PLAN = {
    "price": int(os.getenv("VIP_PRICE", 200)),
    "duration_days": int(os.getenv("VIP_DAYS", 7)),
    "files_limit": "Unlimited",
    "name": "Super VIP 7 Days Unlimited"
}

P0 = {
    "vip": {
        "s": int(os.getenv("VIP_PRICE", 200)),
        "du": int(os.getenv("VIP_DAYS", 7)),
        "u": "days",
        "l": "VIP Plan (7 Days Unlimited)",
    }
}
