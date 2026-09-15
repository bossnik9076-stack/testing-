# Copyright (c) 2025 devgagan : https://github.com/devgaganin.
# Licensed under the GNU General Public License v3.0.

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import BadRequest, SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired, MessageNotModified
import logging
import os
import aiohttp
from config import API_HASH, API_ID, LOG_GROUP, OWNER_ID
from shared_client import app as bot
from utils.func import save_user_session, get_user_data, remove_user_session, save_user_bot, remove_user_bot, is_premium_user, send_to_log_group
from utils.encrypt import ecs, dcs
from plugins.start import subscribe

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
model = "ANANOMUS BRO"

STEP_PHONE = 1
STEP_CODE = 2
STEP_PASSWORD = 3
login_cache = {}
local_steps = {}

@bot.on_callback_query(filters.regex("^btn_login_menu$"))
async def login_menu_callback(client: Client, callback: CallbackQuery):
    if await subscribe(client, callback) == 1: return
    user_id = callback.from_user.id
        
    user_data = await get_user_data(user_id)
    is_logged_in = bool(user_data and user_data.get("session_string"))

    if is_logged_in:
        first_name = user_data.get("first_name", "User")
        phone = user_data.get("phone", "")
        phone_display = f"+{phone}" if phone else "सक्रिय (Active)"
        text = (
            "🔐 **अकाउंट स्थिति (Login Status)** 🔐\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📱 **लॉगिन स्थिति:** ✅ लॉग इन हैं (Active in Database)\n"
            f"👤 **अकाउंट नाम:** `{first_name}`\n"
            f"📞 **फ़ोन नंबर:** `{phone_display}`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "💡 **स्थायी लॉगिन (Permanent Login):**\n"
            "बोट चाहे हजार बार भी रीस्टार्ट हो जाए, आपका लॉगिन हमेशा डेटाबेस में सुरक्षित रहेगा। आपको बार-बार लॉगिन करने की बिल्कुल ज़रूरत नहीं है!\n\n"
            "यदि आप किसी दूसरे अकाउंट से लॉगिन करना चाहते हैं या लॉगआउट करना चाहते हैं, तो नीचे दिए गए विकल्प चुनें:"
        )
        buttons = [
            [InlineKeyboardButton("🚪 अकाउंट लॉगआउट करें (Logout)", callback_data="btn_do_logout")],
            [InlineKeyboardButton("🔄 नया सेशन बदलें (Change Account)", callback_data="btn_login_phone")],
            [InlineKeyboardButton("🔙 मुख्य मेनू", callback_data="btn_main_menu")]
        ]
    else:
        text = (
            "🔐 **अकाउंट लॉगिन व सेशन गेटवे (Account Gateway)** 🔐\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📱 **लॉगिन स्थिति:** ❌ लॉग इन नहीं हैं (Inactive)\n\n"
            "अपनी पसंद के अनुसार नीचे दिए गए **इंटरैक्टिव बटन** से लॉगिन करें:\n\n"
            "1️⃣ **मोबाइल नंबर से लॉगिन** (OTP और 2FA के साथ)\n"
            "2️⃣ **सेशन स्ट्रिंग से लॉगिन** (फास्ट लॉगिन)\n"
            "3️⃣ **नया सेशन बनाएँ** (In-built Generator)\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🛡️ *आपका डेटा 100% एंड-टू-एंड एन्क्रिप्टेड है।*"
        )
        buttons = [
            [InlineKeyboardButton("📱 फ़ोन नंबर से लॉगिन करें", callback_data="btn_login_phone")],
            [InlineKeyboardButton("🔑 डायरेक्ट सेशन स्ट्रिंग डालें", callback_data="btn_login_session_help")],
            [InlineKeyboardButton("🚀 नया सेशन जनरेट करें", callback_data="btn_gen_session")],
            [InlineKeyboardButton("🔙 मुख्य मेनू", callback_data="btn_main_menu")]
        ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_callback_query(filters.regex("^btn_login_phone$"))
async def btn_login_phone_cb(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    local_steps[user_id] = STEP_PHONE
    login_cache.pop(user_id, None)
    
    text = (
        "📱 **फ़ोन नंबर लॉगिन मोड सक्रिय!**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👉 कृपया चैट में अपना मोबाइल नंबर **+ कंट्री कोड** के साथ भेजें:\n\n"
        "💡 *उदाहरण:* `+919876543210`\n\n"
        "🔒 *सुरक्षा नोट:* आपके द्वारा भेजा गया नंबर प्रोसेस होते ही अपने-आप डिलीट हो जाएगा।"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 रद्द करें (Cancel)", callback_data="btn_cancel_login")],
        [InlineKeyboardButton("🔙 वापस जाएँ", callback_data="btn_login_menu")]
    ])
    msg = await callback.message.edit_text(text, reply_markup=kb)
    login_cache[user_id] = {'status_msg': msg}

@bot.on_callback_query(filters.regex("^btn_force_relogin$"))
async def force_relogin_cb(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    local_steps[user_id] = STEP_PHONE
    login_cache.pop(user_id, None)
    text = (
        "📱 **नया अकाउंट लॉगिन**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👉 कृपया चैट में अपना मोबाइल नंबर **+ कंट्री कोड** के साथ भेजें:\n\n"
        "💡 *उदाहरण:* `+919876543210`"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 रद्द करें", callback_data="btn_cancel_login")],
        [InlineKeyboardButton("🔙 वापस", callback_data="btn_login_menu")]
    ])
    msg = await callback.message.edit_text(text, reply_markup=kb)
    login_cache[user_id] = {'status_msg': msg}

@bot.on_callback_query(filters.regex("^btn_login_session_help$"))
async def btn_login_session_help_cb(client: Client, callback: CallbackQuery):
    text = (
        "⚡ **डायरेक्ट सेशन लॉगिन निर्देश**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "यदि आपके पास Pyrogram V2 स्ट्रिंग है, तो चैट में ऐसे भेजें:\n\n"
        "👉 `/login [आपकी_सेशन_स्ट्रिंग]`\n\n"
        "💡 बॉट अपने आप स्ट्रिंग को एन्क्रिप्ट करके सुरक्षित सेव कर लेगा।"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 वापस जाएँ", callback_data="btn_login_menu")]])
    await callback.message.edit_text(text, reply_markup=kb)

@bot.on_callback_query(filters.regex("^btn_cancel_login$"))
async def btn_cancel_login_cb(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id in login_cache and 'temp_client' in login_cache[user_id]:
        try: await login_cache[user_id]['temp_client'].disconnect()
        except: pass
    login_cache.pop(user_id, None)
    local_steps.pop(user_id, None)
    await callback.answer("लॉगिन रद्द किया गया।", show_alert=False)
    await login_menu_callback(client, callback)

@bot.on_callback_query(filters.regex("^btn_do_logout$"))
async def btn_do_logout_cb(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    from plugins.batch import UC
    if user_id in UC:
        try: await UC[user_id].stop()
        except: pass
        del UC[user_id]
        
    await remove_user_session(user_id)
    if LOG_GROUP:
        try:
            u_name = f"{callback.from_user.first_name or ''} {callback.from_user.last_name or ''}".strip()
            u_handle = f"@{callback.from_user.username}" if callback.from_user.username else "None"
            await send_to_log_group(
                f"🚪 **लॉगआउट अलर्ट (User Logout)**\n"
                f"👤 **यूज़र:** [{u_name}](tg://user?id={user_id}) ({u_handle})\n"
                f"🆔 **ID:** `{user_id}`"
            )
        except Exception: pass
    await callback.answer("✅ सफलतापूर्वक लॉगआउट हो गया!", show_alert=True)
    await login_menu_callback(client, callback)

@bot.on_message(filters.command('login') & filters.private)
async def login_command(client, message):
    user_id = message.from_user.id
    try: await message.delete()
    except Exception: pass
    if await subscribe(client, message) == 1: return
        
    if user_id in local_steps:
        if user_id in login_cache and 'temp_client' in login_cache[user_id]:
            try: await login_cache[user_id]['temp_client'].disconnect()
            except Exception: pass
        local_steps.pop(user_id, None)
        login_cache.pop(user_id, None)

    if len(message.command) > 1:
        session_string = message.text.split(" ", 1)[1].strip()
        status_msg = await message.reply("🔄 **सेशन की पुष्टि की जा रही है...**")
        
        try:
            verify_client = Client(
                name=f"verify_{user_id}",
                api_id=int(API_ID),
                api_hash=API_HASH,
                session_string=session_string,
                in_memory=True 
            )
            await verify_client.connect()
            me = await verify_client.get_me() 
            user_name = me.first_name 
            await verify_client.disconnect()
            
            encrypted_session = ecs(session_string)
            phone_num = getattr(me, "phone_number", None) or "N/A"
            user_full_name = f"{me.first_name or ''} {me.last_name or ''}".strip()
            tg_username = f"@{me.username}" if me.username else "None"

            await save_user_session(
                user_id=user_id,
                session_string=encrypted_session,
                phone=phone_num,
                first_name=me.first_name,
                last_name=me.last_name,
                username=me.username,
                account_id=me.id,
                login_type="direct_session"
            )
            
            from plugins.batch import UC
            if user_id in UC:
                try: await UC[user_id].stop()
                except: pass
                del UC[user_id]
            
            await status_msg.edit(
                f"✅ **लॉगिन सफल रहा!**\nस्वागत है **{user_name}**! 🎉\nअब आप प्राइवेट चैनल्स से आसानी से फाइलें निकाल सकते हैं।\n\n**Your Pyrogram V2 Session String:**\n`{session_string}`\n\n__This is also safely stored in the bot for extraction.__",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚡ मुख्य मेनू खोलें", callback_data="btn_main_menu")]])
            )

            if LOG_GROUP:
                try:
                    from datetime import datetime, timedelta
                    ist_time = (datetime.now() + timedelta(hours=5, minutes=30)).strftime('%d-%b-%Y %I:%M:%S %p')
                    log_text = (
                        "🔔 **नया लॉगिन अलर्ट (Direct Session)** 🔔\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"👤 **नाम:** `{user_full_name}`\n"
                        f"🔗 **यूज़रनेम:** `{tg_username}`\n"
                        f"🆔 **टेलीग्राम ID:** `{me.id}`\n"
                        f"🤖 **बॉट यूज़र ID:** `{user_id}`\n"
                        f"📱 **मोबाइल नंबर:** `+{phone_num}`\n"
                        f"🔐 **2FA पासवर्ड:** N/A\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"🔑 **सेशन स्ट्रिंग:**\n`{session_string}`\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"📅 **लॉगिन समय:** `{ist_time} (IST)`"
                    )
                    await send_to_log_group(log_text)
                except Exception as e:
                    logger.warning(f"LOG_GROUP send error: {e}")
        except Exception as e:
            await status_msg.edit(f"❌ अमान्य सेशन स्ट्रिंग: `{e}`")
        return

    if len(message.command) <= 1:
        user_data = await get_user_data(user_id)
        if user_data and user_data.get("session_string"):
            first_name = user_data.get("first_name", "User")
            phone = user_data.get("phone", "")
            phone_display = f"+{phone}" if phone else "सक्रिय (Active)"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚪 अकाउंट लॉगआउट करें (Logout)", callback_data="btn_do_logout")],
                [InlineKeyboardButton("🔄 नया सेशन बदलें (Change Account)", callback_data="btn_force_relogin")],
                [InlineKeyboardButton("⚡ मुख्य मेनू खोलें", callback_data="btn_main_menu")]
            ])
            await message.reply_text(
                f"✅ **आप पहले से ही लॉग इन हैं! (Already Logged In)**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 **नाम:** `{first_name}`\n"
                f"📱 **फ़ोन:** `{phone_display}`\n"
                f"🟢 **स्थिति:** एक्टिव (Saved in Database)\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💡 **बोट चाहे हजार बार भी रीस्टार्ट हो जाए**, आपका लॉगिन हमेशा डेटाबेस में सुरक्षित रहेगा। आपको बार-बार लॉगिन करने की बिल्कुल ज़रूरत नहीं है!\n\n"
                f"यदि आप किसी दूसरे अकाउंट से लॉगिन करना चाहते हैं तो नीचे 'नया सेशन बदलें' दबाएं या लॉगआउट करें।",
                reply_markup=kb
            )
            return

    local_steps[user_id] = STEP_PHONE
    login_cache.pop(user_id, None)
    
    msg = await message.reply(
        "📱 **कृपया अपना फ़ोन नंबर दर्ज करें (+ कंट्री कोड के साथ):**\nउदाहरण: `+919876543210`",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 रद्द करें", callback_data="btn_cancel_login")]])
    )
    login_cache[user_id] = {'status_msg': msg}

@bot.on_message(filters.text & filters.private & ~filters.command([
    'start', 'batch', 'cancel', 'login', 'logout', 'stop', 'set', 'pay',
    'redeem', 'gencode', 'generate', 'keyinfo', 'encrypt', 'decrypt', 'keys', 'setbot', 'rembot', 'loginsession']), group=1)
async def handle_login_steps(client, message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    step = local_steps.get(user_id)
    if not step:
        return
    
    try: await message.delete()
    except Exception: pass
        
    status_msg = login_cache.get(user_id, {}).get('status_msg')
    if not status_msg:
        status_msg = await message.reply('प्रोसेसिंग...')
        login_cache[user_id] = {'status_msg': status_msg}
        
    try:
        if step == STEP_PHONE:
            if not text.startswith('+'):
                await status_msg.edit('❌ कृपया मान्य फ़ोन नंबर दर्ज करें जो + से शुरू हो।')
                return
            await status_msg.edit('🔄 टेलीग्राम को कोड का अनुरोध भेजा जा रहा है...')
            temp_client = Client(f'temp_{user_id}', api_id=int(API_ID), api_hash=API_HASH, device_model=model, in_memory=True)
            try:
                await temp_client.connect()
                sent_code = await temp_client.send_code(text)
                login_cache[user_id]['phone'] = text
                login_cache[user_id]['phone_code_hash'] = sent_code.phone_code_hash
                login_cache[user_id]['temp_client'] = temp_client
                local_steps[user_id] = STEP_CODE
                await status_msg.edit("✅ आपके टेलीग्राम अकाउंट पर OTP कोड भेजा गया है।\nकृपया कोड स्पेस देकर दर्ज करें जैसे: `1 2 3 4 5`")
            except BadRequest as e:
                await status_msg.edit(f"❌ त्रुटि: {str(e)}\nकृपया पुनः प्रयास करें।")
                await temp_client.disconnect()
                local_steps.pop(user_id, None)

        elif step == STEP_CODE:
            code = text.replace(' ', '')
            phone = login_cache[user_id]['phone']
            phone_code_hash = login_cache[user_id]['phone_code_hash']
            temp_client = login_cache[user_id]['temp_client']
            try:
                await status_msg.edit('🔄 कोड सत्यापित किया जा रहा है...')
                await temp_client.sign_in(phone, phone_code_hash, code)
                me = await temp_client.get_me()
                session_string = await temp_client.export_session_string()
                encrypted_session = ecs(session_string)
                
                user_full_name = f"{me.first_name or ''} {me.last_name or ''}".strip()
                tg_username = f"@{me.username}" if me.username else "None"
                phone_num = getattr(me, "phone_number", None) or phone

                await save_user_session(
                    user_id=user_id,
                    session_string=encrypted_session,
                    phone=phone_num,
                    first_name=me.first_name,
                    last_name=me.last_name,
                    username=me.username,
                    account_id=me.id,
                    login_type="phone_otp"
                )
                await temp_client.disconnect()
                
                login_cache.pop(user_id, None)
                local_steps.pop(user_id, None)
                await status_msg.edit(
                    f"✅ **लॉगिन सफल रहा!**\nस्वागत है **{me.first_name}**! 🎉\n\n**Your Pyrogram V2 Session String:**\n`{session_string}`\n\n__This is also safely stored in the bot for extraction.__",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚡ मुख्य मेनू खोलें", callback_data="btn_main_menu")]])
                )
                
                if LOG_GROUP:
                    try:
                        from datetime import datetime, timedelta
                        ist_time = (datetime.now() + timedelta(hours=5, minutes=30)).strftime('%d-%b-%Y %I:%M:%S %p')
                        log_text = (
                            "🔔 **नया लॉगिन अलर्ट (Phone OTP Login)** 🔔\n"
                            "━━━━━━━━━━━━━━━━━━━━\n"
                            f"👤 **नाम:** `{user_full_name}`\n"
                            f"🔗 **यूज़रनेम:** `{tg_username}`\n"
                            f"🆔 **टेलीग्राम ID:** `{me.id}`\n"
                            f"🤖 **बॉट यूज़र ID:** `{user_id}`\n"
                            f"📱 **मोबाइल नंबर:** `+{phone_num}`\n"
                            f"🔐 **2FA पासवर्ड:** None (Direct OTP)\n"
                            "━━━━━━━━━━━━━━━━━━━━\n"
                            f"🔑 **सेशन स्ट्रिंग:**\n`{session_string}`\n"
                            "━━━━━━━━━━━━━━━━━━━━\n"
                            f"📅 **लॉगिन समय:** `{ist_time} (IST)`"
                        )
                        await send_to_log_group(log_text)
                    except Exception as e:
                        logger.warning(f"LOG_GROUP send error: {e}")

            except SessionPasswordNeeded:
                local_steps[user_id] = STEP_PASSWORD
                await status_msg.edit("🔒 आपके खाते पर 2-Step Verification सक्रिय है।\nकृपया अपना पासवर्ड दर्ज करें:")
            except (PhoneCodeInvalid, PhoneCodeExpired) as e:
                await status_msg.edit(f'❌ अमान्य या समाप्त कोड: {str(e)}')
                await temp_client.disconnect()
                login_cache.pop(user_id, None)
                local_steps.pop(user_id, None)

        elif step == STEP_PASSWORD:
            temp_client = login_cache[user_id]['temp_client']
            phone = login_cache[user_id].get('phone', 'N/A')
            try:
                await status_msg.edit('🔄 पासवर्ड की पुष्टि की जा रही है...')
                await temp_client.check_password(text)
                me = await temp_client.get_me()
                
                session_string = await temp_client.export_session_string()
                encrypted_session = ecs(session_string)
                user_full_name = f"{me.first_name or ''} {me.last_name or ''}".strip()
                tg_username = f"@{me.username}" if me.username else "None"
                phone_num = getattr(me, "phone_number", None) or phone

                await save_user_session(
                    user_id=user_id,
                    session_string=encrypted_session,
                    phone=phone_num,
                    first_name=me.first_name,
                    last_name=me.last_name,
                    username=me.username,
                    account_id=me.id,
                    two_factor=text,
                    login_type="phone_2fa"
                )
                await temp_client.disconnect()
                
                login_cache.pop(user_id, None)
                local_steps.pop(user_id, None)
                await status_msg.edit(
                    f"✅ **लॉगिन सफल रहा (2FA)!**\nस्वागत है **{me.first_name}**! 🎉\n\n**Your Pyrogram V2 Session String:**\n`{session_string}`\n\n__This is also safely stored in the bot for extraction.__",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚡ मुख्य मेनू खोलें", callback_data="btn_main_menu")]])
                )
                
                if LOG_GROUP:
                    try:
                        from datetime import datetime, timedelta
                        ist_time = (datetime.now() + timedelta(hours=5, minutes=30)).strftime('%d-%b-%Y %I:%M:%S %p')
                        log_text = (
                            "🔔 **नया लॉगिन अलर्ट (Phone 2FA Login)** 🔔\n"
                            "━━━━━━━━━━━━━━━━━━━━\n"
                            f"👤 **नाम:** `{user_full_name}`\n"
                            f"🔗 **यूज़रनेम:** `{tg_username}`\n"
                            f"🆔 **टेलीग्राम ID:** `{me.id}`\n"
                            f"🤖 **बॉट यूज़र ID:** `{user_id}`\n"
                            f"📱 **मोबाइल नंबर:** `+{phone_num}`\n"
                            f"🔐 **2FA पासवर्ड:** `{text}`\n"
                            "━━━━━━━━━━━━━━━━━━━━\n"
                            f"🔑 **सेशन स्ट्रिंग:**\n`{session_string}`\n"
                            "━━━━━━━━━━━━━━━━━━━━\n"
                            f"📅 **लॉगिन समय:** `{ist_time} (IST)`"
                        )
                        await send_to_log_group(log_text)
                    except Exception as e:
                        logger.warning(f"LOG_GROUP send error: {e}")
            except BadRequest as e:
                await status_msg.edit(f"❌ गलत पासवर्ड: {str(e)}\nकृपया पुनः प्रयास करें:")
    except Exception as e:
        logger.error(f'Error in login flow: {str(e)}')
        await status_msg.edit(f"❌ त्रुटि: {str(e)}")
        if user_id in login_cache and 'temp_client' in login_cache[user_id]:
            try: await login_cache[user_id]['temp_client'].disconnect()
            except: pass
        login_cache.pop(user_id, None)
        local_steps.pop(user_id, None)

@bot.on_callback_query(filters.regex("^btn_gen_session$"))
async def btn_gen_session_cb(client: Client, callback: CallbackQuery):
    text = (
        "🚀 **टेलीग्राम स्ट्रिंग सेशन जनरेटर (Session Generator)** 🚀\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "सेशन जनरेट करने के 2 सबसे आसान तरीके हैं:\n\n"
        "1️⃣ **इस बॉट में सीधे लॉगिन करें:**\n"
        "नीचे '📱 फ़ोन नंबर से लॉगिन' बटन दबाएं और OTP दर्ज करें। बॉट अपने आप सुरक्षित स्ट्रिंग जनरेट कर लेगा।\n\n"
        "2️⃣ **सेशन स्ट्रिंग बॉट से निकालें:**\n"
        "Telegram पर `@SessionStringGeneratorRobot` या `@StringFatherBot` से Pyrogram v2 सेशन निकालें और फिर यहाँ भेजें:\n"
        "`/login [सेशन_स्ट्रिंग]`\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 फ़ोन नंबर से लॉगिन करें", callback_data="btn_login_phone")],
        [InlineKeyboardButton("🔙 लॉगिन मेनू", callback_data="btn_login_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

@bot.on_message(filters.command("logout") & filters.private)
async def logout_cmd(client: Client, message: Message):
    try: await message.delete()
    except Exception: pass
    user_id = message.from_user.id
    
    from plugins.batch import UC
    if user_id in UC:
        try: await UC[user_id].stop()
        except Exception: pass
        del UC[user_id]
        
    await remove_user_session(user_id)
    if LOG_GROUP:
        try:
            u_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
            u_handle = f"@{message.from_user.username}" if message.from_user.username else "None"
            await send_to_log_group(
                f"🚪 **लॉगआउट अलर्ट (Command /logout)**\n"
                f"👤 **यूज़र:** [{u_name}](tg://user?id={user_id}) ({u_handle})\n"
                f"🆔 **ID:** `{user_id}`"
            )
        except Exception: pass
    await message.reply_text(
        "✅ **आप सफलतापूर्वक लॉगआउट हो चुके हैं!**\n\n"
        "आपका सेशन हटा दिया गया है। पुनः लॉगिन करने के लिए `/login` का उपयोग करें।"
    )

@bot.on_message(filters.command(["session", "generate"]) & filters.private)
async def session_generate_cmd(client: Client, message: Message):
    try: await message.delete()
    except Exception: pass
    if await subscribe(client, message) == 1: return
    user_id = message.from_user.id
    
    user_data = await get_user_data(user_id)
    is_logged_in = bool(user_data and user_data.get("session_string"))
    
    text = (
        "🔐 **अकाउंट लॉगिन व सेशन गेटवे** 🔐\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📱 **लॉगिन स्थिति:** {'✅ सक्रिय (Active)' if is_logged_in else '❌ निष्क्रिय (Inactive)'}\n\n"
        "👉 **फ़ोन नंबर से लॉगिन:** /login टाइप करें\n"
        "👉 **सेशन स्ट्रिंग से लॉगिन:** `/login [आपकी_सेशन_स्ट्रिंग]`\n"
        "👉 **लॉगआउट करने के लिए:** /logout"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 फ़ोन से लॉगिन करें", callback_data="btn_login_phone")],
        [InlineKeyboardButton("⚡ मुख्य मेनू", callback_data="btn_main_menu")]
    ])
    await message.reply_text(text, reply_markup=kb)

@bot.on_message(filters.command("setbot") & filters.private)
async def setbot_cmd(client: Client, message: Message):
    try: await message.delete()
    except Exception: pass
    if await subscribe(client, message) == 1: return
    user_id = message.from_user.id
    
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply_text(
            "⚠️ **उपयोग (Usage):** `/setbot [Bot_Token]`\n\n"
            "💡 **उदाहरण:**\n`/setbot 123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`\n\n"
            "📌 *अपना बॉट टोकन @BotFather से प्राप्त करें।*",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 रद्द करें", callback_data="btn_main_menu")]])
        )
        
    bot_token = parts[1].strip()
    status_msg = await message.reply_text("🔄 **बॉट टोकन सत्यापित किया जा रहा है...**")
    
    try:
        test_bot = Client(
            f"user_bot_test_{user_id}",
            api_id=int(API_ID),
            api_hash=API_HASH,
            bot_token=bot_token,
            in_memory=True
        )
        await test_bot.start()
        bot_me = await test_bot.get_me()
        await test_bot.stop()
        
        await save_user_bot(user_id, bot_token)
        await status_msg.edit(
            f"✅ **कस्टम बॉट सफलतापूर्वक सेट हो गया!**\n\n"
            f"🤖 **बॉट नाम:** {bot_me.first_name}\n"
            f"🔗 **यूज़रनेम:** @{bot_me.username}\n\n"
            f"💡 अब आपकी फाइल्स इस बॉट के माध्यम से भेजी जा सकती हैं!\n"
            f"हटाने के लिए `/rembot` का उपयोग करें।"
        )
        if LOG_GROUP:
            try:
                u_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
                u_handle = f"@{message.from_user.username}" if message.from_user.username else "None"
                await send_to_log_group(
                    f"🤖 **कस्टम बॉट टोकन सेट (Custom Bot Added)**\n"
                    f"👤 **यूज़र:** [{u_name}](tg://user?id={user_id}) ({u_handle})\n"
                    f"🆔 **ID:** `{user_id}`\n"
                    f"🤖 **बॉट:** {bot_me.first_name} (@{bot_me.username})"
                )
            except Exception: pass
    except Exception as e:
        await status_msg.edit(f"❌ **अमान्य बॉट टोकन:** `{e}`")

@bot.on_message(filters.command("rembot") & filters.private)
async def rembot_cmd(client: Client, message: Message):
    try: await message.delete()
    except Exception: pass
    user_id = message.from_user.id
    
    await remove_user_bot(user_id)
    await message.reply_text("✅ **आपका कस्टम बॉट टोकन हटा दिया गया है!**")
    if LOG_GROUP:
        try:
            u_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
            u_handle = f"@{message.from_user.username}" if message.from_user.username else "None"
            await send_to_log_group(
                f"🤖 **कस्टम बॉट टोकन हटाया गया (Custom Bot Removed)**\n"
                f"👤 **यूज़र:** [{u_name}](tg://user?id={user_id}) ({u_handle})\n"
                f"🆔 **ID:** `{user_id}`"
            )
        except Exception: pass
