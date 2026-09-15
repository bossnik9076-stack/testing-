# Copyright (c) 2025 devgagan : https://github.com/devgaganin.  
# Licensed under the GNU General Public License v3.0.  
# See LICENSE file in the repository root for full license text.

import os, re, time, asyncio, json, asyncio 
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import UserNotParticipant
from pyrogram.enums import ParseMode
from config import API_ID, API_HASH, LOG_GROUP, STRING, FORCE_SUB, FREEMIUM_LIMIT, PREMIUM_LIMIT
from utils.func import get_user_data, screenshot, thumbnail, get_video_metadata
from utils.func import get_user_data_key, process_text_with_rules, is_premium_user, E
from shared_client import app as X
from plugins.settings import rename_file
from plugins.start import subscribe as sub
from utils.custom_filters import login_in_progress
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

async def upd_dlg(c):
    try:
        async for _ in c.get_dialogs(limit=100): pass
        return True
    except Exception as e:
        print(f'Failed to update dialogs: {e}')
        return False

# fixed the old group of 2021-2022 extraction 🌝 (buy krne ka fayda nhi ab old group) ✅ 
async def get_msg(c, u, i, d, lt):
    try:
        if lt == 'public':
            try:
                # First try with bot client c
                try:
                    xm = await c.get_messages(i, d)
                    if xm and not getattr(xm, "empty", False):
                        return xm
                except Exception:
                    pass
                
                # If bot couldn't fetch, try with userbot u
                client_to_use = u if u else None
                if client_to_use:
                    try:
                        xm = await client_to_use.get_messages(i, d)
                        if xm and not getattr(xm, "empty", False):
                            return xm
                    except Exception:
                        pass
                    try:
                        await client_to_use.join_chat(i)
                        chat = await client_to_use.get_chat(f"@{i}" if not str(i).startswith('@') else i)
                        xm = await client_to_use.get_messages(chat.id, d)
                        if xm and not getattr(xm, "empty", False):
                            return xm
                    except Exception:
                        pass
                return None
            except Exception as e:
                print(f'Error fetching public message: {e}')
                return None
        else:
            # Private channel
            client_to_use = u if u else None
            if client_to_use:
                try:
                    cid_str = str(i).strip()
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

                try:
                    result = await client_to_use.get_messages(cid_int, d)
                    if result and not getattr(result, "empty", False):
                        return result
                except Exception:
                    pass

                try:
                    async for _ in client_to_use.get_dialogs(limit=50): pass
                    result = await client_to_use.get_messages(cid_int, d)
                    if result and not getattr(result, "empty", False):
                        return result
                except Exception:
                    pass

                try:
                    base_id = str(cid_str).replace('-100', '').replace('-', '')
                    alt_cid = int(f"-{base_id}")
                    result = await client_to_use.get_messages(alt_cid, d)
                    if result and not getattr(result, "empty", False):
                        return result
                except Exception:
                    pass

                return None
            return None
    except Exception as e:
        print(f'Error fetching message: {e}')
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
    ud = await get_user_data(uid)
    cl = UC.get(uid)
    if cl: return cl
    xxx = ud.get('session_string') if ud else None
    if xxx:
        try:
            ss = dcs(xxx)
            gg = Client(f'{uid}_client', api_id=API_ID, api_hash=API_HASH, device_model="v3saver", session_string=ss, in_memory=True)
            await gg.start()
            await upd_dlg(gg)
            UC[uid] = gg
            return gg
        except Exception as e:
            print(f'User client error: {e}')
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
            await C.edit_message_text(h, m, f"__**Transferring File...**__\n\n{bar}\n\n⚡ **Completed**: {c_mb:.2f} MB / {t_mb:.2f} MB\n📊 **Progress**: {p:.2f}%\n🚀 **Speed**: {speed:.2f} MB/s\n⏳ **ETA**: {eta}")
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

async def process_msg(c, u, m, d, lt, uid, i):
    try:
        cfg_chat = await get_user_data_key(d, 'chat_id', None)
        tcid = int(d)
        rtmid = None
        if cfg_chat:
            try:
                if '/' in str(cfg_chat):
                    parts = str(cfg_chat).split('/', 1)
                    tcid = int(parts[0])
                    rtmid = int(parts[1]) if len(parts) > 1 else None
                else:
                    tcid = int(cfg_chat)
            except Exception:
                tcid = int(d)
        
        orig_text = m.caption.markdown if m.caption else (m.text.markdown if m.text else '')
        proc_text = await process_text_with_rules(d, orig_text)
        user_cap = await get_user_data_key(d, 'caption', '')
        ft = f'{proc_text}\n\n{user_cap}' if proc_text and user_cap else user_cap if user_cap else proc_text

        # PUBLIC LINK -> DIRECT FORWARD / COPY AS REQUESTED
        if lt == 'public':
            try:
                # 1. Try bot copy_message
                try:
                    sent = await c.copy_message(chat_id=tcid, from_chat_id=i, message_id=m.id, caption=ft if ft else None, parse_mode=ParseMode.MARKDOWN, reply_to_message_id=rtmid)
                    if sent:
                        return 'Forwarded directly.'
                except Exception:
                    pass
                
                # 2. Try bot forward_messages
                try:
                    sent = await c.forward_messages(chat_id=tcid, from_chat_id=i, message_ids=m.id)
                    if sent:
                        return 'Forwarded directly.'
                except Exception:
                    pass

                # 3. Try userbot copy_message
                if u and u != c:
                    try:
                        sent = await u.copy_message(chat_id=tcid, from_chat_id=i, message_id=m.id, caption=ft if ft else None, parse_mode=ParseMode.MARKDOWN, reply_to_message_id=rtmid)
                        if sent:
                            return 'Forwarded directly.'
                    except Exception:
                        pass
                    try:
                        sent = await u.forward_messages(chat_id=tcid, from_chat_id=i, message_ids=m.id)
                        if sent:
                            return 'Forwarded directly.'
                    except Exception:
                        pass
            except Exception as e:
                print(f"Public copy/forward error: {e}")
            # If direct copy was restricted by channel, fall through to download & upload

        # If it is a text-only message (no media)
        if not m.media:
            if m.text:
                await c.send_message(tcid, text=ft if ft else m.text.markdown, reply_to_message_id=rtmid)
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

        if (
            (m.video and m.video.file_name) or
            (m.audio and m.audio.file_name) or
            (m.document and m.document.file_name)
        ):
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
            if th and isinstance(th, str) and os.path.exists(th) and (th.startswith("thumb_") or th.startswith("temp_thumb_")):
                try: os.remove(th)
                except Exception: pass
            await c.delete_messages(d, p.id)
            return 'Done.'
        
        await c.edit_message_text(d, p.id, '🚀 Uploading to Telegram...')
        st = time.time()
        sent = None

        try:
            video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.ogv']
            audio_extensions = ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.opus', '.aiff', '.ac3']
            file_ext = os.path.splitext(f)[1].lower()
            if m.video or (m.document and file_ext in video_extensions):
                mtd = await get_video_metadata(f)
                dur, h, w = mtd['duration'], mtd['width'], mtd['height']
                th = await screenshot(f, dur, d)
                sent = await c.send_video(tcid, video=f, caption=ft if ft else (m.caption.markdown if m.caption else None), parse_mode=ParseMode.MARKDOWN, 
                                thumb=th, width=w, height=h, duration=dur, 
                                progress=prog, progress_args=(c, d, p.id, st), 
                                reply_to_message_id=rtmid)
            elif m.video_note:
                sent = await c.send_video_note(tcid, video_note=f, progress=prog, 
                                    progress_args=(c, d, p.id, st), reply_to_message_id=rtmid)
            elif m.voice:
                sent = await c.send_voice(tcid, f, progress=prog, progress_args=(c, d, p.id, st), 
                                reply_to_message_id=rtmid)
            elif m.sticker:
                sent = await c.send_sticker(tcid, m.sticker.file_id, reply_to_message_id=rtmid)
            elif m.audio or (m.document and file_ext in audio_extensions):
                sent = await c.send_audio(tcid, audio=f, caption=ft if ft else (m.caption.markdown if m.caption else None), parse_mode=ParseMode.MARKDOWN, 
                                thumb=th, progress=prog, progress_args=(c, d, p.id, st), 
                                reply_to_message_id=rtmid)
            elif m.photo:
                sent = await c.send_photo(tcid, photo=f, caption=ft if ft else (m.caption.markdown if m.caption else None), parse_mode=ParseMode.MARKDOWN, 
                                progress=prog, progress_args=(c, d, p.id, st), 
                                reply_to_message_id=rtmid)
            elif m.document:
                sent = await c.send_document(tcid, document=f, caption=ft if ft else (m.caption.markdown if m.caption else None), parse_mode=ParseMode.MARKDOWN, 
                                    progress=prog, progress_args=(c, d, p.id, st), 
                                    reply_to_message_id=rtmid)
            else:
                sent = await c.send_document(tcid, document=f, caption=ft if ft else (m.caption.markdown if m.caption else None), parse_mode=ParseMode.MARKDOWN, 
                                    progress=prog, progress_args=(c, d, p.id, st), 
                                    reply_to_message_id=rtmid)
        except asyncio.CancelledError:
            if os.path.exists(f): os.remove(f)
            return 'Cancelled.'
        except Exception as e:
            err_msg = str(e)
            if "USER_IS_BLOCKED" in err_msg or "Peer id invalid" in err_msg:
                await c.edit_message_text(d, p.id, '❌ Upload failed: Peer ID invalid. Make sure the bot is added to your target channel!')
            else:
                await c.edit_message_text(d, p.id, f'❌ Upload failed: {err_msg[:40]}')
            if os.path.exists(f): os.remove(f)
            if th and isinstance(th, str) and os.path.exists(th) and (th.startswith("thumb_") or th.startswith("temp_thumb_")):
                try: os.remove(th)
                except Exception: pass
            return 'Failed.'

        if os.path.exists(f):
            os.remove(f)
        if th and isinstance(th, str) and os.path.exists(th) and (th.startswith("thumb_") or th.startswith("temp_thumb_")):
            try: os.remove(th)
            except Exception: pass
            
        if sent:
            try:
                log_msg = await c.copy_message(LOG_GROUP, from_chat_id=tcid, message_id=sent.id)
                usr = await c.get_users(uid)
                await c.send_message(LOG_GROUP, text=f"👤 **Extracted by:** [{usr.first_name}](tg://user?id={uid})\n🆔 **User ID:** `{uid}`", reply_to_message_id=log_msg.id)
            except Exception as log_e:
                print(f"Error logging: {log_e}")

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
    uid = m.from_user.id
    cmd = m.command[0]
    
    if await sub(c, m) == 1: return
    
    uc = await get_uclient(uid)
    if not uc:
        await m.reply_text("⚠️ **Login Required**\n\nYou must login using /login to extract links. The bot's internal session is disabled for downloading.")
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

@X.on_message(filters.text & filters.private & ~login_in_progress & ~filters.command([
    'start', 'batch', 'cancel', 'login', 'logout', 'stop', 'set', 
    'pay', 'redeem', 'gencode', 'single', 'generate', 'keyinfo', 'encrypt', 'decrypt', 'keys', 'setbot', 'rembot']))
async def text_handler(c, m):
    uid = m.from_user.id
    if await sub(c, m) == 1: return

    s = Z.get(uid, {}).get('step')

    # If user sent a link directly without clicking a button or typing /single
    if not s:
        L = (m.text or "").strip()
        i, d, lt = E(L)
        if i and d:
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

        if is_user_active(uid):
            await m.reply_text('⚠️ Active task exists. Use /stop first.')
            Z.pop(uid, None)
            return

        pt = await m.reply_text('⏳ Processing link...')
        
        uc = await get_uclient(uid)
        if not uc:
            await pt.edit('⚠️ **Login Required**\n\nYou must login using /login to extract links. The bot\'s internal session is disabled for downloading.')
            Z.pop(uid, None)
            return
            
        try:
            msg = await get_msg(c, uc, i, d, lt)
            if msg:
                res = await process_msg(c, uc, msg, str(m.chat.id), lt, uid, i)
                try:
                    await pt.delete()
                except Exception:
                    pass
                await m.reply_text(f'✅ Extracted: {res}')
            else:
                await pt.edit('❌ Message not found or unable to access.')
        except Exception as e:
            await pt.edit(f'❌ Error: {str(e)[:100]}')
        finally:
            Z.pop(uid, None)

    elif s == 'count':
        if not m.text.strip().isdigit():
            await m.reply_text('❌ Please enter a valid number.')
            return
        
        count = int(m.text.strip())
        if count <= 0:
            await m.reply_text('❌ Please enter a number greater than 0.')
            return
            
        maxlimit = PREMIUM_LIMIT
        if count > maxlimit:
            await m.reply_text(f'⚠️ Maximum batch limit is {maxlimit}.')
            return

        Z[uid].update({'step': 'process', 'did': str(m.chat.id), 'num': count})
        i, s, n, lt = Z[uid]['cid'], Z[uid]['sid'], Z[uid]['num'], Z[uid]['lt']
        success = 0

        pt = await m.reply_text(f'⏳ Starting batch of {n} messages...')
        uc = await get_uclient(uid)
        if not uc:
            await pt.edit('⚠️ **Login Required**\n\nYou must login using /login to extract links. The bot\'s internal session is disabled for downloading.')
            Z.pop(uid, None)
            return
            
        if is_user_active(uid):
            await pt.edit('⚠️ Active task exists. Use /stop first.')
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
                    msg = await get_msg(c, uc, i, mid, lt)
                    if msg:
                        has_media = getattr(msg, "media", None) is not None
                        if not has_media:
                            try:
                                await pt.edit(f'📦 Batch Progress: {success}/{n} (Msg {mid} text/empty skipped) | ✅ Success: {success}')
                            except Exception:
                                pass
                            continue
                            
                        res = await process_msg(c, uc, msg, str(m.chat.id), lt, uid, i)
                        if 'Done' in res or 'Copied' in res or 'Sent' in res or 'Forwarded' in res:
                            success += 1
                        try:
                            await pt.edit(f'📦 Batch Progress: {success}/{n} | ✅ Success: {success}')
                        except Exception:
                            pass
                    else:
                        try:
                            await pt.edit(f'📦 Batch Progress: {success}/{n} (Msg {mid} not found) | ✅ Success: {success}')
                        except Exception:
                            pass
                except asyncio.CancelledError:
                    await pt.edit(f'🛑 Batch cancelled. Success: {success}/{n}')
                    break
                except Exception as e:
                    try:
                        await pt.edit(f'📦 Batch Progress: {success}/{n}: Error - {str(e)[:40]}')
                    except Exception:
                        pass
                
                await asyncio.sleep(2)
            
            if attempts >= max_attempts and success < n:
                await m.reply_text(f'⚠️ **Batch Stopped!**\n\nReached maximum scan attempts. Successfully saved: {success}/{n}')
            else:
                await m.reply_text(f'🎉 **Batch Completed!**\n\n✅ Successfully saved: {success}/{n}')
        finally:
            await remove_active_batch(uid)
            Z.pop(uid, None)



