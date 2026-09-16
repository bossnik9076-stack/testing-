# Copyright (c) 2025 devgagan : https://github.com/devgaganin.  
# Licensed under the GNU General Public License v3.0.  
# See LICENSE file in the repository root for full license text.

import os, re, time, asyncio, json, logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from pyrogram.enums import ParseMode

try:
    import pyrogram.utils
    pyrogram.utils.MIN_CHANNEL_ID = -100999999999999
except Exception:
    pass

logger = logging.getLogger(__name__)
from config import API_ID, API_HASH, LOG_GROUP, STRING, FORCE_SUB, FREEMIUM_LIMIT, PREMIUM_LIMIT
from utils.func import get_user_data, screenshot, thumbnail, get_video_metadata, cleanup_temp_thumb
from utils.func import (
    get_user_data_key, process_text_with_rules, is_premium_user, E,
    can_user_extract, record_user_extraction, parse_replacement_rules, save_user_data,
    clean_chat_id_input, parse_delete_words
)
from shared_client import app as X
from plugins.settings import rename_file
from plugins.start import subscribe as sub
from utils.custom_filters import login_in_progress, settings_in_progress
from utils.encrypt import dcs
from typing import Dict, Any, Optional


Y = None if not STRING else __import__('shared_client').userbot
Z, P, UB, UC, emp = {}, {}, {}, {}, {}

ACTIVE_USERS = {}
ACTIVE_USERS_FILE = "active_users.json"

# fixed directory file_name problems 
def sanitize(filename):
    return re.sub(r'[<>:"/\\|?*\']', '_', filename).strip(" .")[:255]

def load_active_users():
    try:
        if os.path.exists(ACTIVE_USERS_FILE):
            with open(ACTIVE_USERS_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception:
        return {}

async def save_active_users_to_file():
    try:
        with open(ACTIVE_USERS_FILE, 'w') as f:
            json.dump(ACTIVE_USERS, f)
    except Exception as e:
        print(f"Error saving active users: {e}")

async def add_active_batch(user_id: int, batch_info: Dict[str, Any]):
    ACTIVE_USERS[str(user_id)] = batch_info
    await save_active_users_to_file()

def is_user_active(user_id: int) -> bool:
    return str(user_id) in ACTIVE_USERS

async def update_batch_progress(user_id: int, current: int, success: int):
    if str(user_id) in ACTIVE_USERS:
        ACTIVE_USERS[str(user_id)]["current"] = current
        ACTIVE_USERS[str(user_id)]["success"] = success
        await save_active_users_to_file()

async def request_batch_cancel(user_id: int):
    if str(user_id) in ACTIVE_USERS:
        ACTIVE_USERS[str(user_id)]["cancel_requested"] = True
        await save_active_users_to_file()
        return True
    return False

def should_cancel(user_id: int) -> bool:
    user_str = str(user_id)
    return user_str in ACTIVE_USERS and ACTIVE_USERS[user_str].get("cancel_requested", False)

async def remove_active_batch(user_id: int):
    if str(user_id) in ACTIVE_USERS:
        del ACTIVE_USERS[str(user_id)]
        await save_active_users_to_file()

def get_batch_info(user_id: int) -> Optional[Dict[str, Any]]:
    return ACTIVE_USERS.get(str(user_id))

ACTIVE_USERS = load_active_users()

# Fair Queue system to limit concurrent users to 3
# 1GB RAM / 1 vCPU optimized: allows max 3 users at once
# Other users wait in a fair FIFO rotation queue and get served sequentially (user 4, then 5, then 6...)
MAX_CONCURRENT_USERS = 3
TASK_QUEUE_LIST = []
currently_processing_users = set()
_queue_lock = asyncio.Lock()

def release_task_slot(uid):
    global TASK_QUEUE_LIST, currently_processing_users
    if uid in currently_processing_users:
        currently_processing_users.remove(uid)
    if uid in TASK_QUEUE_LIST:
        TASK_QUEUE_LIST.remove(uid)
    # Give next user the slot from queue
    if len(currently_processing_users) < MAX_CONCURRENT_USERS and TASK_QUEUE_LIST:
        next_uid = TASK_QUEUE_LIST.pop(0)
        currently_processing_users.add(next_uid)

async def acquire_task_slot(uid, pt_message=None):
    global TASK_QUEUE_LIST, currently_processing_users
    async with _queue_lock:
        if uid in currently_processing_users:
            return True
            
        if len(currently_processing_users) < MAX_CONCURRENT_USERS:
            currently_processing_users.add(uid)
            return True
            
        if uid not in TASK_QUEUE_LIST:
            TASK_QUEUE_LIST.append(uid)
            
    # If waiting, show dynamic download estimate without exposing queue position or waiting quota
    wait_time = 5
    while uid not in currently_processing_users:
        if pt_message:
            try:
                await pt_message.edit(f'⏳ **डाउनलोडिंग प्रोसेस शुरू होने वाला है...**\n\nअनुमानित समय: ~{wait_time} सेकंड बाद डाउनलोड शुरू होगा...')
            except Exception:
                pass
        await asyncio.sleep(4)
        wait_time = max(2, wait_time - 1)
        async with _queue_lock:
            if len(currently_processing_users) < MAX_CONCURRENT_USERS:
                if TASK_QUEUE_LIST and TASK_QUEUE_LIST[0] == uid:
                    TASK_QUEUE_LIST.pop(0)
                    currently_processing_users.add(uid)
                    break
                elif uid not in TASK_QUEUE_LIST:
                    currently_processing_users.add(uid)
                    break
                    
    if pt_message:
        try:
            await pt_message.edit('⏳ **डाउनलोडिंग प्रोसेस शुरू हो रहा है...**')
        except Exception:
            pass
    return True


async def upd_dlg(c):
    try:
        async for _ in c.get_dialogs(limit=100): pass
        return True
    except Exception as e:
        print(f'Failed to update dialogs: {e}')
        return False

# fixed the old group of 2021-2022 extraction 🌝 (buy krne ka fayda nhi ab old group) ✅ 
async def get_msg(c, u, i, d, lt, topic_id=None):
    try:
        cid_str = str(i).strip()
        try:
            if cid_str.startswith('-100'):
                cid_int = int(cid_str)
            elif cid_str.startswith('-'):
                cid_int = int(f"-100{cid_str[1:]}")
            elif cid_str.isdigit():
                cid_int = int(f"-100{cid_str}")
            else:
                cid_int = int(cid_str)
        except Exception:
            cid_int = i

        base_id = str(cid_str).replace('-100', '').replace('-', '')
        alt_cids = [cid_int]
        if base_id.isdigit():
            alt_1 = int(f"-100{base_id}")
            alt_2 = int(f"-{base_id}")
            alt_3 = int(base_id)
            for x in [alt_1, alt_2, alt_3]:
                if x not in alt_cids:
                    alt_cids.append(x)

        target_mids = [int(d)]
        if topic_id and int(topic_id) not in target_mids:
            target_mids.append(int(topic_id))

        if lt == 'public':
            clients = [c]
            if u and u not in clients: clients.append(u)
            if Y and Y not in clients: clients.append(Y)

            for cl in clients:
                for tmid in target_mids:
                    try:
                        xm = await cl.get_messages(i, tmid)
                        if xm and not getattr(xm, "empty", False):
                            return xm
                    except Exception:
                        pass
                if cl != c:
                    try:
                        await cl.join_chat(i)
                        chat = await cl.get_chat(f"@{i}" if not str(i).startswith('@') else i)
                        for tmid in target_mids:
                            xm = await cl.get_messages(chat.id, tmid)
                            if xm and not getattr(xm, "empty", False):
                                return xm
                    except Exception:
                        pass
            return None
        else:
            # Private channel / supergroup / topic link
            # Priority:
            # 1. User client (u)
            # 2. Bot client (c) - Bot is often added as admin in target/source channel!
            # 3. Default userbot (Y)
            clients = []
            if u and u not in clients: clients.append(u)
            if c and c not in clients: clients.append(c)
            if Y and Y not in clients: clients.append(Y)

            for cl in clients:
                for target_chat in alt_cids:
                    # 1. Direct message fetch
                    for tmid in target_mids:
                        try:
                            result = await cl.get_messages(target_chat, tmid)
                            if result and not getattr(result, "empty", False):
                                return result
                        except Exception:
                            pass

                    # 2. Try resolving peer via get_chat (loads access_hash into Pyrogram)
                    try:
                        await cl.get_chat(target_chat)
                        for tmid in target_mids:
                            result = await cl.get_messages(target_chat, tmid)
                            if result and not getattr(result, "empty", False):
                                return result
                    except Exception:
                        pass

                    # 3. Try resolving via dialogs scan
                    try:
                        async for dlg in cl.get_dialogs(limit=100):
                            if dlg.chat and (dlg.chat.id == target_chat or str(dlg.chat.id) in [str(x) for x in alt_cids]):
                                break
                        for tmid in target_mids:
                            result = await cl.get_messages(target_chat, tmid)
                            if result and not getattr(result, "empty", False):
                                return result
                    except Exception:
                        pass

            return None
    except Exception as e:
        logger.error(f'Error fetching message: {e}')
        return None


async def get_ubot(uid):
    bt = await get_user_data_key(uid, "bot_token", None)
    if not bt: return None
    if uid in UB: return UB.get(uid)
    try:
        bot = Client(f"user_{uid}", bot_token=bt, api_id=API_ID, api_hash=API_HASH)
        await bot.start()
        UB[uid] = bot
        return bot
    except Exception as e:
        print(f"Error starting bot for user {uid}: {e}")
        return None

async def get_uclient(uid):
    uid_int = int(uid)
    cl = UC.get(uid_int)
    if cl:
        if getattr(cl, 'is_connected', False):
            return cl
        else:
            try:
                await cl.start()
                return cl
            except Exception:
                pass

    ud = await get_user_data(uid_int)
    xxx = ud.get('session_string') if ud else None
    if xxx:
        try:
            ss = None
            try:
                ss = dcs(xxx)
            except Exception:
                ss = xxx
            if not ss:
                ss = xxx

            gg = Client(
                f'{uid_int}_client',
                api_id=int(API_ID),
                api_hash=API_HASH,
                device_model="v3saver",
                session_string=ss,
                in_memory=True
            )
            try:
                from utils.func import setup_peer_storage_sync, load_db_peers_into_storage
                setup_peer_storage_sync(gg)
            except Exception:
                pass
            await gg.start()
            try:
                await load_db_peers_into_storage(gg)
            except Exception:
                pass
            asyncio.create_task(upd_dlg(gg))
            UC[uid_int] = gg
            try:
                from plugins.auto_forward import sync_live_listeners_for_client
                asyncio.create_task(sync_live_listeners_for_client(gg, uid_int))
            except Exception:
                pass
            return gg
        except Exception as e:
            err_str = str(e)
            logger.error(f'User client start error for {uid_int}: {e}')
            if any(k in err_str for k in ["SESSION_REVOKED", "AUTH_KEY_UNREGISTERED", "USER_DEACTIVATED"]):
                logger.warning(f"Session revoked by Telegram for {uid_int}. Removing from DB.")
                await remove_user_session(uid_int)
                UC.pop(uid_int, None)
    return None

async def prog(c, t, C, h, m, st):
    if should_cancel(int(h)):
        raise asyncio.CancelledError("Cancelled by user")
    global P
    p = c / t * 100
    interval = 10 if t >= 100 * 1024 * 1024 else 20 if t >= 50 * 1024 * 1024 else 30 if t >= 10 * 1024 * 1024 else 50
    step = int(p // interval) * interval
    if m not in P or P[m] != step or p >= 100:
        P[m] = step
        c_mb = c / (1024 * 1024)
        t_mb = t / (1024 * 1024)
        bar = '🟢' * int(p / 10) + '🔴' * (10 - int(p / 10))
        speed = c / (time.time() - st) / (1024 * 1024) if time.time() > st else 0
        eta = time.strftime('%M:%S', time.gmtime((t - c) / (speed * 1024 * 1024))) if speed > 0 else '00:00'
        try:
            await C.edit_message_text(h, m, f"__**Processing...**__\n\n{bar}\n\n⚡ **Completed**: {c_mb:.2f} MB / {t_mb:.2f} MB\n🚀 **Speed**: {speed:.2f} MB/s\n⏳ **ETA**: {eta}")
        except Exception:
            pass
        if p >= 100: P.pop(m, None)

async def send_direct(c, m, tcid, ft=None, rtmid=None):
    try:
        if m.video:
            await c.send_video(tcid, m.video.file_id, caption=ft, duration=m.video.duration, width=m.video.width, height=m.video.height, reply_to_message_id=rtmid)
        elif m.video_note:
            await c.send_video_note(tcid, m.video_note.file_id, reply_to_message_id=rtmid)
        elif m.voice:
            await c.send_voice(tcid, m.voice.file_id, reply_to_message_id=rtmid)
        elif m.sticker:
            await c.send_sticker(tcid, m.sticker.file_id, reply_to_message_id=rtmid)
        elif m.audio:
            await c.send_audio(tcid, m.audio.file_id, caption=ft, duration=m.audio.duration, performer=m.audio.performer, title=m.audio.title, reply_to_message_id=rtmid)
        elif m.photo:
            photo_id = m.photo.file_id if hasattr(m.photo, 'file_id') else m.photo[-1].file_id
            await c.send_photo(tcid, photo_id, caption=ft, reply_to_message_id=rtmid)
        elif m.document:
            await c.send_document(tcid, m.document.file_id, caption=ft, file_name=m.document.file_name, reply_to_message_id=rtmid)
        else:
            return False
        return True
    except Exception as e:
        print(f'Direct send error: {e}')
        return False

async def log_to_channel(c, u, uid, sent_msg=None, fallback_text=None):
    """
    Guarantees every extracted item (video, file, photo, audio, text, public or private)
    is forwarded/copied to the LOG_GROUP with user details.
    """
    if not LOG_GROUP:
        return
    try:
        try:
            usr = await c.get_users(int(uid))
            u_name = re.sub(r'[_*\[\]()~`>#+\-=|{}.!]', '', usr.first_name or "User")
            mention = f"[{u_name}](tg://user?id={uid})"
        except Exception:
            mention = f"User `{uid}`"

        caption_info = f"👤 **Extracted by:** {mention}\n🆔 **User ID:** `{uid}`\n⏰ **Time:** `{time.strftime('%Y-%m-%d %H:%M:%S')}`"

        logged_msg = None

        if sent_msg:
            from_chat = getattr(getattr(sent_msg, 'chat', None), 'id', None)
            mid = getattr(sent_msg, 'id', None)

            if from_chat and mid:
                # 1. Try bot copy_message
                try:
                    logged_msg = await c.copy_message(LOG_GROUP, from_chat_id=from_chat, message_id=mid)
                except Exception as ce1:
                    logger.debug(f"copy_message to LOG_GROUP failed: {ce1}")

                # 2. Try bot forward_messages
                if not logged_msg:
                    try:
                        fwds = await c.forward_messages(LOG_GROUP, from_chat_id=from_chat, message_ids=mid)
                        logged_msg = fwds[0] if isinstance(fwds, list) else fwds
                    except Exception as fe1:
                        logger.debug(f"forward_messages to LOG_GROUP failed: {fe1}")

                # 3. Try userbot copy/forward if bot failed
                fallback_u = u if (u and u != c) else Y
                if not logged_msg and fallback_u:
                    try:
                        logged_msg = await fallback_u.copy_message(LOG_GROUP, from_chat_id=from_chat, message_id=mid)
                    except Exception:
                        try:
                            fwds = await fallback_u.forward_messages(LOG_GROUP, from_chat_id=from_chat, message_ids=mid)
                            logged_msg = fwds[0] if isinstance(fwds, list) else fwds
                        except Exception:
                            pass

        # 4. If fallback_text provided and no message copied yet
        if not logged_msg and fallback_text:
            try:
                logged_msg = await c.send_message(LOG_GROUP, text=str(fallback_text)[:4000])
            except Exception:
                pass

        # 5. Send user attribution
        if logged_msg:
            try:
                await c.send_message(LOG_GROUP, text=caption_info, reply_to_message_id=logged_msg.id)
            except Exception:
                try:
                    await c.send_message(LOG_GROUP, text=caption_info)
                except Exception:
                    pass
        elif fallback_text or sent_msg:
            try:
                await c.send_message(LOG_GROUP, text=f"📥 **Extraction Notification:**\n{caption_info}")
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Error in log_to_channel: {e}")

async def send_media_file(client, target_chat, f, m, ft, th, dur, h, w, prog, p, d, st, rtmid):
    video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.ogv']
    audio_extensions = ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.opus', '.aiff', '.ac3']
    file_ext = os.path.splitext(f)[1].lower()
    caption_text = ft if ft else (m.caption if m.caption else None)
    
    async def _safe_send(send_func, **kwargs):
        try:
            return await send_func(**kwargs, parse_mode=ParseMode.MARKDOWN)
        except Exception as err:
            err_str = str(err).lower()
            if any(k in err_str for k in ['markdown', 'entity', 'tag', 'entities', 'bracket']):
                logger.warning(f"Markdown parse warning ({err}), retrying without parse_mode")
                kwargs.pop('parse_mode', None)
                return await send_func(**kwargs)
            raise err

    if m.video or (m.document and file_ext in video_extensions):
        return await _safe_send(
            client.send_video,
            chat_id=target_chat, video=f, caption=caption_text,
            thumb=th, width=w, height=h, duration=dur,
            progress=prog, progress_args=(client, d, p.id, st),
            reply_to_message_id=rtmid
        )
    elif m.video_note:
        return await client.send_video_note(
            target_chat, video_note=f, progress=prog,
            progress_args=(client, d, p.id, st), reply_to_message_id=rtmid
        )
    elif m.voice:
        return await client.send_voice(
            target_chat, f, progress=prog, progress_args=(client, d, p.id, st),
            reply_to_message_id=rtmid
        )
    elif m.sticker:
        return await client.send_sticker(target_chat, m.sticker.file_id, reply_to_message_id=rtmid)
    elif m.audio or (m.document and file_ext in audio_extensions):
        return await _safe_send(
            client.send_audio,
            chat_id=target_chat, audio=f, caption=caption_text,
            thumb=th, progress=prog, progress_args=(client, d, p.id, st),
            reply_to_message_id=rtmid
        )
    elif m.photo:
        return await _safe_send(
            client.send_photo,
            chat_id=target_chat, photo=f, caption=caption_text,
            progress=prog, progress_args=(client, d, p.id, st),
            reply_to_message_id=rtmid
        )
    else:
        return await _safe_send(
            client.send_document,
            chat_id=target_chat, document=f, caption=caption_text,
            file_name=os.path.basename(f),
            progress=prog, progress_args=(client, d, p.id, st),
            reply_to_message_id=rtmid
        )

async def process_msg(c, u, m, d, lt, uid, i):
    try:
        cfg_chat = await get_user_data_key(d, 'chat_id', None)
        tcid = int(d)
        rtmid = None
        if cfg_chat:
            try:
                str_cfg = str(cfg_chat).strip()
                if '/' in str_cfg:
                    parts = str_cfg.split('/', 1)
                    target_part = parts[0].strip()
                    tcid = int(target_part) if (target_part.startswith('-100') or target_part.lstrip('-').isdigit()) else target_part
                    rtmid = int(parts[1]) if len(parts) > 1 and parts[1].strip().isdigit() else None
                elif str_cfg.startswith('@'):
                    tcid = str_cfg
                elif str_cfg.startswith('-100') or str_cfg.lstrip('-').isdigit():
                    tcid = int(str_cfg)
                else:
                    tcid = str_cfg
            except Exception:
                tcid = int(d)
        
        # Extract markdown preserving existing links/formatting
        orig_text = ""
        if hasattr(m, 'caption') and m.caption:
            if hasattr(m.caption, 'markdown') and m.caption.markdown:
                orig_text = str(m.caption.markdown)
            elif getattr(m, 'caption_entities', None) and hasattr(c, 'parser'):
                try:
                    orig_text = c.parser.unparse(str(m.caption), m.caption_entities, is_html=False)
                except Exception:
                    orig_text = str(m.caption)
            else:
                orig_text = str(m.caption)
        elif hasattr(m, 'text') and m.text:
            if hasattr(m.text, 'markdown') and m.text.markdown:
                orig_text = str(m.text.markdown)
            elif getattr(m, 'entities', None) and hasattr(c, 'parser'):
                try:
                    orig_text = c.parser.unparse(str(m.text), m.entities, is_html=False)
                except Exception:
                    orig_text = str(m.text)
            else:
                orig_text = str(m.text)
        elif hasattr(m, 'message') and m.message:
            try:
                from telethon.extensions import markdown as tmd
                orig_text = tmd.unparse(m.message, getattr(m, 'entities', []))
            except Exception:
                orig_text = str(m.message)

        proc_text = await process_text_with_rules(d, orig_text)
        user_cap = await get_user_data_key(d, 'caption', '') or ''
        ft = f'{proc_text}\n\n{user_cap}'.strip() if proc_text and user_cap else (user_cap or proc_text or None)

        # PUBLIC LINK -> DIRECT FORWARD / COPY AS REQUESTED
        if lt == 'public':
            try:
                # 1. Try bot copy_message
                try:
                    sent = await c.copy_message(chat_id=tcid, from_chat_id=i, message_id=m.id, caption=ft if ft else None, parse_mode=ParseMode.MARKDOWN, reply_to_message_id=rtmid)
                    if sent:
                        await log_to_channel(c, u, uid, sent)
                        return 'Forwarded directly.'
                except Exception:
                    if ft:
                        try:
                            sent = await c.copy_message(chat_id=tcid, from_chat_id=i, message_id=m.id, caption=ft, reply_to_message_id=rtmid)
                            if sent:
                                await log_to_channel(c, u, uid, sent)
                                return 'Forwarded directly.'
                        except Exception:
                            pass
                
                # 2. Try bot forward_messages
                try:
                    sent = await c.forward_messages(chat_id=tcid, from_chat_id=i, message_ids=m.id)
                    if sent:
                        first_sent = sent[0] if isinstance(sent, list) else sent
                        await log_to_channel(c, u, uid, first_sent)
                        return 'Forwarded directly.'
                except Exception:
                    pass

                # 3. Try userbot copy_message
                if u and u != c:
                    try:
                        sent = await u.copy_message(chat_id=tcid, from_chat_id=i, message_id=m.id, caption=ft if ft else None, parse_mode=ParseMode.MARKDOWN, reply_to_message_id=rtmid)
                        if sent:
                            await log_to_channel(c, u, uid, sent)
                            return 'Forwarded directly.'
                    except Exception:
                        pass
                    try:
                        sent = await u.forward_messages(chat_id=tcid, from_chat_id=i, message_ids=m.id)
                        if sent:
                            first_sent = sent[0] if isinstance(sent, list) else sent
                            await log_to_channel(c, u, uid, first_sent)
                            return 'Forwarded directly.'
                    except Exception:
                        pass
            except Exception as e:
                print(f"Public copy/forward error: {e}")
            # If direct copy was restricted by channel, fall through to download & upload

        # If it is a text-only message (no media)
        if not m.media:
            if m.text:
                msg_text = ft if ft else (orig_text or m.text or '')
                sent_txt = None
                try:
                    sent_txt = await c.send_message(tcid, text=msg_text, parse_mode=ParseMode.MARKDOWN, reply_to_message_id=rtmid)
                except Exception:
                    try:
                        sent_txt = await c.send_message(tcid, text=msg_text, reply_to_message_id=rtmid)
                    except Exception as text_err:
                        fallback_u = u if (u and u != c) else Y
                        if fallback_u and tcid != int(d):
                            try:
                                sent_txt = await fallback_u.send_message(tcid, text=msg_text, parse_mode=ParseMode.MARKDOWN, reply_to_message_id=rtmid)
                            except Exception:
                                sent_txt = await c.send_message(int(d), text=msg_text)
                        else:
                            sent_txt = await c.send_message(int(d), text=msg_text)
                if sent_txt:
                    await log_to_channel(c, u, uid, sent_msg=sent_txt, fallback_text=msg_text)
                return 'Done.'
            return 'Empty message.'

        # PRIVATE LINK (OR RESTRICTED PUBLIC) -> DOWNLOAD & UPLOAD (as in GitHub repo)
        st = time.time()
        p = await c.send_message(d, '⏳ Downloading content...')

        c_name = f"{time.time()}"
        if m.video:
            file_name = m.video.file_name or f"{time.time()}.mp4"
            c_name = sanitize(file_name)
        elif m.audio:
            file_name = m.audio.file_name or f"{time.time()}.mp3"
            c_name = sanitize(file_name)
        elif m.document:
            file_name = m.document.file_name or f"{time.time()}"
            c_name = sanitize(file_name)
        elif m.photo:
            file_name = f"{time.time()}.jpg"
            c_name = sanitize(file_name)

        dl_client = u if (u and u != c) else Y or c
        f = await dl_client.download_media(m, file_name=c_name, progress=prog, progress_args=(c, d, p.id, st))
        
        if not f or not os.path.exists(f):
            await c.edit_message_text(d, p.id, '❌ Download failed.')
            return 'Failed.'
        
        try:
            await c.edit_message_text(d, p.id, '⚙️ Processing file...')
        except Exception:
            pass

        if f and os.path.exists(f):
            f = await rename_file(f, d, p)
        
        fsize = os.path.getsize(f) / (1024 * 1024 * 1024)
        th = thumbnail(d)
        
        if fsize > 2 and Y:
            st = time.time()
            await c.edit_message_text(d, p.id, '⚡ File is larger than 2GB. Uploading via userbot...')
            await upd_dlg(Y)
            mtd = await get_video_metadata(f)
            dur, h, w = mtd['duration'], mtd['width'], mtd['height']
            th = await screenshot(f, dur, d)
            
            send_funcs = {'video': Y.send_video, 'video_note': Y.send_video_note, 
                        'voice': Y.send_voice, 'audio': Y.send_audio, 
                        'photo': Y.send_photo, 'document': Y.send_document}
            
            for mtype, func in send_funcs.items():
                if f.endswith('.mp4'): mtype = 'video'
                if getattr(m, mtype, None):
                    sent = await func(LOG_GROUP, f, thumb=th if mtype == 'video' else None, 
                                    duration=dur if mtype == 'video' else None,
                                    height=h if mtype == 'video' else None,
                                    width=w if mtype == 'video' else None,
                                    caption=ft if m.caption and mtype not in ['video_note', 'voice'] else None, 
                                    parse_mode=ParseMode.MARKDOWN,
                                    progress=prog, progress_args=(c, d, p.id, st))
                    break
            else:
                sent = await Y.send_document(LOG_GROUP, f, thumb=th, caption=ft if m.caption else None, parse_mode=ParseMode.MARKDOWN,
                                            progress=prog, progress_args=(c, d, p.id, st))
            
            await c.copy_message(tcid, LOG_GROUP, sent.id, reply_to_message_id=rtmid)
            if sent:
                try:
                    usr = await c.get_users(uid)
                    await c.send_message(LOG_GROUP, text=f"👤 **Extracted by:** [{usr.first_name}](tg://user?id={uid})\n🆔 **User ID:** `{uid}`", reply_to_message_id=sent.id)
                except Exception:
                    pass
            if os.path.exists(f): os.remove(f)
            cleanup_temp_thumb(th)
            await c.delete_messages(d, p.id)
            return 'Done.'
        
        await c.edit_message_text(d, p.id, '🚀 Uploading to Telegram...')
        st = time.time()
        sent = None

        try:
            mtd = await get_video_metadata(f) if (m.video or f.endswith('.mp4') or f.endswith('.mkv')) else {'duration': None, 'width': None, 'height': None}
            dur, h, w = mtd.get('duration'), mtd.get('width'), mtd.get('height')
            if not th and dur:
                th = await screenshot(f, dur, d)

            # 1. Try sending with bot (c) to target chat (tcid)
            try:
                sent = await send_media_file(c, tcid, f, m, ft, th, dur, h, w, prog, p, d, st, rtmid)
            except Exception as bot_err:
                err_text = str(bot_err)
                is_peer_err = any(k in err_text for k in [
                    "Peer id invalid", "PEER_ID_INVALID", "CHAT_ADMIN_REQUIRED",
                    "CHANNEL_INVALID", "ChannelPrivate", "USER_IS_BLOCKED", "ChatAdminRequired"
                ])
                if is_peer_err and tcid != int(d):
                    logger.warning(f"Bot failed sending to target chat {tcid} ({err_text}). Attempting userbot fallback...")
                    fallback_u = u if (u and u != c) else Y
                    if fallback_u:
                        try:
                            sent = await send_media_file(fallback_u, tcid, f, m, ft, th, dur, h, w, prog, p, d, st, rtmid)
                            logger.info(f"Userbot successfully uploaded to target chat {tcid}.")
                        except Exception as fb_err:
                            logger.error(f"Userbot fallback send also failed: {fb_err}")
                    
                    if not sent:
                        # Fallback to user private chat so media is never lost!
                        try:
                            await c.edit_message_text(d, p.id, '⚠️ टारगेट चैनल में बोट के पास भेजने की अनुमति नहीं मिली। फ़ाइल आपकी प्राइवेट चैट में भेजी जा रही है...')
                            sent = await send_media_file(c, int(d), f, m, ft, th, dur, h, w, prog, p, d, st, None)
                        except Exception:
                            raise bot_err
                else:
                    raise bot_err
        except asyncio.CancelledError:
            if os.path.exists(f): os.remove(f)
            cleanup_temp_thumb(th)
            return 'Cancelled.'
        except Exception as e:
            err_msg = str(e)
            if "USER_IS_BLOCKED" in err_msg or "Peer id invalid" in err_msg:
                await c.edit_message_text(d, p.id, '❌ Upload failed: Peer ID invalid. Make sure the bot is added to your target channel!')
            else:
                await c.edit_message_text(d, p.id, f'❌ Upload failed: {err_msg[:40]}')
            if os.path.exists(f): os.remove(f)
            cleanup_temp_thumb(th)
            return 'Failed.'

        if os.path.exists(f):
            os.remove(f)
        cleanup_temp_thumb(th)
            
        if sent:
            await log_to_channel(c, u, uid, sent)

        try:
            await c.delete_messages(d, p.id)
        except Exception:
            pass
        return 'Done.'
    except Exception as e:
        err_msg = str(e)
        if "USER_IS_BLOCKED" in err_msg or "Peer id invalid" in err_msg:
            return 'Error: Target chat invalid. Make sure bot is in target channel.'
        return f'Error: {err_msg[:50]}'

@X.on_message(filters.command(['batch', 'single']))
async def process_cmd(c, m):
    # Ensure queue processor is running
    if not hasattr(process_cmd, "queue_started"):
        asyncio.create_task(process_queue())
        process_cmd.queue_started = True
    uid = m.from_user.id
    cmd = m.command[0]
    
    if await sub(c, m) == 1: return

    can_extract, reason = await can_user_extract(uid)
    if not can_extract:
        await m.reply_text(reason)
        return
    
    user_data = await get_user_data(uid)
    has_session = bool(user_data and user_data.get("session_string"))
    from config import STRING
    if not has_session and uid not in UC and not STRING:
        await m.reply_text("⚠️ **Login Required**\n\nYou must login using /login to extract links.")
        return
        
    if is_user_active(uid):
        await m.reply_text('⚠️ You have an active task. Use /stop to cancel it.')
        return
    
    Z[uid] = {'step': 'start' if cmd == 'batch' else 'start_single'}
    await m.reply_text(f'👉 Send {"start link of batch..." if cmd == "batch" else "link you want to process"}.')

@X.on_message(filters.command(['cancel', 'stop']))
async def cancel_cmd(c, m):
    uid = m.from_user.id
    if is_user_active(uid):
        if await request_batch_cancel(uid):
            await m.reply_text('✅ Cancellation requested. The current batch will stop shortly.')
        else:
            await m.reply_text('❌ Failed to request cancellation. Please try again.')
    else:
        await m.reply_text('ℹ️ No active batch process found.')

@X.on_message(filters.text & filters.private & ~login_in_progress & ~settings_in_progress & ~filters.command([
    'start', 'batch', 'cancel', 'login', 'logout', 'stop', 'set', 
    'pay', 'redeem', 'gencode', 'single', 'generate', 'keyinfo', 'encrypt', 'decrypt', 'keys', 'setbot', 'rembot',
    'settings', 'setting', 'config',
    'setchatid', 'chatid', 'setchannel', 'channel', 'target', 'settarget', 'remchatid', 'delchatid', 'clearchatid',
    'deleteword', 'deletewords', 'delete', 'del', 'delword', 'remword', 'remdelete', 'cleardelete', 'clearwords',
    'setreplacement', 'setreplace', 'replace', 'replaceword', 'replacement', 'remreplacement', 'clearreplacement', 'clearreplace',
    'setcaption', 'caption', 'remcaption',
    'setrename', 'rename', 'remrename',
    'setthumb', 'thumb', 'remthumb', 'delthumb',
    'reset', 'resetall'
]))
async def text_handler(c, m):
    uid = m.from_user.id
    if await sub(c, m) == 1: return

    s = Z.get(uid, {}).get('step')

    # If user sent a link directly without clicking a button or typing /single
    if not s:
        L = (m.text or "").strip()
        i, d, lt = E(L)
        if i and d:
            can_extract, reason = await can_user_extract(uid)
            if not can_extract:
                await m.reply_text(reason)
                return
            s = 'start_single'
            Z[uid] = {'step': 'start_single'}
        else:
            return

    if s == 'start':
        L = m.text.strip()
        i, d, lt = E(L)
        if not i or not d:
            await m.reply_text('❌ Invalid link format. Please send a valid telegram link.')
            Z.pop(uid, None)
            return
        Z[uid].update({'step': 'count', 'cid': i, 'sid': d, 'lt': lt})
        await m.reply_text('🔢 How many messages to extract? (Enter number)')

    elif s == 'start_single':
        L = m.text.strip()
        i, d, lt = E(L)
        if not i or not d:
            await m.reply_text('❌ Invalid link format. Please send a valid telegram link.')
            Z.pop(uid, None)
            return

        # Check daily extraction limit for free users
        can_extract, reason = await can_user_extract(uid)
        if not can_extract:
            await m.reply_text(reason)
            Z.pop(uid, None)
            return

        if is_user_active(uid):
            await m.reply_text('⚠️ Active task exists. Use /stop first.')
            Z.pop(uid, None)
            return

        pt = await m.reply_text('⏳ Processing link...')
        
        # Fair Queue: max 3 concurrent users
        await acquire_task_slot(uid, pt)

        uc = await get_uclient(uid)
        from config import STRING
        if not uc and not STRING:
            ud = await get_user_data(uid)
            if ud and ud.get('session_string'):
                await pt.edit('⚠️ आपका लॉगिन डेटाबेस में सुरक्षित है, लेकिन टेलीग्राम से कनेक्ट करने में क्षणिक समस्या आई। कृपया कुछ सेकंड बाद पुनः प्रयास करें या /login से नया सेशन डालें।')
            else:
                await pt.edit('⚠️ **Login Required**\n\nYou must login using /login to extract links.')
            release_task_slot(uid)
            Z.pop(uid, None)
            return
            
        try:
            from utils.func import extract_topic_id
            topic_id = extract_topic_id(L)
            msg = await get_msg(c, uc, i, d, lt, topic_id=topic_id)
            if msg:
                res = await process_msg(c, uc, msg, str(m.chat.id), lt, uid, i)
                try:
                    await pt.delete()
                except Exception:
                    pass
                await m.reply_text(f'✅ Extracted: {res or "Done."}')
                # Record successful extraction count for user
                await record_user_extraction(uid)
            else:
                await pt.edit('❌ Message not found or unable to access.')
        except Exception as e:
            await pt.edit(f'❌ Error: {str(e)[:100]}')
        finally:
            release_task_slot(uid)
            Z.pop(uid, None)

    elif s == 'count':
        if not m.text.strip().isdigit():
            await m.reply_text('❌ Please enter a valid number.')
            return
        
        count = int(m.text.strip())
        if count <= 0:
            await m.reply_text('❌ Please enter a number greater than 0.')
            return
            
        is_prem = await is_premium_user(uid)
        maxlimit = PREMIUM_LIMIT if is_prem else FREEMIUM_LIMIT
        if not is_prem and count > 1:
            await m.reply_text("⚠️ **प्रीमियम आवश्यक (Premium Required)**\n\nफ्री यूज़र्स केवल 1 फाइल निकाल सकते हैं।\n24*7 असीमित फाइलों के लिए प्रीमियम लें! 💎\n\n👉 प्लान्स देखने के लिए /plan टाइप करें।")
            return
        elif is_prem and count > maxlimit:
            await m.reply_text(f'⚠️ Maximum batch limit is {maxlimit}.')
            return

        # Check daily limit for free user before starting batch
        can_extract, reason = await can_user_extract(uid)
        if not can_extract:
            await m.reply_text(reason)
            Z.pop(uid, None)
            return

        Z[uid].update({'step': 'process', 'did': str(m.chat.id), 'num': count})
        i, s, n, lt = Z[uid]['cid'], Z[uid]['sid'], Z[uid]['num'], Z[uid]['lt']
        success = 0

        pt = await m.reply_text(f'⏳ Starting batch of {n} messages...')
        
        # Fair Queue: max 3 concurrent users
        await acquire_task_slot(uid, pt)

        uc = await get_uclient(uid)
        from config import STRING
        if not uc and not STRING:
            ud = await get_user_data(uid)
            if ud and ud.get('session_string'):
                await pt.edit('⚠️ आपका लॉगिन डेटाबेस में सुरक्षित है, लेकिन टेलीग्राम से कनेक्ट करने में क्षणिक समस्या आई। कृपया कुछ सेकंड बाद पुनः प्रयास करें या /login से नया सेशन डालें।')
            else:
                await pt.edit('⚠️ **Login Required**\n\nYou must login using /login to extract links.')
            release_task_slot(uid)
            Z.pop(uid, None)
            return
            
        if is_user_active(uid):
            await pt.edit('⚠️ Active task exists. Use /stop first.')
            release_task_slot(uid)
            Z.pop(uid, None)
            return
        
        await add_active_batch(uid, {
            "total": n,
            "current": 0,
            "success": 0,
            "cancel_requested": False,
            "progress_message_id": pt.id
        })
        
        try:
            j = 0
            attempts = 0
            max_attempts = n * 10  # Prevent infinite loop if all are empty/text
            
            while success < n and attempts < max_attempts:
                if should_cancel(uid):
                    await pt.edit(f'🛑 Batch cancelled. Success: {success}/{n}')
                    break
                
                await update_batch_progress(uid, success, success)
                mid = int(s) + j
                j += 1
                attempts += 1
                
                try:
                    try:
                        await pt.edit(f'⏳ **Processing...** ({success}/{n} files extracted)')
                    except Exception:
                        pass
                    msg = await get_msg(c, uc, i, mid, lt)
                    if msg:
                        has_media = getattr(msg, "media", None) is not None
                        # Don't skip if it has text, let it process
                        if not has_media and not getattr(msg, "text", None):
                            continue
                            
                        res = await process_msg(c, uc, msg, str(m.chat.id), lt, uid, i)
                        if res and any(x in res for x in ['Done', 'Copied', 'Sent', 'Forwarded']):
                            success += 1
                            await record_user_extraction(uid)
                            if not is_prem and success >= 1:
                                await m.reply_text(
                                    "⚠️ **फ्री ट्रायल लिमिट समाप्त (Daily Limit Reached)** ⚠️\n"
                                    "━━━━━━━━━━━━━━━━━━━━\n"
                                    "आपकी 1 मुफ़्त फ़ाइल सफलतापूर्वक निकाल ली गई है!\n"
                                    "💎 **24*7 असीमित (Unlimited) फ़ाइल्स निकालने के लिए प्रीमियम लें!**\n\n"
                                    "👉 प्लान्स देखने के लिए: **/plan**"
                                )
                                break
                except asyncio.CancelledError:
                    await pt.edit(f'🛑 Batch cancelled. Success: {success}/{n}')
                    break
                except Exception as e:
                    pass
                
                await asyncio.sleep(2)
            
            if attempts >= max_attempts and success < n:
                await m.reply_text(f'⚠️ **Batch Stopped!**\n\nReached maximum scan attempts. Successfully saved: {success}/{n}')
            else:
                await m.reply_text(f'🎉 **Batch Completed!**\n\n✅ Successfully saved: {success}/{n}')
        finally:
            release_task_slot(uid)
            await remove_active_batch(uid)
            Z.pop(uid, None)



