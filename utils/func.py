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
from config import (
    MONGO_DB as MONGO_URI, DB_NAME, 
    SETTINGS_MONGO_URI, SETTINGS_DB_NAME,
    CACHE_MONGO_URI, CACHE_DB_NAME,
    THUMB_DIR, DEFAULT_THUMB
)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

PUBLIC_LINK_PATTERN = re.compile(r'(https?://)?(t\.me|telegram\.me)/([^/]+)(/(\d+))?')
PRIVATE_LINK_PATTERN = re.compile(r'(https?://)?(t\.me|telegram\.me)/c/(\d+)(/(\d+))?')
VIDEO_EXTENSIONS = {"mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "mpeg", "mpg", "3gp"}

# Cluster 1: Primary Auth & VIP Cluster (nik9076)
mongo_client = AsyncIOMotorClient(MONGO_URI, maxPoolSize=10, serverSelectionTimeoutMS=5000)
db = mongo_client[DB_NAME]

# Cluster 2: User Profiles & Settings Cluster (nikhil_database)
settings_mongo_client = AsyncIOMotorClient(SETTINGS_MONGO_URI, maxPoolSize=10, serverSelectionTimeoutMS=5000)
settings_db = settings_mongo_client[SETTINGS_DB_NAME]

# Cluster 3: High-Volume Cache & Stats Cluster (earlbrooks41441) - Distributes heavy load away from clusters 1 & 2!
cache_mongo_client = AsyncIOMotorClient(CACHE_MONGO_URI, maxPoolSize=10, serverSelectionTimeoutMS=5000)
cache_db = cache_mongo_client[CACHE_DB_NAME]

# Distributed Collections:
users_collection = settings_db["users"]
premium_users_collection = db["premium_users"]
codedb = db["redeem_code"]
banned_users_collection = db["banned_users"]
cached_peers_collection = cache_db["cached_peers"]
statistics_collection = cache_db["statistics"]

async def save_peers_to_db(peers):
    """
    Saves peers (id, access_hash, type, username, phone_number) into MongoDB
    so they persist permanently across server restarts and rebuilds.
    """
    if not peers:
        return
    try:
        from pymongo import UpdateOne
        operations = []
        for p in peers:
            if not p or len(p) < 3:
                continue
            peer_id = p[0]
            access_hash = p[1]
            peer_type = p[2]
            username = p[3] if len(p) > 3 else None
            phone = p[4] if len(p) > 4 else None
            
            if peer_id and access_hash is not None and access_hash != 0:
                operations.append(
                    UpdateOne(
                        {"_id": int(peer_id)},
                        {"$set": {
                            "peer_id": int(peer_id),
                            "access_hash": int(access_hash),
                            "type": str(peer_type),
                            "username": username,
                            "phone_number": phone,
                            "updated_at": datetime.utcnow()
                        }},
                        upsert=True
                    )
                )
        if operations:
            await cached_peers_collection.bulk_write(operations, ordered=False)
            logger.info(f"💾 Synced {len(operations)} peers to MongoDB cached_peers on Cluster 3.")
    except Exception as e:
        logger.error(f"Error saving peers to MongoDB: {e}")

async def load_all_peers_from_db():
    """
    Loads all saved peers from MongoDB cached_peers collection on Cluster 3.
    Also seamlessly migrates and cleans legacy peers from Cluster 1 if present.
    Returns list of tuples: (peer_id, access_hash, type, username, phone_number)
    """
    try:
        peers = []
        cursor = cached_peers_collection.find({})
        async for doc in cursor:
            pid = doc.get("_id") if doc.get("_id") is not None else doc.get("peer_id")
            ah = doc.get("access_hash")
            ptype = doc.get("type", "channel")
            un = doc.get("username")
            pn = doc.get("phone_number")
            if pid is not None and ah is not None:
                peers.append((int(pid), int(ah), str(ptype), un, pn))

        # Check and migrate legacy peers from Cluster 1 to free up Cluster 1 storage
        try:
            legacy_col = db["cached_peers"]
            legacy_count = await legacy_col.count_documents({})
            if legacy_count > 0:
                logger.info(f"🔄 Migrating {legacy_count} peers from Cluster 1 to Cluster 3 cache DB...")
                from pymongo import UpdateOne
                ops = []
                async for doc in legacy_col.find({}):
                    pid = doc.get("_id") if doc.get("_id") is not None else doc.get("peer_id")
                    ah = doc.get("access_hash")
                    ptype = doc.get("type", "channel")
                    un = doc.get("username")
                    pn = doc.get("phone_number")
                    if pid is not None and ah is not None:
                        peers.append((int(pid), int(ah), str(ptype), un, pn))
                        ops.append(UpdateOne({"_id": int(pid)}, {"$set": doc}, upsert=True))
                if ops:
                    await cached_peers_collection.bulk_write(ops, ordered=False)
                await legacy_col.drop()
                logger.info("✅ Migrated all legacy cached peers to Cluster 3 and dropped legacy collection on Cluster 1!")
        except Exception as mig_e:
            logger.debug(f"Legacy peer check note: {mig_e}")

        return peers
    except Exception as e:
        logger.error(f"Error loading peers from MongoDB: {e}")
        return []

async def load_db_peers_into_storage(client):
    """
    Loads all peers from MongoDB and injects them into the Pyrogram client's storage.
    """
    if not client or not hasattr(client, "storage"):
        return
    try:
        peers = await load_all_peers_from_db()
        if peers:
            await client.storage.update_peers(peers)
            logger.info(f"✅ Loaded {len(peers)} cached peers from MongoDB into Pyrogram storage.")
    except Exception as e:
        logger.error(f"Error injecting peers into client storage: {e}")

def setup_peer_storage_sync(client):
    """
    Wraps client.storage.update_peers so any peer learned by Pyrogram
    is automatically mirrored to MongoDB in the background.
    """
    if not client or not hasattr(client, "storage"):
        return
    if getattr(client.storage, "_mongo_peer_sync_enabled", False):
        return
    orig_update_peers = client.storage.update_peers

    async def wrapped_update_peers(peers):
        res = await orig_update_peers(peers)
        try:
            asyncio.create_task(save_peers_to_db(peers))
        except Exception:
            pass
        return res

    client.storage.update_peers = wrapped_update_peers
    client.storage._mongo_peer_sync_enabled = True
    logger.info("⚡ MongoDB peer sync hook attached to Pyrogram client.")

def is_private_link(link: str) -> bool:
    return bool(PRIVATE_LINK_PATTERN.match(link))

def thumbnail(sender: str) -> str | None:
    thumb_path = f"{sender}.jpg"
    if os.path.exists(thumb_path):
        return thumb_path
    return None

def hhmmss(seconds: int) -> str:
    return time.strftime('%H:%M:%S', time.gmtime(seconds))

def extract_topic_id(L: str) -> int | None:
    if not L:
        return None
    text = L.strip()
    m = re.search(r'(?:https?://)?(?:t\.me|telegram\.me)/c/\d+/(\d+)/\d+', text)
    if m:
        return int(m.group(1))
    return None

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
    try:
        uid = int(user_id)
        await users_collection.update_one(
            {"$or": [{"user_id": uid}, {"user_id": str(user_id)}]},
            {"$set": {key: value, "user_id": uid}},
            upsert=True
        )
    except Exception as e:
        logger.error(f"Error saving user data: {e}")

async def get_user_data_key(user_id: int, key: str, default=None):
    try:
        uid = int(user_id)
        user_data = await users_collection.find_one({"$or": [{"user_id": uid}, {"user_id": str(user_id)}]})
        return user_data.get(key, default) if user_data else default
    except Exception as e:
        return default

async def get_user_data(user_id: int):
    try:
        uid = int(user_id)
        return await users_collection.find_one({"$or": [{"user_id": uid}, {"user_id": str(user_id)}]})
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
        uid = int(user_id)
        update_data = {
            "session_string": session_string,
            "updated_at": datetime.now(),
            "user_id": uid
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
            {"$or": [{"user_id": uid}, {"user_id": str(user_id)}]},
            {"$set": update_data},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error saving session: {e}")
        return False

async def cleanup_user_all_dbs(user_id: int):
    """
    Completely cleans up user documents, settings, temporary data and cached records
    across all 3 MongoDB clusters to keep databases lightweight and free of junk.
    """
    try:
        uid = int(user_id)
        # Cluster 2: Unset settings and personal data
        await users_collection.update_many(
            {"$or": [{"user_id": uid}, {"user_id": str(user_id)}]},
            {"$unset": {
                "session_string": "",
                "two_factor": "",
                "phone": "",
                "first_name": "",
                "last_name": "",
                "username": "",
                "account_id": "",
                "login_type": "",
                "delete_words": "",
                "replacement_words": "",
                "rename_tag": "",
                "caption": "",
                "chat_id": "",
                "cached_peers": ""
            }}
        )
    except Exception as e:
        logger.debug(f"Cluster 2 cleanup: {e}")

    try:
        uid = int(user_id)
        # Cluster 3: Delete cached peers or user records
        await cached_peers_collection.delete_many({"$or": [{"user_id": uid}, {"user_id": str(uid)}]})
        await statistics_collection.delete_many({"$or": [{"user_id": uid}, {"user_id": str(uid)}]})
    except Exception as e:
        logger.debug(f"Cluster 3 cleanup: {e}")

    try:
        uid = int(user_id)
        # Cluster 1: Clean legacy peer/temp collections if any
        await db["cached_peers"].delete_many({"$or": [{"user_id": uid}, {"user_id": str(uid)}]})
    except Exception as e:
        logger.debug(f"Cluster 1 cleanup: {e}")

async def init_database_auto_cleanup():
    """
    Sets up MongoDB TTL indexes on all clusters for automatic deletion of old statistics,
    temporary logs, and expired peers so 512MB limits are never exceeded.
    """
    try:
        # Cluster 3: Auto-delete statistics older than 7 days
        await statistics_collection.create_index("created_at", expireAfterSeconds=604800)
    except Exception as e:
        logger.debug(f"TTL index stats note: {e}")

    try:
        # Cluster 3: Auto-delete cached peers un-updated for 30 days
        await cached_peers_collection.create_index("updated_at", expireAfterSeconds=2592000)
    except Exception as e:
        logger.debug(f"TTL index peers note: {e}")

async def remove_user_session(user_id: int) -> bool:
    try:
        uid = int(user_id)
        await cleanup_user_all_dbs(uid)
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

def strip_markdown_link(text: str) -> str:
    """
    Strips markdown [anchor](url) and HTML <a href="...">anchor</a> links,
    returning only the clean anchor text.
    """
    if not text:
        return ""
    cleaned = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', str(text))
    cleaned = re.sub(r'<a\s+[^>]*href=["\'][^"\']*["\'][^>]*>(.*?)</a>', r'\1', cleaned, flags=re.IGNORECASE)
    return cleaned.strip('\'"` ')

def extract_message_markdown(message) -> str:
    """
    Extracts text or caption from Pyrogram message preserving markdown syntax and hyperlinks.
    """
    if not message:
        return ""
    text_obj = getattr(message, 'caption', None) or getattr(message, 'text', None) or ""
    entities = getattr(message, 'caption_entities', None) or getattr(message, 'entities', None)
    if text_obj and entities:
        try:
            from pyrogram.parser import Parser
            return Parser.unparse(str(text_obj), entities, is_html=False)
        except Exception:
            pass
    if hasattr(text_obj, 'markdown') and text_obj.markdown:
        return str(text_obj.markdown)
    return str(text_obj or "")

def clean_chat_id_input(text: str) -> str | None:
    """
    Cleans and standardizes user-provided target chat/channel ID:
    - -1001234567890
    - -1001234567890/123 (with topic)
    - 1001234567890 -> -1001234567890
    - @username
    - https://t.me/username -> @username
    - https://t.me/c/1234567890/123 -> -1001234567890/123
    - chatid: -100...
    """
    if not text:
        return None
    raw = str(text).strip()
    raw = re.sub(r'^(?:/(?:setchatid|chatid|setchannel|channel|target|settarget)|chatid|chat_id|chat\s*id|target|channel)\s*[:=]?\s*', '', raw, flags=re.IGNORECASE).strip()

    c_match = re.search(r't\.me/c/(\d+)(?:/(\d+))?(?:/(\d+))?', raw)
    if c_match:
        cid = f"-100{c_match.group(1)}"
        if c_match.group(3):
            # t.me/c/1234567890/10/55 -> group(2) is topic, group(3) is message
            return f"{cid}/{c_match.group(2)}"
        return cid

    tme_match = re.search(r't\.me/([a-zA-Z0-9_]{4,})', raw)
    if tme_match and tme_match.group(1).lower() not in ['c', 'joinchat', 'addstickers', 's']:
        return f"@{tme_match.group(1)}"

    if re.match(r"^@[a-zA-Z0-9_]{4,}$", raw):
        return raw

    if re.match(r"^(-?\d+)(/\d+)?$", raw):
        if raw.startswith("100") and len(raw) >= 10:
            return f"-{raw}"
        return raw

    if re.match(r"^(\d{9,12})(/\d+)?$", raw):
        parts = raw.split('/', 1)
        base = f"-100{parts[0]}"
        return f"{base}/{parts[1]}" if len(parts) > 1 else base

    return None

def parse_delete_words(text: str) -> list[str]:
    """
    Parses delete word candidates from user input:
    - Strips prefixes like /deleteword, /delete, /del, delete:, del:
    - Splits by commas, newlines, or whitespace
    - Handles single or double quotes
    """
    if not text:
        return []
    raw = str(text).strip()
    raw = re.sub(r'^(?:/(?:deleteword|deletewords|delete|delword|del|remword)|delete:|del:)\s*', '', raw, flags=re.IGNORECASE).strip()
    raw = re.sub(r'[,;\n]+', ' ', raw)
    words = []
    for w in raw.split():
        clean = w.strip("'\"," )
        if clean and clean.lower() not in ['delete', 'del', 'deleteword', 'deletewords']:
            words.append(clean)
    return list(dict.fromkeys(words))

def parse_replacement_rules(text: str) -> list[tuple[str, str]]:
    """
    Parses word replacement pairs from user input supporting:
    - 'word1' '[word2](https://link.com)' (inline links via Telegram 'Create Link')
    - 'word1' [word2](https://link.com)
    - 'word1' ['word2'](https://link.com)
    - 'old' 'new' or "old" "new"
    - Smart/curly quotes: ‘old’ ‘new’, “old” “new”, `old` `new`
    - Separator/arrow styles: old -> new, old ➔ new, old => new, old = new
    - Plain 2-word format: old new
    - Supports leading commands like /replace, /setreplacement, replace:
    """
    if not text:
        return []
        
    normalized = str(text).strip()
    for q in ['‘', '’', '‚', '‛', '`', '´']:
        normalized = normalized.replace(q, "'")
    for q in ['“', '”', '„', '‟', '«', '»']:
        normalized = normalized.replace(q, '"')

    token_pattern = re.compile(
        r"""['"]\[([^\]]+)\]\(([^)]+)\)['"]|"""          # '[anchor](url)' or "[anchor](url)"
        r"""\[\s*['"]?([^\]'"]+)['"]?\s*\]\(([^)]+)\)|""" # [anchor](url) or ['anchor'](url)
        r"""['"]([^'"]+)['"]|"""                          # 'plain text' or "plain text"
        r"""(\S+)"""                                      # raw_word
    )

    rules = []
    for line in normalized.splitlines():
        line = line.strip()
        if not line:
            continue

        # Strip command prefixes like /setreplacement, /replace, replace:, replace
        line = re.sub(r'^(?:/(?:setreplacement|setreplace|replace|replaceword)|replace:|replace\s+)\s*', '', line, flags=re.IGNORECASE).strip()
        if not line:
            continue

        # Check delimiter-based format (->, ➔, =>, =) first
        sep_match = re.split(r'\s*(?:->|➔|=>|=)\s*', line, maxsplit=1)
        if len(sep_match) == 2 and sep_match[0].strip() and sep_match[1].strip():
            old_w = sep_match[0].strip().strip('\'"`')
            new_w = sep_match[1].strip()
            if (new_w.startswith("'") and new_w.endswith("'")) or (new_w.startswith('"') and new_w.endswith('"')):
                new_w = new_w[1:-1].strip()
            new_w = re.sub(r'\[\s*[\'"]([^\'\]]+)[\'"]\s*\]\(([^)]+)\)', r'[\1](\2)', new_w)
            if old_w:
                rules.append((old_w, new_w))
                continue

        # Extract tokens directly
        tokens = []
        for m in token_pattern.finditer(line):
            if m.group(1) is not None:
                tokens.append(f"[{m.group(1).strip()}]({m.group(2).strip()})")
            elif m.group(3) is not None:
                tokens.append(f"[{m.group(3).strip()}]({m.group(4).strip()})")
            elif m.group(5) is not None:
                val = m.group(5).strip()
                link_m = re.match(r'^\[\s*[\'"]?([^\]\'"]+)[\'"]?\s*\]\(([^)]+)\)$', val)
                if link_m:
                    tokens.append(f"[{link_m.group(1).strip()}]({link_m.group(2).strip()})")
                else:
                    tokens.append(val)
            elif m.group(6) is not None:
                tokens.append(m.group(6).strip())

        if len(tokens) >= 2:
            old_w = tokens[0].strip('\'"` ')
            new_w = tokens[1].strip()
            if (new_w.startswith("'") and new_w.endswith("'")) or (new_w.startswith('"') and new_w.endswith('"')):
                new_w = new_w[1:-1].strip()
            if old_w:
                rules.append((old_w, new_w))

    return rules

LINK_REGEX = re.compile(r'\[([^\]]+)\]\((https?://[^\s)]+|tg://[^\s)]+|[^\s)]+)\)')

def apply_single_replacement(text: str, old_word: str, new_replacement: str) -> str:
    """
    Safely replaces occurrences of old_word with new_replacement.
    Handles both plain text and markdown links without corrupting syntax:
    - If old_word had a link in the source, it updates the link URL or anchor cleanly.
    - If old_word was plain, it becomes new_replacement (with link if specified).
    - If old_word was a full markdown link, it replaces cleanly.
    - Prevents double brackets or broken URLs.
    """
    if not text or not old_word:
        return text

    # Check if new_replacement is a markdown link [anchor](url)
    link_match = re.match(r'^\[([^\]]+)\]\(([^)]+)\)$', new_replacement.strip())
    is_new_link = bool(link_match)
    if is_new_link:
        new_anchor, new_url = link_match.groups()
    else:
        new_anchor, new_url = new_replacement, None

    # Check if old_word is itself a markdown link [old_anchor](old_url)
    if old_word.strip().startswith('[') and '](' in old_word and old_word.strip().endswith(')'):
        pattern = re.compile(re.escape(old_word.strip()), re.IGNORECASE)
        if pattern.search(text):
            return pattern.sub(new_replacement, text)

    old_pattern = re.compile(re.escape(old_word), re.IGNORECASE)

    result = []
    last_end = 0

    for m in LINK_REGEX.finditer(text):
        start, end = m.span()
        # 1. Process non-link text preceding this link
        non_link_part = text[last_end:start]
        if non_link_part:
            non_link_part = old_pattern.sub(lambda _: new_replacement, non_link_part)
            result.append(non_link_part)

        # 2. Process link segment
        anchor = m.group(1)
        url = m.group(2)
        if old_pattern.search(anchor):
            if is_new_link:
                # If anchor was solely the old word, replace whole link
                if anchor.strip().lower() == old_word.strip().lower():
                    result.append(f"[{new_anchor}]({new_url})")
                else:
                    updated_anchor = old_pattern.sub(lambda _: new_anchor, anchor)
                    result.append(f"[{updated_anchor}]({new_url})")
            else:
                updated_anchor = old_pattern.sub(lambda _: new_replacement, anchor)
                result.append(f"[{updated_anchor}]({url})")
        elif old_pattern.search(url):
            if is_new_link:
                result.append(f"[{new_anchor}]({new_url})")
            else:
                updated_url = old_pattern.sub(lambda _: new_replacement, url)
                result.append(f"[{anchor}]({updated_url})")
        else:
            result.append(m.group(0))

        last_end = end

    # 3. Process remaining tail text
    tail = text[last_end:]
    if tail:
        tail = old_pattern.sub(lambda _: new_replacement, tail)
        result.append(tail)

    res = ''.join(result)
    # Fix any accidental double brackets like [[text](url)](url)
    res = re.sub(r'\[\s*\[([^\]]+)\]\(([^)]+)\)\s*\]\([^)]+\)', r'[\1](\2)', res)
    return res

def apply_single_delete(text: str, word_to_delete: str) -> str:
    """
    Safely deletes word_to_delete from text and markdown links without leaving
    broken markdown syntax or empty brackets.
    """
    if not text or not word_to_delete:
        return text

    del_pattern = re.compile(re.escape(word_to_delete), re.IGNORECASE)
    result = []
    last_end = 0

    for m in LINK_REGEX.finditer(text):
        start, end = m.span()
        non_link = text[last_end:start]
        if non_link:
            result.append(del_pattern.sub('', non_link))

        anchor = m.group(1)
        url = m.group(2)
        if anchor.strip().lower() == word_to_delete.strip().lower():
            # If the entire link anchor was this word, drop the link completely
            pass
        elif del_pattern.search(anchor):
            new_anchor = del_pattern.sub('', anchor).strip()
            if new_anchor:
                result.append(f"[{new_anchor}]({url})")
        elif del_pattern.search(url):
            # If deleted word was in URL, drop link or keep anchor as plain text
            result.append(anchor)
        else:
            result.append(m.group(0))

        last_end = end

    tail = text[last_end:]
    if tail:
        result.append(del_pattern.sub('', tail))

    res = ''.join(result)
    res = re.sub(r'\[\s*\]\([^)]+\)', '', res)
    return res

async def process_text_with_rules(user_id: int, text: str) -> str:
    if not text:
        return ""
    try:
        replacements = await get_user_data_key(int(user_id), "replacement_words", {}) or {}
        delete_words = await get_user_data_key(int(user_id), "delete_words", []) or []
        
        processed_text = str(text)
        
        # Apply word replacements (link-aware, case-insensitive)
        for word, replacement in replacements.items():
            if not word:
                continue
            rep_str = str(replacement or '')
            try:
                processed_text = apply_single_replacement(processed_text, word, rep_str)
            except Exception as e:
                logger.error(f"Error replacing '{word}': {e}")
                processed_text = processed_text.replace(word, rep_str)
        
        # Apply delete words (link-aware, case-insensitive)
        for word in delete_words:
            if not word:
                continue
            try:
                processed_text = apply_single_delete(processed_text, word)
            except Exception as e:
                logger.error(f"Error deleting '{word}': {e}")
                processed_text = processed_text.replace(word, "")
                
        # Clean consecutive spaces while preserving line structure
        lines = [re.sub(r'[ \t]+', ' ', l).strip() for l in processed_text.splitlines()]
        return '\n'.join(lines).strip()
    except Exception as e:
        logger.error(f"Error in process_text_with_rules: {e}")
        return text

async def screenshot(video: str, duration: int, sender: str) -> str | None:
    os.makedirs(THUMB_DIR, exist_ok=True)
    existing_screenshot = f"{sender}.jpg"
    if os.path.exists(existing_screenshot):
        try:
            with Image.open(existing_screenshot) as img:
                img.thumbnail((1280, 720))
                thumb_out = os.path.join(THUMB_DIR, f"thumb_{sender}_{int(time.time()*1000)}.jpg")
                img.convert('RGB').save(thumb_out, "JPEG", quality=85)
                return thumb_out
        except Exception:
            return existing_screenshot

    try:
        output_file = os.path.join(THUMB_DIR, f"temp_thumb_{sender}_{int(time.time()*1000)}.jpg")
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

def cleanup_temp_thumb(th: str | None) -> None:
    """
    Safely deletes temporary thumbnails.
    NEVER deletes user's permanent custom thumbnail ({user_id}.jpg) or DEFAULT_THUMB.
    """
    if not th or not isinstance(th, str) or not os.path.exists(th):
        return
    base = os.path.basename(th)
    # Never delete user's permanent custom thumbnail (e.g. 12345678.jpg) or default thumbnail
    if re.match(r"^\d+\.jpg$", base) or base == DEFAULT_THUMB:
        return
    # Delete if it's a generated temporary thumbnail
    try:
        os.remove(th)
    except Exception:
        pass

def clean_stale_thumbnails(max_age_seconds: int = 300) -> int:
    """
    Cleans up all temporary thumbnail files from THUMB_DIR (thumbnails/)
    and any legacy temp_thumb_*.jpg files in the root server directory.
    NEVER touches permanent user custom thumbnails ({user_id}.jpg) or DEFAULT_THUMB.
    """
    deleted_count = 0
    now = time.time()
    
    # 1. Purge temp files in THUMB_DIR (thumbnails/)
    if os.path.exists(THUMB_DIR):
        for fname in os.listdir(THUMB_DIR):
            fpath = os.path.join(THUMB_DIR, fname)
            if not os.path.isfile(fpath):
                continue
            if re.match(r"^\d+\.jpg$", fname) or fname == DEFAULT_THUMB:
                continue
            try:
                mtime = os.path.getmtime(fpath)
                if (now - mtime) >= max_age_seconds:
                    os.remove(fpath)
                    deleted_count += 1
            except Exception:
                pass
                
    # 2. Purge legacy temp_thumb_*.jpg or thumb_*_*.jpg from root server directory
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        for fname in os.listdir(root_dir):
            if (fname.startswith("temp_thumb_") or (fname.startswith("thumb_") and "_" in fname)) and fname.endswith(".jpg"):
                fpath = os.path.join(root_dir, fname)
                if os.path.isfile(fpath):
                    try:
                        mtime = os.path.getmtime(fpath)
                        if (now - mtime) >= max_age_seconds:
                            os.remove(fpath)
                            deleted_count += 1
                    except Exception:
                        pass
    except Exception:
        pass
        
    return deleted_count

async def auto_clean_thumbnails_loop():
    """Background task to periodically clean up temporary thumbnails."""
    while True:
        try:
            clean_stale_thumbnails(max_age_seconds=180)
        except Exception:
            pass
        await asyncio.sleep(300)

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
        from config import OWNER_ID
        uid = int(user_id)
        if isinstance(OWNER_ID, list):
            if uid in OWNER_ID or str(uid) in [str(x) for x in OWNER_ID]:
                return True
        elif str(uid) == str(OWNER_ID):
            return True

        user = await premium_users_collection.find_one({"$or": [{"user_id": uid}, {"user_id": str(uid)}]})
        if user and "subscription_end" in user:
            now = datetime.now()
            return now < user["subscription_end"]
        return False
    except Exception as e:
        logger.error(f"Error checking premium status: {e}")
        return False

async def get_premium_details(user_id: int):
    try:
        uid = int(user_id)
        user = await premium_users_collection.find_one({"$or": [{"user_id": uid}, {"user_id": str(uid)}]})
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

async def can_user_extract(user_id: int) -> tuple[bool, str]:
    """
    Check if user can extract a file.
    Premium users (Basic or Pro) or Owner can extract unlimited files 24*7.
    Free users can only extract 1 file per 24 hours (public or private).
    Trial is not consumed until they actually extract a file.
    """
    try:
        from config import OWNER_ID
        uid = int(user_id)
        if isinstance(OWNER_ID, list):
            if uid in OWNER_ID or str(uid) in [str(x) for x in OWNER_ID]:
                return True, "owner"
        elif str(uid) == str(OWNER_ID):
            return True, "owner"

        if await is_premium_user(uid):
            return True, "premium"

        user_data = await users_collection.find_one({"$or": [{"user_id": uid}, {"user_id": str(uid)}]})
        last_time = None
        if user_data:
            last_time = user_data.get("last_free_extract_time")
            # fallback to legacy date string if present
            if not last_time and user_data.get("free_extract_date"):
                today_str = datetime.now().strftime("%Y-%m-%d")
                if user_data.get("free_extract_date") == today_str and user_data.get("free_extract_count", 0) >= 1:
                    last_time = datetime.now()

        if last_time:
            now = datetime.now()
            if isinstance(last_time, str):
                try:
                    last_time = datetime.fromisoformat(last_time)
                except Exception:
                    last_time = now
            diff = now - last_time
            if diff.total_seconds() < 24 * 3600:
                remaining_sec = int(24 * 3600 - diff.total_seconds())
                hours = remaining_sec // 3600
                minutes = (remaining_sec % 3600) // 60
                time_left_str = f"{hours} घंटे {minutes} मिनट" if hours > 0 else f"{minutes} मिनट"
                msg = (
                    "⚠️ **प्रीमियम आवश्यक (Daily Free Limit Reached)** ⚠️\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "आप एक **फ़्री यूज़र** हैं। आप 24 घंटे में केवल **1 मुफ़्त फ़ाइल** (पब्लिक या प्राइवेट) निकाल सकते हैं।\n\n"
                    f"⏳ **अगली फ़्री फ़ाइल:** `{time_left_str}` बाद निकाल सकेंगे।\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "💎 **24*7 असीमित (Unlimited) फ़ाइल्स निकालने के लिए:**\n"
                    "• बेसिक या प्रो प्रीमियम प्लान लें और बिना किसी लिमिट के कभी भी अनगिनत फ़ाइलें निकालें!\n\n"
                    "👉 **प्लान्स व अपग्रेड के लिए:** `/plan`"
                )
                return False, msg

        return True, "free"
    except Exception as e:
        logger.error(f"Error checking user extract limit: {e}")
        return True, "error_fallback"

async def record_user_extraction(user_id: int):
    """
    Record an extraction.
    Only when a file is actually extracted successfully does this consume the free extraction.
    """
    try:
        uid = int(user_id)
        if await is_premium_user(uid):
            await users_collection.update_one(
                {"$or": [{"user_id": uid}, {"user_id": str(uid)}]},
                {"$inc": {"used_files": 1}},
                upsert=True
            )
            return

        now = datetime.now()
        await users_collection.update_one(
            {"$or": [{"user_id": uid}, {"user_id": str(uid)}]},
            {
                "$set": {
                    "last_free_extract_time": now,
                    "free_extract_date": now.strftime("%Y-%m-%d"),
                    "free_extract_count": 1
                },
                "$inc": {"used_files": 1}
            },
            upsert=True
        )
    except Exception as e:
        logger.error(f"Error recording user extraction: {e}")

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
