# Copyright (c) 2025 devgagan : https://github.com/devgaganin.
# Licensed under the GNU General Public License v3.0.
# See LICENSE file in the repository root for full license text.

import os
import time
import random
import asyncio
from datetime import datetime, timedelta
from shared_client import app
from pyrogram import Client, filters
from pyrogram.errors import UserNotParticipant, MessageNotModified
from pyrogram.types import (
    BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
)
from config import LOG_GROUP, OWNER_ID, FORCE_SUB, JOIN_LINK, ADMIN_CONTACT
from utils.func import (
    users_collection, db, premium_users_collection, is_banned,
    get_premium_details, is_premium_user, get_user_data_key, get_user_data,
    send_to_log_group
)

user_sub_cache = {}

async def subscribe(client: Client, message_or_cb) -> int:
    user_id = message_or_cb.from_user.id if message_or_cb.from_user else None
    if not user_id:
        return 0

    from config import OWNER_ID
    if isinstance(OWNER_ID, list):
        if user_id in OWNER_ID or str(user_id) in [str(x) for x in OWNER_ID]:
            return 0
    elif str(user_id) == str(OWNER_ID):
        return 0

    if not FORCE_SUB:
        return 0

    if await is_banned(user_id):
        if isinstance(message_or_cb, CallbackQuery):
            await message_or_cb.answer("❌ You are BANNED from using this bot.", show_alert=True)
        else:
            await message_or_cb.reply_text("❌ **You are BANNED from using this bot.**")
        return 1

    now = time.time()
    if user_id in user_sub_cache and (now - user_sub_cache[user_id]) < 30:
        return 0

    try:
        ch1 = FORCE_SUB if FORCE_SUB else "nikbotchannel"
        await client.get_chat_member(ch1, user_id)
        await client.get_chat_member("niksupportgroup", user_id)
        
        user_sub_cache[user_id] = now
        return 0
    except UserNotParticipant:
        link1 = JOIN_LINK if JOIN_LINK else "https://t.me/nikbotchannel"
        link2 = "https://t.me/niksupportgroup"

        caption = (
            "⚠️ **Access Denied! / एक्सेस अस्वीकृत!** ⚠️\n\n"
            "📢 बॉट का उपयोग करने के लिए आपको हमारे **दोनों चैनल्स** को जॉइन करना अनिवार्य है:\n\n"
            "1️⃣ **मुख्य चैनल (Updates Channel)**\n"
            "2️⃣ **सपोर्ट ग्रुप (Support Group)**\n\n"
            "👇 नीचे दिए गए बटनों से जॉइन करें और फिर **'🔄 Verify (सत्यापित करें)'** पर क्लिक करें!"
        )
        
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📢 Join Channel 1", url=link1),
                InlineKeyboardButton("📢 Join Channel 2", url=link2)
            ],
            [
                InlineKeyboardButton("🔄 Verify / चेक करें", callback_data="verify_sub")
            ]
        ])
        
        if isinstance(message_or_cb, CallbackQuery):
            await message_or_cb.answer("❌ कृपया पहले दोनों चैनल जॉइन करें!", show_alert=True)
            try:
                await message_or_cb.message.reply_photo(
                    photo="https://i.postimg.cc/mrhQv1tF/752d3ef5-a5bb-4239-83f5-4f835dc824fa.jpg",
                    caption=caption,
                    reply_markup=kb
                )
            except Exception:
                await message_or_cb.message.reply_text(caption, reply_markup=kb)
        else:
            try:
                await message_or_cb.reply_photo(
                    photo="https://i.postimg.cc/mrhQv1tF/752d3ef5-a5bb-4239-83f5-4f835dc824fa.jpg",
                    caption=caption,
                    reply_markup=kb
                )
            except Exception:
                await message_or_cb.reply_text(caption, reply_markup=kb)
        return 1
    except Exception:
        return 0

START_IMAGES = [
    "https://i.postimg.cc/8Pm34W5q/download.jpg",
    "https://i.postimg.cc/nLgwrGR0/download.jpg",
    "https://i.postimg.cc/Bbchh9qL/download.jpg",
    "https://i.postimg.cc/RV4pWFRD/download.jpg",
    "https://i.postimg.cc/KYSMYK7x/download.jpg",
    "https://i.postimg.cc/Z53WXbkZ/download.jpg",
    "https://i.postimg.cc/W1M4X5Zx/download.jpg",
    "https://i.postimg.cc/25kCTrrL/download.jpg"
]

def get_main_menu_keyboard(is_owner: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("📥 Single Extract", callback_data="btn_single"),
            InlineKeyboardButton("📦 Batch Extract", callback_data="btn_batch")
        ],
        [
            InlineKeyboardButton("🔑 Login / Session", callback_data="btn_login_menu"),
            InlineKeyboardButton("⚙️ Custom Settings", callback_data="btn_settings_menu")
        ],
        [
            InlineKeyboardButton("📊 My Limits & Plan", callback_data="btn_mylimit"),
            InlineKeyboardButton("💎 VIP Plans", callback_data="see_plan")
        ],
        [
            InlineKeyboardButton("🎟️ Redeem Code", callback_data="btn_redeem_guide"),
            InlineKeyboardButton("🛑 Force Stop Task", callback_data="btn_force_stop")
        ],
        [
            InlineKeyboardButton("⚡ Server Speedtest", callback_data="btn_speedtest"),
            InlineKeyboardButton("❓ Help & Guide", callback_data="btn_help")
        ],
        [
            InlineKeyboardButton("☎️ Contact Admin", url="https://t.me/ananomusbro")
        ]
    ]
    if is_owner:
        buttons.insert(0, [InlineKeyboardButton("👑 Owner Admin Panel", callback_data="btn_owner_panel")])
    return InlineKeyboardMarkup(buttons)

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    try: await message.delete()
    except Exception: pass
    
    if await subscribe(client, message) == 1:
        return

    is_owner = False
    if isinstance(OWNER_ID, list):
        is_owner = user_id in OWNER_ID or str(user_id) in [str(x) for x in OWNER_ID]
    else:
        is_owner = str(user_id) == str(OWNER_ID)

    welcome_text = (
        "⚡ **स्वागत है Ananomus BRO Saver v3 में!** ⚡\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🚀 **सुपरफास्ट और लाइटवेट कंटेंट सेवर बॉट**\n\n"
        "✨ अब आपको कमांड टाइप करने की कोई ज़रूरत नहीं है! नीचे दिए गए **इंटरैक्टिव बटनों** से सीधे सब कुछ नियंत्रित करें:\n\n"
        "• 📥 **Single Extract**: किसी भी पोस्ट का लिंक सीधे भेजें\n"
        "• 📦 **Batch Extract**: एक साथ हज़ारों फाइलें निकालें\n"
        "• 🔄 **Auto Forward**: किसी भी चैनल के संदेश सीधे अपने चैनल में भेजें\n"
        "• 🔑 **Login / Session**: प्राइवेट/रिस्ट्रिक्टेड चैनल एक्सेस करें\n"
        "• ⚙️ **Settings**: थंबनेल, रीनेम टैग, कैप्शन, वाटरमार्क सेट करें\n"
        "• 📊 **My Limits**: अपना कोटा और एक्टिव प्लान चेक करें\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💡 *शुरू करने के लिए नीचे दिए गए किसी भी बटन पर क्लिक करें:* 👇"
    )

    random_photo = random.choice(START_IMAGES)
    kb = get_main_menu_keyboard(is_owner)

    if LOG_GROUP:
        try:
            u_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
            u_handle = f"@{message.from_user.username}" if message.from_user.username else "None"
            ist_now = (datetime.now() + timedelta(hours=5, minutes=30)).strftime('%d-%b-%Y %I:%M:%S %p')
            start_log = (
                f"⚡ **बॉट स्टार्ट लॉग (/start)**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 **यूज़र:** [{u_name}](tg://user?id={user_id}) ({u_handle})\n"
                f"🆔 **यूज़र ID:** `{user_id}`\n"
                f"📅 **समय:** `{ist_now} (IST)`"
            )
            await send_to_log_group(start_log)
        except Exception:
            pass

    try:
        await message.reply_photo(
            photo=random_photo,
            caption=welcome_text,
            reply_markup=kb
        )
    except Exception:
        await message.reply_text(welcome_text, reply_markup=kb)

@app.on_callback_query(filters.regex("^verify_sub$"))
async def verify_sub_callback(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    user_sub_cache.pop(user_id, None)
    
    if await subscribe(client, callback) == 0:
        await callback.answer("✅ बहुत बढ़िया! आप दोनों चैनल से जुड़े हुए हैं।", show_alert=True)
        try:
            await callback.message.delete()
        except Exception:
            pass
        
        is_owner = False
        if isinstance(OWNER_ID, list):
            is_owner = user_id in OWNER_ID or str(user_id) in [str(x) for x in OWNER_ID]
        else:
            is_owner = str(user_id) == str(OWNER_ID)
            
        welcome_text = (
            "✅ **वेरिफिकेशन सफल रहा!**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "अब आप बॉट की सभी सुविधाओं का आनंद ले सकते हैं। कृपया नीचे दिए गए विकल्पों में से चुनें:"
        )
        await client.send_message(user_id, welcome_text, reply_markup=get_main_menu_keyboard(is_owner))

@app.on_callback_query(filters.regex("^btn_single$"))
async def btn_single_cb(client: Client, callback: CallbackQuery):
    if await subscribe(client, callback) == 1: return
    user_id = callback.from_user.id
    user_data = await get_user_data(user_id)
    has_session = bool(user_data and user_data.get("session_string"))
    from plugins.batch import UC
    from config import STRING
    if not has_session and user_id not in UC and not STRING:
        await callback.answer("⚠️ Login Required! Please login first using /login.", show_alert=True)
        return
    from plugins.batch import Z
    Z[user_id] = {'step': 'start_single'}
    
    text = (
        "📥 **सिंगल लिंक एक्सट्रैक्टर (Single Extract Mode)**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👉 कृपया उस **पब्लिक या प्राइवेट पोस्ट का लिंक** चैट में भेजें जिसे आप डाउनलोड करना चाहते हैं।\n\n"
        "💡 *उदाहरण:* `https://t.me/c/1234567890/123` या `https://t.me/channel_name/123`"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 रद्द करें (Cancel)", callback_data="btn_cancel_step")],
        [InlineKeyboardButton("🔙 मुख्य मेनू (Main Menu)", callback_data="btn_main_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

@app.on_callback_query(filters.regex("^btn_batch$"))
async def btn_batch_cb(client: Client, callback: CallbackQuery):
    if await subscribe(client, callback) == 1: return
    user_id = callback.from_user.id
    user_data = await get_user_data(user_id)
    has_session = bool(user_data and user_data.get("session_string"))
    from plugins.batch import UC
    from config import STRING
    if not has_session and user_id not in UC and not STRING:
        await callback.answer("⚠️ Login Required! Please login first using /login.", show_alert=True)
        return
        
    from plugins.batch import Z
    Z[user_id] = {'step': 'start'}
    
    text = (
        "📦 **बैच एक्सट्रैक्टर (Bulk Batch Extract Mode)**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👉 कृपया बैच का **प्रारंभिक लिंक (Start Link)** चैट में भेजें:\n\n"
        "💡 *उदाहरण:* `https://t.me/c/1234567890/100`"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 रद्द करें (Cancel)", callback_data="btn_cancel_step")],
        [InlineKeyboardButton("🔙 मुख्य मेनू (Main Menu)", callback_data="btn_main_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

@app.on_callback_query(filters.regex("^btn_cancel_step$"))
async def btn_cancel_step_cb(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    from plugins.batch import Z
    from utils.custom_filters import set_settings_step, set_user_step
    Z.pop(user_id, None)
    set_settings_step(user_id, None)
    set_user_step(user_id, None)
    await callback.answer("✅ प्रक्रिया रद्द कर दी गई।", show_alert=False)
    await show_main_menu(client, callback)

@app.on_callback_query(filters.regex("^btn_main_menu$"))
async def btn_main_menu_cb(client: Client, callback: CallbackQuery):
    if await subscribe(client, callback) == 1: return
    await show_main_menu(client, callback)

async def show_main_menu(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    is_owner = False
    if isinstance(OWNER_ID, list):
        is_owner = user_id in OWNER_ID or str(user_id) in [str(x) for x in OWNER_ID]
    else:
        is_owner = str(user_id) == str(OWNER_ID)
        
    text = (
        "⚡ **Ananomus BRO v3 - मुख्य डैशबोर्ड** ⚡\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "कृपया नीचे दिए गए विकल्पों में से चुनें:"
    )
    try:
        await callback.message.edit_text(text, reply_markup=get_main_menu_keyboard(is_owner))
    except Exception:
        await callback.message.reply_text(text, reply_markup=get_main_menu_keyboard(is_owner))

@app.on_callback_query(filters.regex("^btn_mylimit$"))
async def btn_mylimit_cb(client: Client, callback: CallbackQuery):
    if await subscribe(client, callback) == 1: return
    user_id = callback.from_user.id
    
    premium_details = await get_premium_details(user_id)
    if not premium_details:
        text = (
            "📊 **आपकी उपयोग सीमा (Free Tier)** 📊\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👤 **प्लान:** फ्री यूज़र (Free User)\n"
            "🎁 **दैनिक कोटा:** रोज़ 1 फ्री ट्रायल\n"
            "⚡ **अधिकतम साइज:** स्टैंडर्ड\n\n"
            "👉 असीमित डाउनलोड और बैच के लिए प्रीमियम लें: /plan"
        )
    else:
        start_date = premium_details.get("subscription_start")
        end_date = premium_details.get("subscription_end")
        plan_type = premium_details.get("plan_type", "Pro")
        
        total_days = 1
        if start_date and end_date:
            total_days = max(1, (end_date - start_date).days)
            
        total_limit = "असीमित (Unlimited)" if plan_type == "Pro" else f"{total_days * 250} Files"
        used_files = await get_user_data_key(user_id, "used_files", 0)
        
        expiry_ist = end_date + timedelta(hours=5, minutes=30) if end_date else "N/A"
        formatted_expiry = expiry_ist.strftime('%d-%b-%Y %I:%M:%S %p') if end_date else "N/A"
        
        text = (
            f"📊 **आपकी प्रीमियम स्थिति (VIP Status)** 📊\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👑 **प्लान:** `{plan_type} VIP`\n"
            f"📦 **कोटा:** `{total_limit}`\n"
            f"✅ **डाउनलोड की गई फाइलें:** `{used_files}`\n"
            f"⏳ **वैधता (Expiry):** `{formatted_expiry} (IST)`\n\n"
            f"✨ आपके पास सभी VIP फीचर्स का पूरा एक्सेस है!"
        )
        
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 VIP Plans देखें", callback_data="see_plan")],
        [InlineKeyboardButton("🔙 मुख्य मेनू", callback_data="btn_main_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

@app.on_callback_query(filters.regex("^btn_force_stop$"))
async def btn_force_stop_cb(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    from plugins.batch import is_user_active, request_batch_cancel
    
    if is_user_active(user_id):
        if await request_batch_cancel(user_id):
            await callback.answer("🛑 रनिंग टास्क रोक दिया गया है!", show_alert=True)
            await callback.message.edit_text(
                "🛑 **टास्क सफलतापूर्वक रोक दिया गया!**\n\n"
                "✅ चल रही डाउनलोडिंग तुरंत निरस्त कर दी गई है और अधूरी फाइलें हटा दी गई हैं。",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 मुख्य मेनू", callback_data="btn_main_menu")]])
            )
        else:
            await callback.answer("⚠️ टास्क रोकने में त्रुटि!", show_alert=True)
    else:
        await callback.answer("ℹ️ आपका कोई सक्रिय टास्क नहीं चल रहा है।", show_alert=True)

@app.on_callback_query(filters.regex("^btn_speedtest$"))
async def btn_speedtest_cb(client: Client, callback: CallbackQuery):
    if await subscribe(client, callback) == 1: return
    await callback.message.edit_text("⚡ **स्पीड टेस्ट चल रहा है... कृपया 10-15 सेकंड प्रतीक्षा करें...**")
    
    try:
        import speedtest
        def run_st():
            st = speedtest.Speedtest()
            st.get_best_server()
            st.download()
            st.upload()
            return st.results.dict()

        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, run_st)
        
        dl = res['download'] / (1024 * 1024)
        ul = res['upload'] / (1024 * 1024)
        ping = res['ping']
        isp = res['client']['isp']

        msg = (
            f"🚀 **सर्वर स्पीड टेस्ट परिणाम (Server Speed)** 🚀\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔽 **डाउनलोड स्पीड:** `{dl:.2f} Mbps`\n"
            f"🔼 **अपलोड स्पीड:** `{ul:.2f} Mbps`\n"
            f"⏱️ **पिंग (Latency):** `{ping} ms`\n"
            f"🌐 **आईएसपी (ISP):** `{isp}`\n\n"
            f"⚡ *1 vCPU / 1GB RAM ऑप्टिमाइज़्ड इंजन सक्रिय है!*"
        )
    except Exception as e:
        msg = f"❌ स्पीड टेस्ट विफल: `{e}`"
        
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 मुख्य मेनू", callback_data="btn_main_menu")]])
    await callback.message.edit_text(msg, reply_markup=kb)

@app.on_callback_query(filters.regex("^btn_help$"))
async def btn_help_cb(client: Client, callback: CallbackQuery):
    if await subscribe(client, callback) == 1: return
    help_text = (
        "❓ **उपयोग गाइड और निर्देश (User Guide)** ❓\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "1️⃣ **पब्लिक पोस्ट डाउनलोड**: बस किसी भी चैनल का लिंक भेजें।\n"
        "2️⃣ **प्राइवेट चैनल**: 'Login / Session' बटन दबाकर लॉगिन करें, फिर लिंक भेजें।\n"
        "3️⃣ **बैच डाउनलोड**: 'Batch Extract' बटन दबाकर पहला लिंक और संख्या दर्ज करें।\n"
        "4️⃣ **सेटिंग्स**: 'Custom Settings' बटन से अपना रीनेम टैग, थंबनेल और कैप्शन सेट करें।\n"
        "5️⃣ **स्टॉप**: किसी भी समय काम रोकने के लिए 'Force Stop Task' दबाएं।\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💬 किसी भी समस्या के लिए एडमिन से संपर्क करें: @ananomusbro"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 VIP Plans", callback_data="see_plan")],
        [InlineKeyboardButton("🔙 मुख्य मेनू", callback_data="btn_main_menu")]
    ])
    await callback.message.edit_text(help_text, reply_markup=kb)

@app.on_callback_query(filters.regex("^btn_redeem_guide$"))
async def btn_redeem_guide_cb(client: Client, callback: CallbackQuery):
    text = (
        "🎟️ **रिडीम कोड कैसे इस्तेमाल करें?**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "यदि आपके पास प्रीमियम रिडीम कोड है, तो चैट में ऐसे भेजें:\n\n"
        "👉 `/redeem [आपका_कोड]`\n\n"
        "💡 *उदाहरण:* `/redeem ANANOMUS-PRO-87XYZ123`"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 मुख्य मेनू", callback_data="btn_main_menu")]])
    await callback.message.edit_text(text, reply_markup=kb)

@app.on_callback_query(filters.regex("^see_plan$"))
async def see_plan_cb(client: Client, callback: CallbackQuery):
    plan_text = (
        "👑 **ANANOMUSBRO VIP PLANS** 👑\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🌟 **प्रीमियम यूज़र्स के लिए 24*7 असीमित फाइल्स:** 🚀\n\n"
        "📦 **1. BASIC PLAN:**\n"
        "✨ रोज़ाना 24*7 फाइलें निकालें\n"
        "✨ No Daily File Restriction\n"
        "✨ Fast Download Speed\n"
        "✨ Private & Public Channel Support\n"
        "🏆 **कीमत:** एडमिन से संपर्क करें\n\n"
        "🚀 **2. PRO PLAN (अनुशंसित):**\n"
        "✨ असीमित फाइल्स 24*7 (No Limit)\n"
        "✨ Ultra Fast Speed (10-50 Mbps)\n"
        "✨ Bulk Batch Extraction (हज़ारों फाइलें एक साथ)\n"
        "✨ Custom Watermark & Renaming\n"
        "✨ VIP Priority Queue Access\n"
        "🏆 **साप्ताहिक प्रो:** ₹200 (7 दिन)\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "💳 **भुगतान माध्यम:** केवल UPI स्वीकार्य ✅"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 नियम एवं शर्तें (Terms)", callback_data="see_terms")],
        [InlineKeyboardButton("💬 अभी एडमिन से खरीदें", url="https://t.me/ananomusbro")],
        [InlineKeyboardButton("🔙 मुख्य मेनू", callback_data="btn_main_menu")]
    ])
    await callback.message.edit_text(plan_text, reply_markup=kb)

@app.on_callback_query(filters.regex("^see_terms$"))
async def see_terms_cb(client: Client, callback: CallbackQuery):
    terms_text = (
        "📜 **नियम और शर्तें (Terms & Conditions)** 📜\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "1. बॉट केवल उपयोगिता उपकरण के रूप में प्रदान किया गया है।\n"
        "2. कॉपीराइट उल्लंघन के लिए उपयोगकर्ता स्वयं जिम्मेदार होगा।\n"
        "3. सर्वर मेंटेनेंस और टेलीग्राम नियमों के अनुसार प्लान शर्तों में बदलाव संभव है।"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 प्लान्स देखें", callback_data="see_plan")],
        [InlineKeyboardButton("🔙 मुख्य मेनू", callback_data="btn_main_menu")]
    ])
    await callback.message.edit_text(terms_text, reply_markup=kb)

@app.on_message(filters.command("plan") & filters.private)
async def plan_cmd(client: Client, message: Message):
    try: await message.delete()
    except Exception: pass
    if await subscribe(client, message) == 1: return
    plan_text = (
        "👑 **ANANOMUSBRO VIP PLANS** 👑\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📦 **Basic Plan:**\n"
        "✨ 24*7 असीमित फाइल्स\n"
        "✨ Fast Speed & Private Link Support\n\n"
        "🚀 **Pro Plan (अनुशंसित):**\n"
        "✨ 24*7 Unlimited Files\n"
        "✨ Maximum Ultra Fast Speed\n"
        "✨ Bulk Batch Extraction (एक साथ हज़ारों फाइल्स)\n"
        "✨ Custom Watermark & Renaming\n"
        "🏆 **मूल्य:** ₹200 (7 दिन)\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔗 **भुगतान:** केवल UPI स्वीकार्य ✅"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 नियम एवं शर्तें", callback_data="see_terms")],
        [InlineKeyboardButton("💬 एडमिन से संपर्क करें", url="https://t.me/ananomusbro")]
    ])
    await message.reply_text(plan_text, reply_markup=kb)

@app.on_message(filters.command("help") & filters.private)
async def help_cmd(client: Client, message: Message):
    try: await message.delete()
    except Exception: pass
    if await subscribe(client, message) == 1: return
    await message.reply_text(
        "❓ **निर्देश:** कृपया मुख्य मेनू के इंटरैक्टिव बटनों का उपयोग करें। /start दबाएं।",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚡ मुख्य मेनू खोलें", callback_data="btn_main_menu")]])
    )

@app.on_message(filters.command("single") & filters.private)
async def single_cmd(client: Client, message: Message):
    try: await message.delete()
    except Exception: pass
    if await subscribe(client, message) == 1: return
    user_id = message.from_user.id
    from plugins.batch import get_uclient
    uc = await get_uclient(user_id)
    if not uc:
        await message.reply_text("⚠️ **Login Required**\n\nYou must login using /login to extract links.")
        return
    from plugins.batch import Z
    Z[user_id] = {'step': 'start_single'}
    
    text = (
        "📥 **सिंगल लिंक एक्सट्रैक्टर (Single Extract Mode)**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👉 कृपया उस **पब्लिक या प्राइवेट पोस्ट का लिंक** चैट में भेजें जिसे आप डाउनलोड करना चाहते हैं。\n\n"
        "💡 *उदाहरण:* `https://t.me/c/1234567890/123` या `https://t.me/channel_name/123`"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 रद्द करें (Cancel)", callback_data="btn_cancel_step")],
        [InlineKeyboardButton("🔙 मुख्य मेनू", callback_data="btn_main_menu")]
    ])
    await message.reply_text(text, reply_markup=kb)

@app.on_message(filters.command(["myplan", "mylimit"]) & filters.private)
async def myplan_cmd(client: Client, message: Message):
    try: await message.delete()
    except Exception: pass
    if await subscribe(client, message) == 1: return
    user_id = message.from_user.id
    
    premium_details = await get_premium_details(user_id)
    if not premium_details:
        text = (
            "📊 **आपकी उपयोग सीमा (Free Tier)** 📊\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👤 **प्लान:** फ्री यूज़र (Free User)\n"
            "🎁 **दैनिक कोटा:** रोज़ 1 फ्री ट्रायल\n"
            "⚡ **अधिकतम साइज:** स्टैंडर्ड\n\n"
            "👉 असीमित डाउनलोड और बैच के लिए प्रीमियम लें: /plan"
        )
    else:
        start_date = premium_details.get("subscription_start")
        end_date = premium_details.get("subscription_end")
        plan_type = premium_details.get("plan_type", "Pro")
        
        total_days = 1
        if start_date and end_date:
            total_days = max(1, (end_date - start_date).days)
            
        total_limit = "असीमित (Unlimited)" if plan_type == "Pro" else f"{total_days * 250} Files"
        used_files = await get_user_data_key(user_id, "used_files", 0)
        
        expiry_ist = end_date + timedelta(hours=5, minutes=30) if end_date else "N/A"
        formatted_expiry = expiry_ist.strftime('%d-%b-%Y %I:%M:%S %p') if end_date else "N/A"
        
        text = (
            f"📊 **आपकी प्रीमियम स्थिति (VIP Status)** 📊\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👑 **प्लान:** `{plan_type} VIP`\n"
            f"📦 **कोटा:** `{total_limit}`\n"
            f"✅ **डाउनलोड की गई फाइलें:** `{used_files}`\n"
            f"⏳ **वैधता (Expiry):** `{formatted_expiry} (IST)`\n\n"
            f"✨ आपके पास सभी VIP फीचर्स का पूरा एक्सेस है!"
        )
        
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 VIP Plans देखें", callback_data="see_plan")],
        [InlineKeyboardButton("🔙 मुख्य मेनू", callback_data="btn_main_menu")]
    ])
    await message.reply_text(text, reply_markup=kb)

@app.on_message(filters.command("pay") & filters.private)
async def pay_cmd(client: Client, message: Message):
    try: await message.delete()
    except Exception: pass
    if await subscribe(client, message) == 1: return
    
    plan_text = (
        "👑 **ANANOMUSBRO EXCLUSIVE PRO PLAN** 👑\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🌟 **असीमित फीचर्स और स्पीड:** 🚀\n\n"
        "✨ **No Size Limit** (कितनी भी बड़ी फाइल निकालें)\n"
        "✨ **Unlimited Files** (रोज़ असीमित फाइलें डाउनलोड करें)\n"
        "✨ **Ultra Fast Speed** (10-50 Mbps मैक्सिमम थ्रूपुट)\n"
        "✨ **Custom Watermarking** (वीडियो पर अपना टेक्स्ट या लोगो लगाएं)\n"
        "✨ **Private Restricted Access** (प्राइवेट चैनल्स अनलॉक)\n"
        "✨ **Bulk Batch Extraction** (एक साथ हज़ारों फाइलें निकालें)\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "💳 **प्लान मूल्य:**\n"
        "🏆 **साप्ताहिक प्रो प्लान:** ₹200 (7 दिन)\n\n"
        "🔗 **भुगतान माध्यम:** केवल UPI स्वीकार्य ✅\n"
        "💬 खरीदने के लिए एडमिन से संपर्क करें: @ananomusbro"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 नियम एवं शर्तें (Terms)", callback_data="see_terms")],
        [InlineKeyboardButton("💬 अभी एडमिन से खरीदें", url="https://t.me/ananomusbro")],
        [InlineKeyboardButton("🔙 मुख्य मेनू", callback_data="btn_main_menu")]
    ])
    await message.reply_text(plan_text, reply_markup=kb)

@app.on_message(filters.command("speedtest") & filters.private)
async def speedtest_cmd(client: Client, message: Message):
    try: await message.delete()
    except Exception: pass
    if await subscribe(client, message) == 1: return
    
    status_msg = await message.reply_text("⚡ **स्पीड टेस्ट चल रहा है... कृपया 10-15 सेकंड प्रतीक्षा करें...**")
    try:
        import speedtest
        def run_st():
            st = speedtest.Speedtest()
            st.get_best_server()
            st.download()
            st.upload()
            return st.results.dict()

        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, run_st)
        
        dl = res['download'] / (1024 * 1024)
        ul = res['upload'] / (1024 * 1024)
        ping = res['ping']
        isp = res['client']['isp']

        msg = (
            f"🚀 **सर्वर स्पीड टेस्ट परिणाम (Server Speed)** 🚀\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔽 **डाउनलोड स्पीड:** `{dl:.2f} Mbps`\n"
            f"🔼 **अपलोड स्पीड:** `{ul:.2f} Mbps`\n"
            f"⏱️ **पिंग (Latency):** `{ping} ms`\n"
            f"🌐 **आईएसपी (ISP):** `{isp}`\n\n"
            f"⚡ *1 vCPU / 1GB RAM ऑप्टिमाइज़्ड इंजन सक्रिय है!*"
        )
    except Exception as e:
        msg = f"❌ स्पीड टेस्ट विफल: `{e}`"
        
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 मुख्य मेनू", callback_data="btn_main_menu")]])
    await status_msg.edit(msg, reply_markup=kb)
