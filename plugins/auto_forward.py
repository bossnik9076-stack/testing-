# Copyright (c) 2025 devgagan : https://github.com/devgaganin.
# Licensed under the GNU General Public License v3.0.
# See LICENSE file in the repository root for full license text.

import os
import re
import time
import math
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from pyrogram import Client, filters, enums
from pyrogram.enums import ParseMode
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)
from pyrogram.errors import FloodWait, MessageNotModified, RPCError

from shared_client import app, userbot
from config import LOG_GROUP, OWNER_ID
from utils.func import (
    get_user_data, is_premium_user, send_to_log_group,
    get_user_data_key, save_user_data, process_text_with_rules,
    users_collection, db
)
from plugins.start import subscribe as sub, get_main_menu_keyboard

try:
    import pyrogram.utils
    pyrogram.utils.MIN_CHANNEL_ID = -100999999999999
except Exception:
    pass

logger = logging.getLogger(__name__)

# MongoDB collections
live_forward_col = db["live_auto_forwards"]
auto_fwd_settings_col = db["auto_fwd_user_configs"]

# In-memory session tracking for single-step text inputs (like entering Source, Target, Range)
# user_id -> dict
FWD_SESSIONS: Dict[int, Dict[str, Any]] = {}

# Active batch forward tasks: user_id -> dict
ACTIVE_FWD_TASKS: Dict[int, Dict[str, Any]] = {}

# Active live listener Pyrogram client handler references: rule_id -> (client, handler_instance)
ACTIVE_LIVE_HANDLERS: Dict[str, Any] = {}


def get_channel_id_from_link(link_or_text: str):
    """
    Parses channel username or integer ID and message ID from standard Telegram link.
    Supports:
    - https://t.me/c/1234567890/456 -> (-1001234567890, 456)
    - https://t.me/username/456 -> ('username', 456)
    - -1001234567890 -> (-1001234567890, None)
    - @username -> ('username', None)
    - username -> ('username', None)
    - 1234567890 -> (-1001234567890, None)
    """
    text = link_or_text.strip().replace("?single", "")
    priv_match = re.match(r"(?:https?://)?(?:t\.me|telegram\.me)/c/(\d+)(?:/(\d+))?", text)
    if priv_match:
        c_id = int(f"-100{priv_match.group(1)}")
        m_id = int(priv_match.group(2)) if priv_match.group(2) else None
        return c_id, m_id

    pub_match = re.match(r"(?:https?://)?(?:t\.me|telegram\.me)/([a-zA-Z0-9_]+)(?:/(\d+))?", text)
    if pub_match:
        uname = pub_match.group(1)
        m_id = int(pub_match.group(2)) if pub_match.group(2) else None
        if uname.lower() not in ["joinchat", "addlist", "share"]:
            return uname, m_id

    if text.startswith("-100") and text[4:].isdigit():
        return int(text), None
    if text.startswith("-") and text[1:].isdigit():
        return int(f"-100{text[1:]}"), None
    if text.isdigit():
        return int(f"-100{text}"), None
    if text.startswith("@"):
        return text[1:], None
    if re.match(r"^[a-zA-Z0-9_]{4,}$", text):
        return text, None

    return None, None


def TimeFormatter(milliseconds: int) -> str:
    seconds, milliseconds = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    tmp = (
        ((str(days) + "d, ") if days else "") +
        ((str(hours) + "h, ") if hours else "") +
        ((str(minutes) + "m, ") if minutes else "") +
        ((str(seconds) + "s, ") if seconds else "")
    )
    return tmp[:-2] if tmp else "0s"


def make_fwd_progress_text(fetched: int, forwarded: int, total: int, status: str, eta_str: str) -> str:
    pct = math.floor((forwarded / max(total, 1)) * 100)
    pct = min(100, max(0, pct))
    bar_done = math.floor(pct / 10)
    bar_left = 10 - bar_done
    bar = "●" * bar_done + "○" * bar_left

    return (
        f"🚀 **ऑटो फॉरवर्डिंग चालू है (Auto Forward In Progress)**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **प्रगति (Progress):** `[{bar}]` **{pct}%**\n"
        f"🔄 **कुल जाँची गई (Fetched):** `{fetched}`\n"
        f"✅ **फॉरवर्ड हुई (Forwarded):** `{forwarded} / {total}`\n"
        f"⏳ **अनुमानित समय (ETA):** `{eta_str}`\n"
        f"📌 **स्थिति:** `{status}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 *आप कभी भी नीचे दिए गए बटन से प्रोसेस रोक सकते हैं।*"
    )


# -------------------------------------------------------------
# User Auto-Forward Settings Storage & Helpers
# -------------------------------------------------------------

async def get_fwd_config(user_id: int) -> dict:
    doc = await auto_fwd_settings_col.find_one({"user_id": int(user_id)})
    if not doc:
        doc = {
            "user_id": int(user_id),
            "source_chat": None,
            "target_chat": None,
            "forward_tag": False,
            "protect_content": False,
            "apply_custom_caption": True,
            "apply_word_rules": True
        }
    return doc


async def update_fwd_config(user_id: int, updates: dict):
    await auto_fwd_settings_col.update_one(
        {"user_id": int(user_id)},
        {"$set": updates},
        upsert=True
    )


# -------------------------------------------------------------
# Core Message Processing & Forwarding (Superfast: No Thumbnail overhead)
# -------------------------------------------------------------

async def extract_and_format_caption(user_id: int, message: Message, client: Client = None, cfg: dict = None) -> Optional[str]:
    """
    Applies custom settings based on user configuration:
    - Word replacement & deletion rules (if apply_word_rules is enabled)
    - Custom user caption (if apply_custom_caption is enabled)
    """
    if cfg is None:
        cfg = await get_fwd_config(user_id)

    orig_text = ""
    if hasattr(message, 'caption') and message.caption:
        if hasattr(message.caption, 'markdown') and message.caption.markdown:
            orig_text = str(message.caption.markdown)
        elif getattr(message, 'caption_entities', None) and client and hasattr(client, 'parser'):
            try:
                orig_text = client.parser.unparse(str(message.caption), message.caption_entities, is_html=False)
            except Exception:
                orig_text = str(message.caption)
        else:
            orig_text = str(message.caption)
    elif hasattr(message, 'text') and message.text:
        if hasattr(message.text, 'markdown') and message.text.markdown:
            orig_text = str(message.text.markdown)
        elif getattr(message, 'entities', None) and client and hasattr(client, 'parser'):
            try:
                orig_text = client.parser.unparse(str(message.text), message.entities, is_html=False)
            except Exception:
                orig_text = str(message.text)
        else:
            orig_text = str(message.text)

    # 1. Apply word replacements & deletions if enabled
    if cfg.get("apply_word_rules", True):
        proc_text = await process_text_with_rules(user_id, orig_text)
    else:
        proc_text = orig_text

    # 2. Append custom caption if enabled
    user_cap = ""
    if cfg.get("apply_custom_caption", True):
        user_cap = await get_user_data_key(user_id, 'caption', '') or ''

    if proc_text and user_cap:
        return f"{proc_text}\n\n{user_cap}".strip()
    return (user_cap or proc_text or None)


async def send_processed_message(
    client: Client,
    user_client: Optional[Client],
    user_id: int,
    message: Message,
    to_chat: Any,
    forward_tag: bool = False,
    protect_content: bool = False,
    cfg: dict = None
) -> bool:
    """
    Sends message directly and rapidly:
    1. If forward_tag is True: Direct forward_messages (zero re-upload).
    2. Otherwise: Fast copy_message with custom processed caption (Zero re-upload & zero download overhead).
    3. Fallback only if copy is restricted (copy-protection): download and upload directly without thumbnail lag.
    """
    if not message or getattr(message, "empty", False) or getattr(message, "service", False):
        return False

    formatted_caption = await extract_and_format_caption(user_id, message, client, cfg)
    sender = user_client if user_client else client

    # 1. Forward Tag mode (Raw forward)
    if forward_tag:
        try:
            await sender.forward_messages(
                chat_id=to_chat,
                from_chat_id=message.chat.id,
                message_ids=message.id,
                protect_content=protect_content
            )
            return True
        except FloodWait as fw:
            await asyncio.sleep(fw.value)
            try:
                await sender.forward_messages(
                    chat_id=to_chat,
                    from_chat_id=message.chat.id,
                    message_ids=message.id,
                    protect_content=protect_content
                )
                return True
            except Exception:
                pass
        except Exception as fwd_err:
            logger.debug(f"Direct forward failed ({fwd_err}), falling back to copy.")

    # 2. Clean Copy mode (Instant copy with custom processed caption)
    send_caption = formatted_caption if formatted_caption else (message.caption or None)

    # 2A. Text-only message
    if not message.media:
        text_content = formatted_caption if formatted_caption else (message.text or "")
        if not text_content:
            return False
        for send_c in [client, user_client]:
            if not send_c:
                continue
            try:
                await send_c.send_message(
                    chat_id=to_chat,
                    text=text_content,
                    parse_mode=ParseMode.MARKDOWN,
                    protect_content=protect_content
                )
                return True
            except Exception:
                try:
                    await send_c.send_message(
                        chat_id=to_chat,
                        text=text_content,
                        protect_content=protect_content
                    )
                    return True
                except Exception:
                    pass
        return False

    # 2B. Media message: Instant copy_message
    for send_c in [client, user_client]:
        if not send_c:
            continue
        try:
            if send_caption:
                try:
                    await send_c.copy_message(
                        chat_id=to_chat,
                        from_chat_id=message.chat.id,
                        message_id=message.id,
                        caption=send_caption,
                        parse_mode=ParseMode.MARKDOWN,
                        protect_content=protect_content
                    )
                    return True
                except Exception:
                    await send_c.copy_message(
                        chat_id=to_chat,
                        from_chat_id=message.chat.id,
                        message_id=message.id,
                        caption=send_caption,
                        protect_content=protect_content
                    )
                    return True
            else:
                await send_c.copy_message(
                    chat_id=to_chat,
                    from_chat_id=message.chat.id,
                    message_id=message.id,
                    protect_content=protect_content
                )
                return True
        except FloodWait as fw:
            await asyncio.sleep(fw.value)
            try:
                await send_c.copy_message(
                    chat_id=to_chat,
                    from_chat_id=message.chat.id,
                    message_id=message.id,
                    caption=send_caption if send_caption else None,
                    protect_content=protect_content
                )
                return True
            except Exception:
                pass
        except Exception as copy_err:
            logger.debug(f"copy_message failed ({copy_err})")

    # 2C. Fallback for restricted channels (No thumbnail modification overhead)
    dl_client = user_client if user_client else client
    temp_file = None
    try:
        raw_name = f"fwd_{int(time.time()*1000)}"
        if message.video and message.video.file_name:
            raw_name = message.video.file_name
        elif message.document and message.document.file_name:
            raw_name = message.document.file_name
        elif message.audio and message.audio.file_name:
            raw_name = message.audio.file_name
        elif message.photo:
            raw_name = f"{raw_name}.jpg"

        temp_file = await dl_client.download_media(message, file_name=raw_name)
        if not temp_file or not os.path.exists(temp_file):
            return False

        up_client = client or user_client
        sent = None

        if message.video:
            sent = await up_client.send_video(
                chat_id=to_chat,
                video=temp_file,
                caption=send_caption,
                duration=message.video.duration,
                width=message.video.width,
                height=message.video.height,
                parse_mode=ParseMode.MARKDOWN,
                protect_content=protect_content
            )
        elif message.audio:
            sent = await up_client.send_audio(
                chat_id=to_chat,
                audio=temp_file,
                caption=send_caption,
                duration=message.audio.duration,
                performer=message.audio.performer,
                title=message.audio.title,
                parse_mode=ParseMode.MARKDOWN,
                protect_content=protect_content
            )
        elif message.photo:
            sent = await up_client.send_photo(
                chat_id=to_chat,
                photo=temp_file,
                caption=send_caption,
                parse_mode=ParseMode.MARKDOWN,
                protect_content=protect_content
            )
        elif message.voice:
            sent = await up_client.send_voice(
                chat_id=to_chat,
                voice=temp_file,
                caption=send_caption,
                duration=message.voice.duration,
                protect_content=protect_content
            )
        elif message.video_note:
            sent = await up_client.send_video_note(
                chat_id=to_chat,
                video_note=temp_file,
                duration=message.video_note.duration,
                length=message.video_note.length,
                protect_content=protect_content
            )
        else:
            sent = await up_client.send_document(
                chat_id=to_chat,
                document=temp_file,
                caption=send_caption,
                file_name=os.path.basename(temp_file),
                parse_mode=ParseMode.MARKDOWN,
                protect_content=protect_content
            )
        return bool(sent)

    except Exception as up_err:
        logger.error(f"Fallback download/upload failed: {up_err}")
        return False
    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass


# -------------------------------------------------------------
# Batch Forwarding Worker (Historical Message Range)
# -------------------------------------------------------------

async def run_forwarding_worker(client: Client, user_client, user_id: int, status_msg: Message, task_data: dict):
    from_chat = task_data["from_chat"]
    to_chat = task_data["to_chat"]
    start_id = task_data["start_id"]
    end_id = task_data["end_id"]
    forward_tag = task_data.get("forward_tag", False)
    protect = task_data.get("protect", False)
    cfg = task_data.get("cfg")

    total_msgs = max(1, end_id - start_id + 1)
    fetched = 0
    forwarded = 0
    start_time = time.time()
    last_ui_update = 0

    cancel_btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 प्रक्रिया रोकें (Cancel Task)", callback_data=f"fwd_cancel_{user_id}")]
    ])

    try:
        curr_id = start_id
        while curr_id <= end_id:
            if user_id not in ACTIVE_FWD_TASKS or ACTIVE_FWD_TASKS[user_id].get("cancel_requested"):
                break

            fetched += 1
            msg_to_send = None

            # Fetch message
            fetch_client = user_client if user_client else client
            try:
                msg_to_send = await fetch_client.get_messages(from_chat, curr_id)
            except FloodWait as fw:
                await asyncio.sleep(fw.value)
                continue
            except Exception as e:
                logger.debug(f"Error fetching msg {curr_id}: {e}")

            if msg_to_send and not msg_to_send.empty and not msg_to_send.service:
                success = await send_processed_message(
                    client=client,
                    user_client=user_client,
                    user_id=user_id,
                    message=msg_to_send,
                    to_chat=to_chat,
                    forward_tag=forward_tag,
                    protect_content=protect,
                    cfg=cfg
                )
                if success:
                    forwarded += 1

                await asyncio.sleep(0.8 if user_client else 0.4)

            curr_id += 1

            # Update UI periodically
            now = time.time()
            if (now - last_ui_update) >= 5 or curr_id > end_id:
                elapsed = max(1, now - start_time)
                speed = forwarded / elapsed if elapsed > 0 else 1
                remaining_items = max(0, total_msgs - fetched)
                eta_ms = (remaining_items / speed * 1000) if speed > 0 else 0
                eta_str = TimeFormatter(eta_ms)

                progress_text = make_fwd_progress_text(
                    fetched=fetched,
                    forwarded=forwarded,
                    total=total_msgs,
                    status="फॉरवर्ड हो रहा है (Forwarding...)",
                    eta_str=eta_str
                )
                try:
                    await status_msg.edit_text(progress_text, reply_markup=cancel_btn)
                    last_ui_update = now
                except (MessageNotModified, Exception):
                    pass

        # Check final status
        is_cancelled = ACTIVE_FWD_TASKS.get(user_id, {}).get("cancel_requested", False)
        duration = TimeFormatter((time.time() - start_time) * 1000)

        if is_cancelled:
            final_text = (
                f"🛑 **ऑटो फॉरवर्डिंग रोक दी गई (Cancelled)!**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ **सफलतापूर्वक भेजे गए:** `{forwarded} / {total_msgs}`\n"
                f"⏱️ **बीता समय:** `{duration}`\n"
                f"━━━━━━━━━━━━━━━━━━━━"
            )
        else:
            final_text = (
                f"🎉 **ऑटो फॉरवर्डिंग सफलतापूर्वक पूर्ण हुई!**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ **कुल फॉरवर्ड किए गए मैसेज:** `{forwarded} / {total_msgs}`\n"
                f"⏱️ **कुल समय लगा:** `{duration}`\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🚀 आपकी फाइलें सफलतापूर्वक भेज दी गई हैं!"
            )

        home_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 ऑटो फॉरवर्ड पैनल", callback_data="btn_auto_forward")],
            [InlineKeyboardButton("🔙 मुख्य मेनू (Main Menu)", callback_data="btn_main_menu")]
        ])

        try:
            await status_msg.edit_text(final_text, reply_markup=home_kb)
        except Exception:
            await client.send_message(user_id, final_text, reply_markup=home_kb)

        if LOG_GROUP:
            try:
                await send_to_log_group(
                    f"📢 **ऑटो फॉरवर्ड रिपोर्ट (Batch Done)**\n"
                    f"👤 यूज़र ID: `{user_id}`\n"
                    f"📤 Source: `{from_chat}`\n"
                    f"📥 Target: `{to_chat}`\n"
                    f"📊 Forwarded: `{forwarded} / {total_msgs}`"
                )
            except Exception:
                pass

    except Exception as e:
        logger.error(f"Error in run_forwarding_worker: {e}")
        try:
            await status_msg.edit_text(f"❌ **फॉरवर्डिंग में त्रुटि:**\n`{e}`")
        except Exception:
            pass
    finally:
        ACTIVE_FWD_TASKS.pop(user_id, None)


# -------------------------------------------------------------
# 24/7 Real-Time Live Auto-Forward Engine
# -------------------------------------------------------------

async def handle_incoming_live_message(incoming_client: Client, message: Message, rule: dict):
    rule_id = str(rule.get("_id"))
    user_id = int(rule.get("user_id"))
    to_chat = rule.get("to_chat")
    forward_tag = rule.get("forward_tag", False)
    topic_id = rule.get("topic_id")

    if topic_id:
        msg_topic = getattr(message, "message_thread_id", None) or getattr(message, "topic_id", None)
        if msg_topic and int(msg_topic) != int(topic_id):
            return

    try:
        from plugins.batch import UC, Y
        user_client = UC.get(user_id) or (incoming_client if not getattr(incoming_client, "me", None) or not incoming_client.me.is_bot else None)

        cfg = await get_fwd_config(user_id)

        success = await send_processed_message(
            client=app,
            user_client=user_client,
            user_id=user_id,
            message=message,
            to_chat=to_chat,
            forward_tag=forward_tag,
            protect_content=False,
            cfg=cfg
        )

        if success:
            await live_forward_col.update_one(
                {"_id": rule["_id"]},
                {
                    "$inc": {"forwarded_count": 1},
                    "$set": {"last_forwarded_at": datetime.utcnow()}
                }
            )
            logger.info(f"⚡ [Live FWD] Forwarded msg {message.id} to {to_chat} for user {user_id}")
    except Exception as e:
        logger.error(f"Error handling live message {message.id} for rule {rule_id}: {e}")


def register_live_listener_hook(client: Client, rule: dict):
    rule_id = str(rule.get("_id"))
    from_chat = rule.get("from_chat")

    if rule_id in ACTIVE_LIVE_HANDLERS:
        return

    async def _live_event_handler(c: Client, msg: Message):
        matched = False
        if isinstance(from_chat, int):
            if msg.chat and msg.chat.id == from_chat:
                matched = True
        elif isinstance(from_chat, str):
            if msg.chat and ((msg.chat.username and msg.chat.username.lower() == from_chat.lower().lstrip("@")) or str(msg.chat.id) == from_chat):
                matched = True

        if matched:
            asyncio.create_task(handle_incoming_live_message(c, msg, rule))

    try:
        from pyrogram.handlers import MessageHandler
        handler_instance = MessageHandler(_live_event_handler)
        client.add_handler(handler_instance, group=10)
        ACTIVE_LIVE_HANDLERS[rule_id] = (client, handler_instance)
        logger.info(f"✅ Registered Live Listener for {from_chat} (Rule {rule_id})")
    except Exception as e:
        logger.error(f"Failed to register live listener: {e}")


def unregister_live_listener_hook(rule_id: str):
    if rule_id in ACTIVE_LIVE_HANDLERS:
        try:
            client, handler_instance = ACTIVE_LIVE_HANDLERS.pop(rule_id)
            client.remove_handler(handler_instance, group=10)
            logger.info(f"🛑 Unregistered Live Listener {rule_id}")
        except Exception as e:
            logger.warning(f"Error unregistering live hook {rule_id}: {e}")


async def sync_live_listeners_for_client(client: Client, user_id: Optional[int] = None):
    query = {"is_active": True}
    if user_id:
        query["user_id"] = int(user_id)

    try:
        async for rule in live_forward_col.find(query):
            rule_id = str(rule["_id"])
            if rule_id not in ACTIVE_LIVE_HANDLERS:
                register_live_listener_hook(client, rule)
    except Exception as e:
        logger.error(f"Error syncing live listeners: {e}")


# -------------------------------------------------------------
# Interactive Dashboard UI (User Request: Source, Target, Settings, Actions)
# -------------------------------------------------------------

async def get_fwd_panel_text(user_id: int) -> str:
    cfg = await get_fwd_config(user_id)
    source_str = f"`{cfg.get('source_chat')}`" if cfg.get("source_chat") else "❌ सेट नहीं है (Not Set)"
    target_str = f"`{cfg.get('target_chat')}`" if cfg.get("target_chat") else "❌ सेट नहीं है (Not Set)"

    tag_mode = "🏷️ मूल फॉरवर्ड टैग (Raw Forward)" if cfg.get("forward_tag") else "✨ क्लीन कॉपी (Clean Copy)"
    protect_mode = "🔒 सुरक्षित (ON)" if cfg.get("protect_content") else "🔓 सामान्य (OFF)"

    user_caption = await get_user_data_key(user_id, 'caption', '')
    replacements = await get_user_data_key(user_id, 'replacement_words', {}) or {}
    delete_words = await get_user_data_key(user_id, 'delete_words', []) or []

    cap_status = "✅ सक्रिय (ON)" if (cfg.get("apply_custom_caption", True) and user_caption) else ("⏸️ बंद (OFF)" if not cfg.get("apply_custom_caption", True) else "❌ खाली (Empty)")
    rules_status = f"✅ सक्रिय ({len(replacements) + len(delete_words)} नियम)" if cfg.get("apply_word_rules", True) else "⏸️ बंद (OFF)"

    # Live listeners count
    live_count = await live_forward_col.count_documents({"user_id": int(user_id), "is_active": True})
    live_badge = f"🟢 सक्रिय ({live_count} लिसनर्स)" if live_count > 0 else "⚪ कोई सक्रिय नहीं"

    return (
        "🔄 **ऑटो फॉरवर्ड कंट्रोल पैनल (Auto Forward Panel)** 🔄\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📊 **वर्तमान कॉन्फ़िगरेशन (Current Setup):**\n\n"
        f"📤 **सोर्स चैट (Source):** {source_str}\n"
        f"📥 **टारगेट चैट (Target):** {target_str}\n"
        f"🏷️ **फॉरवर्ड मोड:** {tag_mode}\n"
        f"🛡️ **कंटेंट सुरक्षा:** {protect_mode}\n"
        f"📡 **24/7 लाइव लिसनर:** {live_badge}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⚙️ **कस्टम सेटिंग्स स्थिति (बिना थंबनेल ओवरहेड):**\n"
        f"• 📋 **कस्टम कैप्शन:** {cap_status}\n"
        f"• 🔄 **वर्ड रिप्लेस/डिलीट रूल्स:** {rules_status}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💡 नीचे दिए गए बटनों से चैट ID, सेटिंग्स और फॉरवर्डिंग तुरंत प्रबंधित करें:"
    )


def get_fwd_panel_keyboard(cfg: dict) -> InlineKeyboardMarkup:
    tag_btn_text = "🏷️ मोड: फॉरवर्ड टैग" if cfg.get("forward_tag") else "✨ मोड: क्लीन कॉपी"
    protect_btn_text = "🔒 सुरक्षा: चालू" if cfg.get("protect_content") else "🔓 सुरक्षा: बंद"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📤 सोर्स चैट सेट करें", callback_data="fwd_ui_set_source"),
            InlineKeyboardButton("📥 टारगेट चैट सेट करें", callback_data="fwd_ui_set_target")
        ],
        [
            InlineKeyboardButton(tag_btn_text, callback_data="fwd_ui_toggle_tag"),
            InlineKeyboardButton(protect_btn_text, callback_data="fwd_ui_toggle_protect")
        ],
        [
            InlineKeyboardButton("⚙️ कस्टम सेटिंग्स (Custom Settings)", callback_data="fwd_ui_custom_settings"),
            InlineKeyboardButton("📡 24/7 लाइव लिसनर्स", callback_data="fwd_ui_manage_live")
        ],
        [
            InlineKeyboardButton("🚀 अभी बैच फॉरवर्ड शुरू करें", callback_data="fwd_ui_start_batch"),
            InlineKeyboardButton("⚡ लाइव मिरर सक्रिय करें", callback_data="fwd_ui_activate_live")
        ],
        [
            InlineKeyboardButton("🔙 मुख्य मेनू (Main Menu)", callback_data="btn_main_menu")
        ]
    ])


@app.on_callback_query(filters.regex("^btn_auto_forward$"))
async def btn_auto_forward_callback(client: Client, callback: CallbackQuery):
    if await sub(client, callback) == 1:
        return
    user_id = callback.from_user.id
    FWD_SESSIONS.pop(user_id, None)

    cfg = await get_fwd_config(user_id)
    text = await get_fwd_panel_text(user_id)
    kb = get_fwd_panel_keyboard(cfg)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.reply_text(text, reply_markup=kb)


@app.on_callback_query(filters.regex("^fwd_ui_set_source$"))
async def fwd_ui_set_source_cb(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    FWD_SESSIONS[user_id] = {"action": "input_source"}

    cancel_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 रद्द करें (Cancel)", callback_data="fwd_ui_cancel_input")]
    ])
    await callback.message.edit_text(
        "📤 **सोर्स चैट सेट करें (Set Source Chat)**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "कृपया सोर्स का **लिंक**, **चैट ID** या **यूजरनेम** भेजें:\n\n"
        "💡 *उदाहरण:*\n"
        "• पब्लिक लिंक: `https://t.me/source_channel`\n"
        "• प्राइवेट लिंक: `https://t.me/c/1234567890/10`\n"
        "• चैट ID: `-1001234567890`\n"
        "• यूजरनेम: `@my_source_channel`\n\n"
        "रद्द करने के लिए /cancel टाइप करें या नीचे दिया गया बटन दबाएं।",
        reply_markup=cancel_kb
    )


@app.on_callback_query(filters.regex("^fwd_ui_set_target$"))
async def fwd_ui_set_target_cb(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    FWD_SESSIONS[user_id] = {"action": "input_target"}

    cancel_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 रद्द करें (Cancel)", callback_data="fwd_ui_cancel_input")]
    ])
    await callback.message.edit_text(
        "📥 **टारगेट चैट सेट करें (Set Target Chat)**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "कृपया उस चैनल या ग्रुप का **लिंक** या **ID** भेजें जहाँ संदेश भेजने हैं:\n\n"
        "💡 *उदाहरण:*\n"
        "• चैट ID: `-1001234567890`\n"
        "• प्राइवेट लिंक: `https://t.me/c/1234567890`\n"
        "• यूजरनेम: `@my_target_channel`\n\n"
        "⚠️ *नोट: सुनिश्चित करें कि बॉट (या आपका लॉगिन किया हुआ अकाउंट) टारगेट चैट में एडमिन है।*",
        reply_markup=cancel_kb
    )


@app.on_callback_query(filters.regex("^fwd_ui_cancel_input$"))
async def fwd_ui_cancel_input_cb(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    FWD_SESSIONS.pop(user_id, None)
    await callback.answer("इनपुट रद्द कर दिया गया।", show_alert=False)
    await btn_auto_forward_callback(client, callback)


@app.on_callback_query(filters.regex("^fwd_ui_toggle_tag$"))
async def fwd_ui_toggle_tag_cb(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    cfg = await get_fwd_config(user_id)
    new_val = not cfg.get("forward_tag", False)
    await update_fwd_config(user_id, {"forward_tag": new_val})

    cfg["forward_tag"] = new_val
    text = await get_fwd_panel_text(user_id)
    kb = get_fwd_panel_keyboard(cfg)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass
    status_text = "🏷️ फॉरवर्ड टैग चालू" if new_val else "✨ क्लीन कॉपी मोड चालू"
    await callback.answer(status_text, show_alert=False)


@app.on_callback_query(filters.regex("^fwd_ui_toggle_protect$"))
async def fwd_ui_toggle_protect_cb(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    cfg = await get_fwd_config(user_id)
    new_val = not cfg.get("protect_content", False)
    await update_fwd_config(user_id, {"protect_content": new_val})

    cfg["protect_content"] = new_val
    text = await get_fwd_panel_text(user_id)
    kb = get_fwd_panel_keyboard(cfg)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass
    status_text = "🔒 कंटेंट सुरक्षा चालू" if new_val else "🔓 कंटेंट सुरक्षा बंद"
    await callback.answer(status_text, show_alert=False)


# -------------------------------------------------------------
# Auto-Forward Specific Custom Settings Submenu (No Thumbnail)
# -------------------------------------------------------------

@app.on_callback_query(filters.regex("^fwd_ui_custom_settings$"))
async def fwd_ui_custom_settings_cb(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    cfg = await get_fwd_config(user_id)

    cap_active = cfg.get("apply_custom_caption", True)
    words_active = cfg.get("apply_word_rules", True)

    user_caption = await get_user_data_key(user_id, 'caption', '')
    replacements = await get_user_data_key(user_id, 'replacement_words', {}) or {}
    delete_words = await get_user_data_key(user_id, 'delete_words', []) or []

    text = (
        "⚙️ **ऑटो फॉरवर्ड कस्टम सेटिंग्स (Forward Custom Settings)**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "यहाँ से आप तय कर सकते हैं कि फॉरवर्ड करते समय कौन-कौन सी कस्टम सेटिंग्स लागू होंगी।\n\n"
        f"📋 **कस्टम कैप्शन:** {'✅ चालू' if cap_active else '❌ बंद'}\n"
        f"   • वर्तमान कैप्शन: {f'`{user_caption[:35]}...`' if user_caption else 'कोई नहीं'}\n\n"
        f"🔄 **वर्ड रूल्स:** {'✅ चालू' if words_active else '❌ बंद'}\n"
        f"   • रिप्लेसमेंट: `{len(replacements)}` नियम\n"
        f"   • डिलीट वर्ड्स: `{len(delete_words)}` शब्द\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💡 *थंबनेल सेटिंग्स को यहाँ से हटा दिया गया है ताकि फॉरवर्डिंग सुपरफास्ट रहे। "
        "यदि परमानेंट थंबनेल बदलना हो तो मुख्य सेटिंग्स मेनू से कभी भी कर सकते हैं।*"
    )

    cap_btn_text = "📋 कैप्शन: चालू" if cap_active else "📋 कैप्शन: बंद"
    words_btn_text = "🔄 वर्ड रूल्स: चालू" if words_active else "🔄 वर्ड रूल्स: बंद"

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(cap_btn_text, callback_data="fwd_ui_toggle_cap_rule"),
            InlineKeyboardButton(words_btn_text, callback_data="fwd_ui_toggle_word_rule")
        ],
        [
            InlineKeyboardButton("🗑️ डिलीट वर्ड्स (Delete Words)", callback_data="fwd_ui_set_delete_words"),
            InlineKeyboardButton("🔄 रिप्लेस वर्ड्स (Replace Words)", callback_data="fwd_ui_set_replace_words")
        ],
        [
            InlineKeyboardButton("✏️ कैप्शन सेट करें", callback_data="fwd_ui_set_fwd_caption"),
            InlineKeyboardButton("🏷️ रीनेम टैग सेट करें", callback_data="fwd_ui_set_rename_tag")
        ],
        [
            InlineKeyboardButton("🧹 डिलीट वर्ड्स साफ़ करें", callback_data="fwd_ui_clear_del_words"),
            InlineKeyboardButton("❌ रिप्लेस रूल्स साफ़ करें", callback_data="fwd_ui_clear_rep_words")
        ],
        [
            InlineKeyboardButton("🔙 ऑटो फॉरवर्ड पैनल", callback_data="btn_auto_forward")
        ]
    ])

    await callback.message.edit_text(text, reply_markup=kb)


@app.on_callback_query(filters.regex("^fwd_ui_set_delete_words$"))
async def fwd_ui_set_delete_words_cb(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    FWD_SESSIONS[user_id] = {"action": "input_del_words"}
    cancel_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 रद्द करें (Cancel)", callback_data="fwd_ui_custom_settings")]
    ])
    await callback.message.edit_text(
        "🗑️ **डिलीट वर्ड्स जोड़ें (Add Delete Words):**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👉 वे सभी शब्द भेजें जिन्हें आप फ़ाइल नाम और कैप्शन से हटाना चाहते हैं:\n\n"
        "💡 *उदाहरण:* `promo ad www.site.com @oldchannel`\n\n"
        "*(शब्दों को स्पेस या कॉमा देकर एक साथ भेज सकते हैं)*",
        reply_markup=cancel_kb
    )


@app.on_callback_query(filters.regex("^fwd_ui_set_replace_words$"))
async def fwd_ui_set_replace_words_cb(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    FWD_SESSIONS[user_id] = {"action": "input_rep_words"}
    cancel_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 रद्द करें (Cancel)", callback_data="fwd_ui_custom_settings")]
    ])
    await callback.message.edit_text(
        "🔄 **वर्ड रिप्लेसमेंट नियम जोड़ें (Word Replacement):**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👉 जिन शब्दों को बदलना है, उन्हें इस तरह भेजें:\n"
        "`'पुराना_शब्द' 'नया_शब्द'` या `पुराना -> नया`\n\n"
        "💡 *हाइपरलिंक भी लगा सकते हैं (जैसे 'पुराना' '[मेरा चैनल](https://t.me/mychannel)')*\n"
        "उदा: `'Join @Old' '[Join My Channel](https://t.me/newchannel)'`",
        reply_markup=cancel_kb
    )


@app.on_callback_query(filters.regex("^fwd_ui_set_rename_tag$"))
async def fwd_ui_set_rename_tag_cb(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    FWD_SESSIONS[user_id] = {"action": "input_rename_tag"}
    cancel_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 रद्द करें (Cancel)", callback_data="fwd_ui_custom_settings")]
    ])
    await callback.message.edit_text(
        "🏷️ **रीनेम टैग सेट करें (Set Rename Tag):**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👉 फाइलों के नाम के अंत में जोड़ने के लिए अपना टैग भेजें:\n\n"
        "💡 *उदाहरण:* `@MyChannel`\n\n"
        "टैग हटाने के लिए केवल `None` या `Clear` लिखकर भेजें।",
        reply_markup=cancel_kb
    )


@app.on_callback_query(filters.regex("^fwd_ui_clear_del_words$"))
async def fwd_ui_clear_del_words_cb(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    await users_collection.update_one({'user_id': user_id}, {'$unset': {'delete_words': ''}})
    await callback.answer("🧹 सभी डिलीट वर्ड्स साफ़ कर दिए गए!", show_alert=True)
    await fwd_ui_custom_settings_cb(client, callback)


@app.on_callback_query(filters.regex("^fwd_ui_clear_rep_words$"))
async def fwd_ui_clear_rep_words_cb(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    await users_collection.update_one({'user_id': user_id}, {'$unset': {'replacement_words': ''}})
    await callback.answer("❌ सभी रिप्लेसमेंट रूल्स साफ़ कर दिए गए!", show_alert=True)
    await fwd_ui_custom_settings_cb(client, callback)


@app.on_callback_query(filters.regex("^fwd_ui_toggle_cap_rule$"))
async def fwd_ui_toggle_cap_rule_cb(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    cfg = await get_fwd_config(user_id)
    new_val = not cfg.get("apply_custom_caption", True)
    await update_fwd_config(user_id, {"apply_custom_caption": new_val})
    await callback.answer("कैप्शन टॉगल किया गया", show_alert=False)
    await fwd_ui_custom_settings_cb(client, callback)


@app.on_callback_query(filters.regex("^fwd_ui_toggle_word_rule$"))
async def fwd_ui_toggle_word_rule_cb(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    cfg = await get_fwd_config(user_id)
    new_val = not cfg.get("apply_word_rules", True)
    await update_fwd_config(user_id, {"apply_word_rules": new_val})
    await callback.answer("वर्ड रूल्स टॉगल किया गया", show_alert=False)
    await fwd_ui_custom_settings_cb(client, callback)


@app.on_callback_query(filters.regex("^fwd_ui_set_fwd_caption$"))
async def fwd_ui_set_fwd_caption_cb(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    FWD_SESSIONS[user_id] = {"action": "input_caption"}

    cancel_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 रद्द करें (Cancel)", callback_data="fwd_ui_custom_settings")]
    ])
    await callback.message.edit_text(
        "📋 **नया कस्टम कैप्शन दर्ज करें:**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "कृपया वह टेक्स्ट भेजें जो आप हर फॉरवर्ड किए गए मीडिया के नीचे जोड़ना चाहते हैं:\n\n"
        "हटाने के लिए केवल `None` या `Clear` लिखकर भेजें।",
        reply_markup=cancel_kb
    )


# -------------------------------------------------------------
# Execution Triggers (Batch & Live from Panel)
# -------------------------------------------------------------

@app.on_callback_query(filters.regex("^fwd_ui_start_batch$"))
async def fwd_ui_start_batch_cb(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id in ACTIVE_FWD_TASKS:
        await callback.answer("⚠️ आपकी एक ऑटो फॉरवर्डिंग प्रक्रिया पहले से चल रही है!", show_alert=True)
        return

    cfg = await get_fwd_config(user_id)
    from_chat = cfg.get("source_chat")
    to_chat = cfg.get("target_chat")

    if not from_chat:
        await callback.answer("❌ कृपया पहले सोर्स चैट (Source Chat) सेट करें!", show_alert=True)
        return
    if not to_chat:
        await callback.answer("❌ कृपया पहले टारगेट चैट (Target Chat) सेट करें!", show_alert=True)
        return

    FWD_SESSIONS[user_id] = {"action": "input_batch_range"}

    cancel_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 रद्द करें (Cancel)", callback_data="btn_auto_forward")]
    ])

    await callback.message.edit_text(
        "🔢 **मैसेज रेंज दर्ज करें (Enter Message Range):**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📤 **सोर्स:** `{from_chat}`\n"
        f"📥 **टारगेट:** `{to_chat}`\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "कृपया शुरुआती और अंतिम मैसेज ID भेजें:\n\n"
        "💡 *फॉर्मेट:* `StartID-EndID` या `StartID EndID`\n"
        "उदा: `1-100` या `50 150`",
        reply_markup=cancel_kb
    )


@app.on_callback_query(filters.regex("^fwd_ui_activate_live$"))
async def fwd_ui_activate_live_cb(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    cfg = await get_fwd_config(user_id)
    from_chat = cfg.get("source_chat")
    to_chat = cfg.get("target_chat")

    if not from_chat:
        await callback.answer("❌ कृपया पहले सोर्स चैट (Source Chat) सेट करें!", show_alert=True)
        return
    if not to_chat:
        await callback.answer("❌ कृपया पहले टारगेट चैट (Target Chat) सेट करें!", show_alert=True)
        return

    # Check if this rule already exists
    existing = await live_forward_col.find_one({
        "user_id": user_id,
        "from_chat": from_chat,
        "to_chat": to_chat
    })
    if existing:
        if not existing.get("is_active"):
            await live_forward_col.update_one({"_id": existing["_id"]}, {"$set": {"is_active": True}})
            register_live_listener_hook(client, existing)
            await callback.answer("▶️ लाइव लिसनर पुनः शुरू कर दिया गया!", show_alert=True)
        else:
            await callback.answer("ℹ️ यह लाइव लिसनर पहले से सक्रिय है!", show_alert=True)
        await btn_auto_forward_callback(client, callback)
        return

    doc = {
        "user_id": user_id,
        "from_chat": from_chat,
        "to_chat": to_chat,
        "forward_tag": cfg.get("forward_tag", False),
        "is_active": True,
        "created_at": datetime.utcnow(),
        "forwarded_count": 0
    }
    result = await live_forward_col.insert_one(doc)
    doc["_id"] = result.inserted_id

    # Register hook on bot and userbot
    register_live_listener_hook(client, doc)
    from plugins.batch import UC
    user_client = UC.get(user_id)
    if user_client:
        register_live_listener_hook(user_client, doc)

    await callback.answer("🎉 24/7 लाइव लिसनर सक्रिय हो गया!", show_alert=True)
    await btn_auto_forward_callback(client, callback)


@app.on_callback_query(filters.regex("^fwd_ui_manage_live$"))
async def fwd_ui_manage_live_cb(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    rules = []
    async for r in live_forward_col.find({"user_id": int(user_id)}):
        rules.append(r)

    if not rules:
        text = (
            "📡 **लाइव लिसनर्स प्रबंधन (Live Listeners)**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "वर्तमान में आपका कोई भी **लाइव लिसनर** सक्रिय नहीं है।\n\n"
            "💡 पैनल में सोर्स और टारगेट चैट सेट करके **'⚡ लाइव मिरर सक्रिय करें'** बटन दबाएं।"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 ऑटो फॉरवर्ड पैनल", callback_data="btn_auto_forward")]
        ])
        await callback.message.edit_text(text, reply_markup=kb)
        return

    lines = [
        "📡 **आपके सक्रिय 24/7 लाइव लिसनर्स (Active Rules):**\n",
        "━━━━━━━━━━━━━━━━━━━━"
    ]
    for idx, r in enumerate(rules, 1):
        status = "🟢 सक्रिय (ON)" if r.get("is_active", True) else "🔴 बंद (OFF)"
        fwd_count = r.get("forwarded_count", 0)
        from_c = r.get("from_chat")
        to_c = r.get("to_chat")
        tag_mode = "टैग सहित" if r.get("forward_tag") else "क्लीन कॉपी"
        lines.append(
            f"**{idx}.** `{from_c}` ➔ `{to_c}`\n"
            f"   • स्थिति: {status} | मोड: {tag_mode}\n"
            f"   • कुल फॉरवर्ड: `{fwd_count}`\n"
        )
    lines.append("━━━━━━━━━━━━━━━━━━━━")

    rule_btns = []
    for idx, r in enumerate(rules, 1):
        rid = str(r["_id"])
        is_active = r.get("is_active", True)
        toggle_text = f"⏸️ #{idx}" if is_active else f"▶️ #{idx}"
        del_text = f"🗑️ #{idx}"
        rule_btns.append([
            InlineKeyboardButton(f"{toggle_text} स्थिति बदलें", callback_data=f"fwd_toggle_{rid}"),
            InlineKeyboardButton(f"{del_text} हटाएं", callback_data=f"fwd_del_{rid}")
        ])

    rule_btns.append([InlineKeyboardButton("🔙 ऑटो फॉरवर्ड पैनल", callback_data="btn_auto_forward")])
    await callback.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(rule_btns))


@app.on_callback_query(filters.regex(r"^fwd_toggle_([a-fA-F0-9]+)$"))
async def fwd_toggle_rule_cb(client: Client, callback: CallbackQuery):
    from bson import ObjectId
    rule_id_str = callback.matches[0].group(1)
    user_id = callback.from_user.id

    try:
        rule = await live_forward_col.find_one({"_id": ObjectId(rule_id_str), "user_id": user_id})
        if not rule:
            await callback.answer("❌ नियम नहीं मिला!", show_alert=True)
            return

        new_status = not rule.get("is_active", True)
        await live_forward_col.update_one(
            {"_id": ObjectId(rule_id_str)},
            {"$set": {"is_active": new_status}}
        )

        if not new_status:
            unregister_live_listener_hook(rule_id_str)
            await callback.answer("⏸️ लाइव लिसनर रोक दिया गया।", show_alert=False)
        else:
            rule["is_active"] = True
            register_live_listener_hook(client, rule)
            await callback.answer("▶️ लाइव लिसनर शुरू कर दिया गया!", show_alert=False)

        await fwd_ui_manage_live_cb(client, callback)
    except Exception as e:
        logger.error(f"Toggle rule error: {e}")
        await callback.answer("त्रुटि हुई।", show_alert=True)


@app.on_callback_query(filters.regex(r"^fwd_del_([a-fA-F0-9]+)$"))
async def fwd_del_rule_cb(client: Client, callback: CallbackQuery):
    from bson import ObjectId
    rule_id_str = callback.matches[0].group(1)
    user_id = callback.from_user.id

    try:
        unregister_live_listener_hook(rule_id_str)
        await live_forward_col.delete_one({"_id": ObjectId(rule_id_str), "user_id": user_id})
        await callback.answer("🗑️ लाइव लिसनर हटा दिया गया।", show_alert=False)
        await fwd_ui_manage_live_cb(client, callback)
    except Exception as e:
        logger.error(f"Delete rule error: {e}")
        await callback.answer("त्रुटि हुई।", show_alert=True)


@app.on_callback_query(filters.regex(r"^fwd_cancel_(\d+)$"))
async def fwd_cancel_running_task_cb(client: Client, callback: CallbackQuery):
    target_uid = int(callback.matches[0].group(1))
    user_id = callback.from_user.id
    if user_id != target_uid and str(user_id) != str(OWNER_ID):
        await callback.answer("❌ यह आपका टास्क नहीं है!", show_alert=True)
        return

    if target_uid in ACTIVE_FWD_TASKS:
        ACTIVE_FWD_TASKS[target_uid]["cancel_requested"] = True
        await callback.answer("🛑 प्रक्रिया रोकने का अनुरोध भेजा गया...", show_alert=True)
    else:
        await callback.answer("यह टास्क पहले ही समाप्त हो चुका है।", show_alert=False)


# -------------------------------------------------------------
# Input Handler for User text (Source, Target, Batch Range, Caption)
# -------------------------------------------------------------

@app.on_message(filters.private & ~filters.command(["start", "cancel", "help", "login", "batch", "single", "speedtest", "myplan", "settings", "terms"]))
async def fwd_panel_text_handler(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in FWD_SESSIONS:
        return

    session = FWD_SESSIONS[user_id]
    action = session.get("action")
    text = (message.text or "").strip()

    if text.lower() in ["/cancel", "cancel", "रद्द करें"]:
        FWD_SESSIONS.pop(user_id, None)
        cfg = await get_fwd_config(user_id)
        kb = get_fwd_panel_keyboard(cfg)
        panel_text = await get_fwd_panel_text(user_id)
        await message.reply_text("🛑 **रद्द कर दिया गया।**\n\n" + panel_text, reply_markup=kb)
        return

    # 1. INPUT SOURCE CHAT
    if action == "input_source":
        cid, _ = get_channel_id_from_link(text)
        if not cid:
            await message.reply_text(
                "❌ **अमान्य लिंक या ID!** कृपया सही लिंक या ID भेजें:\n"
                "उदा: `https://t.me/source_channel` या `-1001234567890`"
            )
            return

        await update_fwd_config(user_id, {"source_chat": cid})
        FWD_SESSIONS.pop(user_id, None)

        cfg = await get_fwd_config(user_id)
        kb = get_fwd_panel_keyboard(cfg)
        panel_text = await get_fwd_panel_text(user_id)
        await message.reply_text(
            f"✅ **सोर्स चैट सफलतापूर्वक सेट हो गया:** `{cid}`\n\n" + panel_text,
            reply_markup=kb
        )
        return

    # 2. INPUT TARGET CHAT
    elif action == "input_target":
        cid, _ = get_channel_id_from_link(text)
        if not cid:
            await message.reply_text(
                "❌ **अमान्य लिंक या ID!** कृपया सही लिंक या ID भेजें:\n"
                "उदा: `-1001234567890` या `https://t.me/target_channel`"
            )
            return

        await update_fwd_config(user_id, {"target_chat": cid})
        FWD_SESSIONS.pop(user_id, None)

        cfg = await get_fwd_config(user_id)
        kb = get_fwd_panel_keyboard(cfg)
        panel_text = await get_fwd_panel_text(user_id)
        await message.reply_text(
            f"✅ **टारगेट चैट सफलतापूर्वक सेट हो गया:** `{cid}`\n\n" + panel_text,
            reply_markup=kb
        )
        return

    # 3. INPUT CAPTION
    elif action == "input_caption":
        FWD_SESSIONS.pop(user_id, None)
        if text.lower() in ["none", "clear", "हटाएं"]:
            await save_user_data(user_id, 'caption', '')
            await message.reply_text("✅ **कस्टम कैप्शन हटा दिया गया।**")
        else:
            await save_user_data(user_id, 'caption', text)
            await message.reply_text("✅ **कस्टम कैप्शन सफलतापूर्वक सहेज लिया गया।**")

        cfg = await get_fwd_config(user_id)
        kb = get_fwd_panel_keyboard(cfg)
        panel_text = await get_fwd_panel_text(user_id)
        await message.reply_text(panel_text, reply_markup=kb)
        return

    # 4. INPUT DELETE WORDS
    elif action == "input_del_words":
        FWD_SESSIONS.pop(user_id, None)
        from utils.func import parse_delete_words
        words = parse_delete_words(text)
        if words:
            existing = await get_user_data_key(user_id, 'delete_words', []) or []
            updated = list(dict.fromkeys(existing + words))
            await save_user_data(user_id, 'delete_words', updated)
            await message.reply_text(
                f"✅ **डिलीट लिस्ट में जोड़े गए शब्द:**\n`{', '.join(words)}`\n\n"
                f"📊 **कुल एक्टिव डिलीट वर्ड्स:** {len(updated)}"
            )
        else:
            await message.reply_text("❌ कोई मान्य शब्द नहीं मिला।")

        cfg = await get_fwd_config(user_id)
        kb = get_fwd_panel_keyboard(cfg)
        panel_text = await get_fwd_panel_text(user_id)
        await message.reply_text(panel_text, reply_markup=kb)
        return

    # 5. INPUT REPLACE WORDS
    elif action == "input_rep_words":
        FWD_SESSIONS.pop(user_id, None)
        from utils.func import parse_replacement_rules, extract_message_markdown
        raw_input = extract_message_markdown(message) or text
        matches = re.findall(r"""['"]([^'"]+)['"]\s*['"]([^'"]*)['"]""", raw_input)
        if not matches:
            matches = parse_replacement_rules(raw_input)

        if matches:
            replacements = await get_user_data_key(user_id, 'replacement_words', {}) or {}
            added = []
            for old_w, new_w in matches:
                old_clean = old_w.strip()
                new_clean = new_w.strip()
                if old_clean:
                    replacements[old_clean] = new_clean
                    added.append(f"• `{old_clean}` ➔ `{new_clean}`")
            await save_user_data(user_id, 'replacement_words', replacements)
            await message.reply_text(
                "✅ **वर्ड रिप्लेसमेंट नियम सेव हो गए!**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                + "\n".join(added) + "\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 **कुल एक्टिव नियम:** {len(replacements)}"
            )
        else:
            await message.reply_text(
                "❌ **अमान्य फॉर्मेट!**\n"
                "कृपया `'पुराना_शब्द' 'नया_शब्द'` या `पुराना -> नया` फॉर्मेट में भेजें।\n"
                "💡 उदाहरण: `'Join @Old' '[My Channel](https://t.me/new)'`"
            )

        cfg = await get_fwd_config(user_id)
        kb = get_fwd_panel_keyboard(cfg)
        panel_text = await get_fwd_panel_text(user_id)
        await message.reply_text(panel_text, reply_markup=kb)
        return

    # 6. INPUT RENAME TAG
    elif action == "input_rename_tag":
        FWD_SESSIONS.pop(user_id, None)
        if text.lower() in ["none", "clear", "हटाएं"]:
            await save_user_data(user_id, 'rename_tag', '')
            await message.reply_text("✅ **रीनेम टैग हटा दिया गया।**")
        else:
            await save_user_data(user_id, 'rename_tag', text)
            await message.reply_text(f"✅ **रीनेम टैग सेट किया गया:** `{text}`")

        cfg = await get_fwd_config(user_id)
        kb = get_fwd_panel_keyboard(cfg)
        panel_text = await get_fwd_panel_text(user_id)
        await message.reply_text(panel_text, reply_markup=kb)
        return

    # 4. INPUT BATCH RANGE & EXECUTE
    elif action == "input_batch_range":
        nums = re.findall(r"\d+", text)
        if len(nums) < 2:
            await message.reply_text(
                "❌ **गलत फॉर्मेट!** कृपया दो संख्याएँ भेजें।\n"
                "उदा: `1-100` या `10 50`"
            )
            return

        s_id = int(nums[0])
        e_id = int(nums[1])
        if s_id > e_id:
            s_id, e_id = e_id, s_id

        is_prem = await is_premium_user(user_id)
        diff = e_id - s_id + 1
        if not is_prem and diff > 500:
            e_id = s_id + 499
            await message.reply_text(f"ℹ️ *फ्री यूज़र्स के लिए एक बार में अधिकतम 500 संदेश अनुमति है। रेंज को `{s_id}-{e_id}` पर सेट किया गया है।*")

        FWD_SESSIONS.pop(user_id, None)
        cfg = await get_fwd_config(user_id)

        from_chat = cfg["source_chat"]
        to_chat = cfg["target_chat"]

        ACTIVE_FWD_TASKS[user_id] = {
            "cancel_requested": False,
            "from_chat": from_chat,
            "to_chat": to_chat,
            "start_id": s_id,
            "end_id": e_id,
            "forward_tag": cfg.get("forward_tag", False),
            "protect": cfg.get("protect_content", False),
            "cfg": cfg
        }

        from plugins.batch import UC, Y
        user_client = UC.get(user_id) or Y or userbot

        status_msg = await message.reply_text(
            f"⏳ **ऑटो फॉरवर्डिंग शुरू हो रही है...**\n"
            f"📤 `{from_chat}` ➔ 📥 `{to_chat}`\n"
            f"🔢 रेंज: `{s_id}` से `{e_id}`"
        )

        asyncio.create_task(
            run_forwarding_worker(client, user_client, user_id, status_msg, ACTIVE_FWD_TASKS[user_id])
        )
        return
