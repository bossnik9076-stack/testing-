# Copyright (c) 2025 devgagan : https://github.com/devgaganin.
# Licensed under the GNU General Public License v3.0.

import os
import psutil
import platform
import shutil
from datetime import timedelta, datetime
from shared_client import client as bot_client, app
from telethon import events
from pyrogram import filters
from pyrogram.types import Message
from utils.func import get_premium_details, is_private_chat, get_display_name, is_premium_user, premium_users_collection
from config import OWNER_ID
import logging

logger = logging.getLogger('teamspy')

@app.on_message(filters.command("status") & filters.private)
async def pyro_status_handler(client, message: Message):
    try: await message.delete()
    except Exception: pass
    user_id = message.from_user.id
    
    premium_details = await get_premium_details(user_id)
    if premium_details:
        expiry_utc = premium_details["subscription_end"]
        expiry_ist = expiry_utc + timedelta(hours=5, minutes=30)
        formatted_expiry = expiry_ist.strftime("%d-%b-%Y %I:%M:%S %p")
        plan_type = premium_details.get("plan_type", "Pro")
        premium_status = f"✅ प्रीमियम ({plan_type}) वैध: {formatted_expiry} (IST)"
    else:
        premium_status = "❌ फ्री यूज़र (Free User)"
    
    await message.reply_text(
        "📊 **आपकी वर्तमान स्थिति:**\n\n"
        f"👑 **प्रीमियम:** {premium_status}\n"
        f"⚡ **सर्वर थ्रूपुट:** अनुकूलित (Lightweight 1 vCPU / 1GB RAM Engine)"
    )

@app.on_message(filters.command("stats") & filters.private)
async def pyro_server_stats_handler(client, message: Message):
    try: await message.delete()
    except Exception: pass
    user_id = message.from_user.id
    is_owner = user_id in OWNER_ID if isinstance(OWNER_ID, list) else str(user_id) == str(OWNER_ID)
    if not is_owner:
        return await message.reply_text("❌ यह केवल एडमिन के लिए है।")
        
    total, used, free = shutil.disk_usage("/")
    memory = psutil.virtual_memory()
    cpu_usage = psutil.cpu_percent(interval=0.5)
    
    stats_text = (
        f"🖥 **सर्वर लाइव स्टेट्स (VPS Stats)** 🖥\n\n"
        f"**⚙️ OS:** `{platform.system()} {platform.release()}`\n"
        f"**💻 CPU लोड:** `{cpu_usage}%` (1 Core)\n"
        f"**🧠 RAM लोड:** `{memory.percent}%` (1 GB)\n"
        f"**💾 डिस्क उपयोग:** `{used // (1024**3)} GB / {total // (1024**3)} GB`\n"
        f"**⚡ ऑप्टिमाइजेशन:** TgCrypto C-Extensions + Pillow Lightweight Engine\n\n"
        f"**Powered by ANANOMUS BRO**"
    )
    await message.reply_text(stats_text)


if bot_client:
    @bot_client.on(events.NewMessage(pattern='/status'))
    async def status_handler(event):
        try: await event.delete()
        except Exception: pass
        if not await is_private_chat(event): return
        user_id = event.sender_id
        
        premium_details = await get_premium_details(user_id)
        if premium_details:
            expiry_utc = premium_details["subscription_end"]
            expiry_ist = expiry_utc + timedelta(hours=5, minutes=30)
            formatted_expiry = expiry_ist.strftime("%d-%b-%Y %I:%M:%S %p")
            plan_type = premium_details.get("plan_type", "Pro")
            premium_status = f"✅ प्रीमियम ({plan_type}) वैध: {formatted_expiry} (IST)"
        else:
            premium_status = "❌ फ्री यूज़र (Free User)"
        
        await event.respond(
            "📊 **आपकी वर्तमान स्थिति:**\n\n"
            f"👑 **प्रीमियम:** {premium_status}\n"
            f"⚡ **सर्वर थ्रूपुट:** अनुकूलित (Lightweight 1 vCPU / 1GB RAM Engine)"
        )

    @bot_client.on(events.NewMessage(pattern='/stats'))
    async def server_stats_handler(event):
        try: await event.delete()
        except Exception: pass
        if not await is_private_chat(event): return
        user_id = event.sender_id
        is_owner = user_id in OWNER_ID if isinstance(OWNER_ID, list) else str(user_id) == str(OWNER_ID)
        if not is_owner:
            await event.respond("❌ यह केवल एडमिन के लिए है।")
            return
            
        total, used, free = shutil.disk_usage("/")
        memory = psutil.virtual_memory()
        cpu_usage = psutil.cpu_percent(interval=0.5)
        
        stats_text = (
            f"🖥 **सर्वर लाइव स्टेट्स (VPS Stats)** 🖥\n\n"
            f"**⚙️ OS:** `{platform.system()} {platform.release()}`\n"
            f"**💻 CPU लोड:** `{cpu_usage}%` (1 Core)\n"
            f"**🧠 RAM लोड:** `{memory.percent}%` (1 GB)\n"
            f"**💾 डिस्क उपयोग:** `{used // (1024**3)} GB / {total // (1024**3)} GB`\n"
            f"**⚡ ऑप्टिमाइजेशन:** TgCrypto C-Extensions + Pillow Lightweight Engine\n\n"
            f"**Powered by ANANOMUS BRO**"
        )
        await event.respond(stats_text)
