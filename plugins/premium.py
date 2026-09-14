# Copyright (c) 2025 Gagan : https://github.com/devgaganin.  
# Licensed under the GNU General Public License v3.0.  
# See LICENSE file in the repository root for full license text.

from shared_client import client as bot_client, app
from telethon import events
from datetime import timedelta
from config import OWNER_ID
from utils.func import add_premium_user, is_private_chat
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton as IK, InlineKeyboardMarkup as IKM
from config import OWNER_ID, JOIN_LINK as JL , ADMIN_CONTACT as AC
import base64 as spy
from utils.func import a1, a2, a3, a4, a5, a7, a8, a9, a10, a11
from plugins.start import subscribe


@bot_client.on(events.NewMessage(pattern='/add'))
async def add_premium_handler(event):
    if not await is_private_chat(event):
        await event.respond(
            'This command can only be used in private chats for security reasons.'
            )
        return
    """Handle /add command to add premium users (owner only)"""
    user_id = event.sender_id
    if user_id not in OWNER_ID:
        await event.respond('This command is restricted to the bot owner.')
        return
    text = event.message.text.strip()
    parts = text.split(' ')
    if len(parts) != 4:
        await event.respond(
            """Invalid format. Use: /add user_id duration_value duration_unit
Example: /add 123456 1 week"""
            )
        return
    try:
        target_user_id = int(parts[1])
        duration_value = int(parts[2])
        duration_unit = parts[3].lower()
        valid_units = ['min', 'hours', 'days', 'weeks', 'month', 'year',
            'decades']
        if duration_unit not in valid_units:
            await event.respond(
                f"Invalid duration unit. Choose from: {', '.join(valid_units)}"
                )
            return
        success, result = await add_premium_user(target_user_id,
            duration_value, duration_unit)
        if success:
            expiry_utc = result
            expiry_ist = expiry_utc + timedelta(hours=5, minutes=30)
            formatted_expiry = expiry_ist.strftime('%d-%b-%Y %I:%M:%S %p')
            await event.respond(
                f"""✅ User {target_user_id} added as premium member
Subscription valid until: {formatted_expiry} (IST)"""
                )
            await bot_client.send_message(target_user_id,
                f"""✅ Your have been added as premium member
**Validity upto**: {formatted_expiry} (IST)"""
                )
        else:
            await event.respond(f'❌ Failed to add premium user: {result}')
    except ValueError:
        await event.respond(
            'Invalid user ID or duration value. Both must be integers.')
    except Exception as e:
        await event.respond(f'Error: {str(e)}')
        
        
attr1 = spy.b64encode("photo".encode()).decode()
attr2 = spy.b64encode("file_id".encode()).decode()

@app.on_message(filters.command(spy.b64decode(a5.encode()).decode()))
async def start_handler(client, message):
    subscription_status = await subscribe(client, message)
    if subscription_status == 1:
        return
        
    caption = (
        "🤖 **अल्टीमेट रेस्ट्रिक्टेड कंटेंट सेवर बोट** 🤖\n\n"
        "✨ **मुख्य विशेषताएँ (Features):**\n"
        "🔹 सिंगल या बैच एक्सट्रैक्शन (Public/Private)\n"
        "🔹 लॉगिन/लॉगआउट सपोर्ट\n"
        "🔹 कस्टम थंबनेल, कैप्शन और टेक्स्ट रिप्लेसमेंट\n"
        "🔹 VIP सपोर्ट और अल्ट्राफास्ट स्पीड\n\n"
        "👇 **नीचे दिए गए बटन्स का उपयोग करें:**"
    )
    
    kb = IKM([
        [IK("🔥 Single Extract", callback_data="help_single"), IK("📦 Batch Extract", callback_data="help_batch")],
        [IK("🔐 Login", callback_data="help_login"), IK("⚙️ Settings", callback_data="help_settings")],
        [IK("💎 VIP Plans", callback_data="see_plan"), IK("🆘 Contact Admin", url=AC)]
    ])
    
    try:
        await message.reply_photo(
            photo="https://graph.org/file/d44f024a08ded19452152.jpg",
            caption=caption,
            reply_markup=kb
        )
    except Exception:
        await message.reply_text(caption, reply_markup=kb)

@app.on_callback_query(filters.regex(r"^help_"))
async def custom_help_callbacks(client, query):
    data = query.data
    if data == "help_single":
        await query.answer("Single Extract", show_alert=False)
        await query.message.edit_text("📥 **Single Extract:**\nJust send the link of any public or private message.\nFor private, you must use /login first.", reply_markup=IKM([[IK("🔙 Back", callback_data="help_back")]]))
    elif data == "help_batch":
        await query.answer("Batch Extract", show_alert=False)
        await query.message.edit_text("📦 **Batch Extract:**\nUse `/batch <link>` to extract up to 100k files.\nYou can also use `/cancel` to stop it.", reply_markup=IKM([[IK("🔙 Back", callback_data="help_back")]]))
    elif data == "help_login":
        await query.answer("Login", show_alert=False)
        await query.message.edit_text("🔐 **Login System:**\nUse `/login` in bot PM to login to your Telegram account.\nUse `/logout` to logout.", reply_markup=IKM([[IK("🔙 Back", callback_data="help_back")]]))
    elif data == "help_settings":
        await query.answer("Settings", show_alert=False)
        await query.message.edit_text("⚙️ **Settings:**\nSend `/settings` to open the settings panel (Telethon based). You can configure rename tags, replacement words, and more.", reply_markup=IKM([[IK("🔙 Back", callback_data="help_back")]]))
    elif data == "help_back":
        await start_handler(client, query.message)
        try: await query.message.delete()
        except: pass
