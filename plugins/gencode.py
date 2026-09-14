# Copyright (c) 2025 devgagan : https://github.com/devgaganin.
# Licensed under the GNU General Public License v3.0.

from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from shared_client import app
from utils.func import add_premium_user, codedb, send_to_log_group
from config import OWNER_ID, LOG_GROUP
import string
import random
from datetime import timedelta
from plugins.start import subscribe as sub

@app.on_message(filters.command("gencode") & filters.private)
async def generate_code_cmd(client, message):
    user_id = message.from_user.id
    try: await message.delete()
    except Exception: pass
    
    is_owner = False
    if isinstance(OWNER_ID, list):
        is_owner = user_id in OWNER_ID or str(user_id) in [str(x) for x in OWNER_ID]
    else:
        is_owner = str(user_id) == str(OWNER_ID)
        
    if not is_owner:
        return await message.reply("❌ यह कमांड केवल ओनर के लिए है।")
    
    parts = message.text.split()
    if len(parts) < 3:
        return await message.reply(
            "⚠️ **सही फॉर्मेट:** `/gencode [संख्या] [यूनिट] [basic/pro]`\n"
            "**उदाहरण:** `/gencode 1 month pro` या `/gencode 7 days basic`"
        )
        
    try:
        duration_value = int(parts[1])
        duration_unit = parts[2].lower()
        plan_type = "Pro"
        if len(parts) > 3:
            plan_type = parts[3].capitalize()
            if plan_type not in ["Basic", "Pro"]:
                plan_type = "Pro"
                
        valid_units = ['min', 'hours', 'days', 'weeks', 'month', 'year', 'decades']
        if duration_unit not in valid_units:
            return await message.reply(f"❌ अमान्य यूनिट। उपलब्ध: {', '.join(valid_units)}")
            
        random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        redeem_code = f"ANANOMUS-{plan_type.upper()}-{random_chars}"
        
        await codedb.insert_one({
            "code": redeem_code,
            "duration_value": duration_value,
            "duration_unit": duration_unit,
            "plan_type": plan_type
        })

        if LOG_GROUP:
            try:
                await send_to_log_group(
                    f"🎟️ **नया रिडीम कोड जनरेट हुआ (New Code Generated)**\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"👑 **जनरेट कर्ता (Admin):** `{user_id}`\n"
                    f"🎫 **कोड:** `{redeem_code}`\n"
                    f"💎 **प्लान:** `{plan_type}`\n"
                    f"⏱️ **अवधि:** `{duration_value} {duration_unit}`"
                )
            except Exception: pass
        
        await message.reply(
            f"✅ **रिडीम कोड सफलतापूर्वक जनरेट हुआ!**\n\n"
            f"🎟️ **कोड:** `{redeem_code}`\n"
            f"💎 **प्लान:** `{plan_type}`\n"
            f"⏱️ **अवधि:** `{duration_value} {duration_unit}`\n\n"
            f"💡 इस्तेमाल करने के लिए: `/redeem {redeem_code}`"
        )
    except Exception as e:
        await message.reply(f"❌ त्रुटि: {str(e)}")

@app.on_message(filters.command("redeem") & filters.private)
async def redeem_code_cmd(client, message):
    try: await message.delete()
    except Exception: pass
    if await sub(client, message) == 1: return
    user_id = message.from_user.id
    
    parts = message.text.split()
    if len(parts) < 2:
        return await message.reply("⚠️ **कृपया कोड साथ भेजें:** `/redeem [कोड]`")
        
    redeem_code = parts[1].strip()
    msg = await message.reply("🔄 **कोड सत्यापित किया जा रहा है...**")
    
    try:
        code_data = await codedb.find_one({"code": redeem_code})
        if not code_data:
            return await msg.edit("❌ **अमान्य या समाप्त रिडीम कोड!**")
            
        duration_value = code_data.get("duration_value")
        duration_unit = code_data.get("duration_unit")
        plan_type = code_data.get("plan_type", "Pro")
        
        success, result = await add_premium_user(user_id, duration_value, duration_unit, plan_type)
        if success:
            await codedb.delete_one({"_id": code_data["_id"]})
            
            expiry_ist = result + timedelta(hours=5, minutes=30)
            formatted_expiry = expiry_ist.strftime('%d-%b-%Y %I:%M:%S %p')
            
            await msg.edit(
                f"🎉 **बधाई हो! कोड सफलतापूर्वक रिडीम हो गया!** 🎉\n\n"
                f"💎 **प्लान:** `{plan_type} VIP`\n"
                f"⏱️ **अवधि:** `{duration_value} {duration_unit}`\n"
                f"📅 **वैधता:** `{formatted_expiry} (IST)`\n\n"
                f"अब आप बिना किसी सीमा के फाइलें निकाल सकते हैं!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚡ मुख्य मेनू खोलें", callback_data="btn_main_menu")]])
            )
            
            if LOG_GROUP:
                try:
                    u_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
                    u_handle = f"@{message.from_user.username}" if message.from_user.username else "None"
                    await send_to_log_group(
                        f"🎟️ **रिडीम कोड सफलतापूर्वक उपयोग किया गया (Code Redeemed)**\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"👤 **यूज़र:** [{u_name}](tg://user?id={user_id}) ({u_handle})\n"
                        f"🆔 **ID:** `{user_id}`\n"
                        f"🎫 **कोड:** `{redeem_code}`\n"
                        f"💎 **प्लान:** `{plan_type}`\n"
                        f"⏳ **वैधता:** `{formatted_expiry} (IST)`"
                    )
                except Exception: pass
        else:
            await msg.edit(f"❌ सिस्टम त्रुटि: {result}")
    except Exception as e:
        await msg.edit(f"❌ त्रुटि: {str(e)}")
