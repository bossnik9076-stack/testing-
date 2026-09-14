import os
import json
import logging
import asyncio

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from pyrogram import Client as PyroClient
from telethon import TelegramClient
from telethon.sessions import MemorySession
from config import API_ID, API_HASH, BOT_TOKEN, STRING

logger = logging.getLogger(__name__)

app = PyroClient(
    "restricted_saver_bot",
    api_id=int(API_ID),
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=32,
    max_concurrent_transmissions=10,
    in_memory=True
)

client = None
try:
    if API_ID and API_HASH:
        client = TelegramClient(MemorySession(), int(API_ID), str(API_HASH))
except Exception as e:
    logger.warning(f"Telethon client init warning: {e}")
    client = None

bot_client = client

userbot = None
if STRING:
    try:
        userbot = PyroClient(
            "userbot_session",
            api_id=int(API_ID),
            api_hash=API_HASH,
            session_string=STRING,
            in_memory=True
        )
    except Exception as e:
        logger.warning(f"UserBot init warning: {e}")

async def get_user_client(user_id):
    try:
        from plugins.batch import get_uclient
        return await get_uclient(user_id)
    except Exception:
        return userbot

ACTIVE_USERS_FILE = os.path.join(os.path.dirname(__file__), "active_users.json")

def load_data():
    if not os.path.exists(ACTIVE_USERS_FILE):
        return {"users": [], "banned_users": [], "premium_users": {}, "user_settings": {}, "active_sessions": {}}
    try:
        with open(ACTIVE_USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"users": [], "banned_users": [], "premium_users": {}, "user_settings": {}, "active_sessions": {}}

def save_data(data):
    with open(ACTIVE_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
