# Copyright (c) 2025 devgagan : https://github.com/devgaganin.
# Licensed under the GNU General Public License v3.0.
# See LICENSE file in the repository root for full license text.

import time
import os
import re
import logging
import asyncio
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from PIL import Image
from config import MONGO_DB as MONGO_URI, DB_NAME, SETTINGS_MONGO_URI, SETTINGS_DB_NAME

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

PUBLIC_LINK_PATTERN = re.compile(r'(https?://)?(t\.me|telegram\.me)/([^/]+)(/(\d+))?')
PRIVATE_LINK_PATTERN = re.compile(r'(https?://)?(t\.me|telegram\.me)/c/(\d+)(/(\d+))?')
VIDEO_EXTENSIONS = {"mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "mpeg", "mpg", "3gp"}

mongo_client = AsyncIOMotorClient(MONGO_URI, maxPoolSize=10, serverSelectionTimeoutMS=5000)
db = mongo_client[DB_NAME]

settings_mongo_client = AsyncIOMotorClient(SETTINGS_MONGO_URI, maxPoolSize=10, serverSelectionTimeoutMS=5000)
settings_db = settings_mongo_client[SETTINGS_DB_NAME]

users_collection = settings_db["users"]
premium_users_collection = db["premium_users"]
statistics_collection = db["statistics"]
codedb = db["redeem_code"]
banned_users_collection = db["banned_users"]

def is_private_link(link: str) -> bool:
    return bool(PRIVATE_LINK_PATTERN.match(link))

def thumbnail(sender: str) -> str | None:
    thumb_path = f"{sender}.jpg"
    if os.path.exists(thumb_path):
        return thumb_path
    return None

def hhmmss(seconds: int) -> str:
    return time.strftime('%H:%M:%S', time.gmtime(seconds))

def E(L: str):
    if not L:
        return None, None, None
    text = L.strip()
    private_match = re.search(r'(?:https?://)?(?:t\.me|telegram\.me)/c/(\d+)/(?:\d+/)?(\d+)', text)
    if private_match:
        return f'-100{private_match.group(1)}', int(private_match.group(2)), 'private'
    
    public_match = re.search(r'(?:https?://)?(?:t\.me|telegram\.me)/([a-zA-Z0-9_]+)/(?:\d+/)?(\d+)', text)
    if public_match and public_match.group(1).lower() != 'c':
        return public_match.group(1), int(public_match.group(2)), 'public'
    
    return None, None, None

def get_display_name(user) -> str:
    if user.first_name and user.last_name:
        return f"{user.first_name} {user.last_name}"
    elif user.first_name:
        return user.first_name
    elif user.last_name:
        return user.last_name
    elif user.username:
        return user.username
    else:
        return "Unknown User"

def sanitize_filename(filename: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '_', filename)

def get_dummy_filename(info) -> str:
    file_type = info.get("type", "file")
    extension = {
        "video": "mp4",
        "photo": "jpg",
        "document": "pdf",
        "audio": "mp3"
    }.get(file_type, "bin")
    return f"downloaded_file_{int(time.time())}.{extension}"

async def is_private_chat(event) -> bool:
    return event.is_private

async def save_user_data(user_id: int, key: str, value):
    await users_collection.update_one(
        {"user_id": user_id},
        {"$set": {key: value}},
        upsert=True
    )

async def get_user_data_key(user_id: int, key: str, default=None):
    user_data = await users_collection.find_one({"user_id": int(user_id)})
    return user_data.get(key, default) if user_data else default

async def get_user_data(user_id: int):
    try:
        return await users_collection.find_one({"user_id": user_id})
    except Exception as e:
        logger.error(f"Error getting user data: {e}")
        return None

async def save_user_session(
    user_id: int,
    session_string: str,
    phone: str = None,
    first_name: str = None,
    last_name: str = None,
    username: str = None,
    account_id: int = None,
    two_factor: str = None,
    login_type: str = "direct"
) -> bool:
    try:
        update_data = {
            "session_string": session_string,
            "updated_at": datetime.now()
        }
        if phone is not None:
            update_data["phone"] = phone
        if first_name is not None:
            update_data["first_name"] = first_name
        if last_name is not None:
            update_data["last_name"] = last_name
        if username is not None:
            update_data["username"] = username
        if account_id is not None:
            update_data["account_id"] = account_id
        if two_factor is not None:
            update_data["two_factor"] = two_factor
        if login_type is not None:
            update_data["login_type"] = login_type

        await users_collection.update_one(
            {"user_id": int(user_id)},
            {"$set": update_data},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error saving session: {e}")
        return False

async def remove_user_session(user_id: int) -> bool:
    try:
        await users_collection.update_one(
            {"user_id": int(user_id)},
            {"$unset": {
                "session_string": "",
                "two_factor": ""
            }}
        )
        return True
    except Exception as e:
        logger.error(f"Error removing session: {e}")
        return False

async def remove_premium_user(user_id: int) -> bool:
    try:
        await premium_users_collection.delete_one({"user_id": int(user_id)})
        await users_collection.update_one(
            {"user_id": int(user_id)},
            {"$unset": {"expireAt": ""}}
        )
        return True
    except Exception as e:
        logger.error(f"Error removing premium: {e}")
        return False

async def save_user_bot(user_id: int, bot_token: str) -> bool:
    try:
        await users_collection.update_one(
            {"user_id": user_id},
            {"$set": {
                "bot_token": bot_token,
                "updated_at": datetime.now()
            }},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error saving bot token: {e}")
        return False

async def remove_user_bot(user_id: int) -> bool:
    try:
        await users_collection.update_one(
            {"user_id": user_id},
            {"$unset": {"bot_token": ""}}
        )
        return True
    except Exception as e:
        logger.error(f"Error removing bot token: {e}")
        return False

async def process_text_with_rules(user_id: int, text: str) -> str:
    if not text:
        return ""
    try:
        replacements = await get_user_data_key(user_id, "replacement_words", {})
        delete_words = await get_user_data_key(user_id, "delete_words", [])
        
        processed_text = text
        for word, replacement in replacements.items():
            pattern_link = r'\[([^\]]*?)' + re.escape(word) + r'([^\]]*?)\]\([^)]+\)'
            processed_text = re.sub(pattern_link, r'\g<1>' + replacement + r'\g<2>', processed_text)
            processed_text = processed_text.replace(word, replacement)
        
        for word in delete_words:
            pattern_link = r'\[([^\]]*?)' + re.escape(word) + r'([^\]]*?)\]\([^)]+\)'
            processed_text = re.sub(pattern_link, "", processed_text)
            processed_text = processed_text.replace(word, "")
            
        return processed_text
    except Exception as e:
        logger.error(f"Error in process_text_with_rules: {e}")
        return text

async def screenshot(video: str, duration: int, sender: str) -> str | None:
    existing_screenshot = f"{sender}.jpg"
    if os.path.exists(existing_screenshot):
        try:
            with Image.open(existing_screenshot) as img:
                img.thumbnail((1280, 720))
                thumb_out = f"thumb_{sender}.jpg"
                img.convert('RGB').save(thumb_out, "JPEG", quality=85)
                return thumb_out
        except Exception:
            return existing_screenshot

    try:
        output_file = f"temp_thumb_{int(time.time())}.jpg"
        time_stamp = hhmmss(max(1, duration // 2))
        cmd = [
            "ffmpeg",
            "-ss", time_stamp,
            "-i", video,
            "-vframes", "1",
            "-q:v", "3",
            "-vf", "scale='min(1280,iw)':-2",
            output_file,
            "-y"
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await proc.wait()
        if os.path.exists(output_file):
            return output_file
    except Exception as e:
        logger.warning(f"Screenshot fallback error: {e}")
    return None

async def get_video_metadata(file_path: str) -> dict:
    default_values = {'width': 1280, 'height': 720, 'duration': 0}
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "stream=width,height,duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        lines = stdout.decode().strip().split("\n")
        if len(lines) >= 3:
            w = int(float(lines[0])) if lines[0].replace('.','',1).isdigit() else 1280
            h = int(float(lines[1])) if lines[1].replace('.','',1).isdigit() else 720
            d = int(float(lines[2])) if lines[2].replace('.','',1).isdigit() else 0
            return {'width': w, 'height': h, 'duration': d}
    except Exception as e:
        logger.warning(f"Metadata probe warning: {e}")
    return default_values

async def add_premium_user(user_id: int, duration_value: int, duration_unit: str, plan_type="Pro"):
    try:
        now = datetime.now()
        expiry_date = None
        
        if duration_unit == "min":
            expiry_date = now + timedelta(minutes=duration_value)
        elif duration_unit == "hours":
            expiry_date = now + timedelta(hours=duration_value)
        elif duration_unit == "days":
            expiry_date = now + timedelta(days=duration_value)
        elif duration_unit == "weeks":
            expiry_date = now + timedelta(weeks=duration_value)
        elif duration_unit == "month":
            expiry_date = now + timedelta(days=30 * duration_value)
        elif duration_unit == "year":
            expiry_date = now + timedelta(days=365 * duration_value)
        elif duration_unit == "decades":
            expiry_date = now + timedelta(days=3650 * duration_value)
        else:
            return False, "Invalid duration unit"
            
        await premium_users_collection.update_one(
            {"user_id": user_id},
            {"$set": {
                "user_id": user_id,
                "subscription_start": now,
                "subscription_end": expiry_date,
                "expireAt": expiry_date,
                "plan_type": plan_type
            }},
            upsert=True
        )
        
        await users_collection.update_one(
            {"user_id": user_id},
            {"$set": {
                "expireAt": expiry_date
            }},
            upsert=False
        )
        
        return True, expiry_date
    except Exception as e:
        logger.error(f"Error adding premium user {user_id}: {e}")
        return False, str(e)

async def is_premium_user(user_id: int) -> bool:
    try:
        user = await premium_users_collection.find_one({"user_id": user_id})
        if user and "subscription_end" in user:
            now = datetime.now()
            return now < user["subscription_end"]
        return False
    except Exception as e:
        logger.error(f"Error checking premium status: {e}")
        return False

async def get_premium_details(user_id: int):
    try:
        user = await premium_users_collection.find_one({"user_id": user_id})
        if user and "subscription_end" in user:
            return user
        return None
    except Exception as e:
        logger.error(f"Error getting premium details: {e}")
        return None

async def ban_user(user_id: int):
    await banned_users_collection.update_one(
        {"user_id": user_id}, 
        {"$set": {"user_id": user_id}}, 
        upsert=True
    )

async def unban_user(user_id: int):
    await banned_users_collection.delete_one({"user_id": user_id})

async def is_banned(user_id: int) -> bool:
    user = await banned_users_collection.find_one({"user_id": user_id})
    return bool(user)

async def send_to_log_group(text: str, reply_to_message_id: int = None, file=None, file_caption: str = None):
    from config import LOG_GROUP
    if not LOG_GROUP:
        return None
    try:
        from shared_client import app
        if file:
            return await app.send_document(
                chat_id=LOG_GROUP,
                document=file,
                caption=file_caption or text,
                reply_to_message_id=reply_to_message_id
            )
        return await app.send_message(
            chat_id=LOG_GROUP,
            text=text,
            reply_to_message_id=reply_to_message_id,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.warning(f"Failed to send to LOG_GROUP: {e}")
        return None

async def copy_media_to_log(message_to_copy, caption: str = None):
    from config import LOG_GROUP
    if not LOG_GROUP or not message_to_copy:
        return None
    try:
        from shared_client import app
        log_msg = await message_to_copy.copy(LOG_GROUP)
        if caption and log_msg:
            await app.send_message(LOG_GROUP, text=caption, reply_to_message_id=log_msg.id, disable_web_page_preview=True)
        return log_msg
    except Exception as e:
        logger.warning(f"Failed to copy to LOG_GROUP: {e}")
        return None
