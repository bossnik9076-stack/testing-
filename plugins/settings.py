# Copyright (c) 2025 devgagan : https://github.com/devgaganin.
# Licensed under the GNU General Public License v3.0.
# See LICENSE file in the repository root for full license text.

import re
import os
import time
import logging
from telethon import events, Button
from pyrogram import filters
from pyrogram.types import (
    InlineKeyboardMarkup as PKM, InlineKeyboardButton as PKB,
    Message, CallbackQuery
)
from shared_client import client as gf, app as pyapp
from config import OWNER_ID, LOG_GROUP
from utils.func import (
    get_user_data_key, save_user_data, users_collection, is_premium_user,
    send_to_log_group, parse_replacement_rules, extract_message_markdown,
    clean_chat_id_input, parse_delete_words
)
from utils.custom_filters import (
    settings_in_progress, set_settings_step, get_settings_step
)
from plugins.start import subscribe as sub

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {'mp4', 'mkv', 'avi', 'mov', 'wmv', 'flv', 'webm', 'mpeg', 'mpg', '3gp'}
SET_PIC = 'settings.jpg'
MESS = '⚙️ **अपने कस्टम सेटिंग्स को कस्टमाइज़ करें:**'

active_conversations = {}


async def get_settings_text(user_id: int) -> str:
    rename_tag = await get_user_data_key(user_id, 'rename_tag', '')
    caption = await get_user_data_key(user_id, 'caption', '')
    delete_words = await get_user_data_key(user_id, 'delete_words', []) or []
    replacements = await get_user_data_key(user_id, 'replacement_words', {}) or {}
    target_chat = await get_user_data_key(user_id, 'chat_id', '')
    has_thumb = os.path.exists(f"{user_id}.jpg")

    thumb_status = "✅ सक्रिय (Set)" if has_thumb else "❌ सेट नहीं है"
    tag_status = f"`{rename_tag}`" if rename_tag else "❌ सेट नहीं है"
    cap_status = "✅ सेट है (Configured)" if caption else "❌ सेट नहीं है"
    chat_status = f"`{target_chat}`" if target_chat else "❌ सेट नहीं (बॉट चैट में आएगा)"
    del_count = f"{len(delete_words)} शब्द" if delete_words else "❌ कोई नहीं"
    rep_count = f"{len(replacements)} नियम" if replacements else "❌ कोई नहीं"

    return (
        "⚙️ **कस्टम सेटिंग्स डैशबोर्ड (Personalization)** ⚙️\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📊 **आपकी वर्तमान सेटिंग्स की स्थिति:**\n\n"
        f"• 📢 **टारगेट चैट ID:** {chat_status}\n"
        f"• 🖼️ **थंबनेल:** {thumb_status}\n"
        f"• 🏷️ **रीनेम टैग:** {tag_status}\n"
        f"• 📋 **कस्टम कैप्शन:** {cap_status}\n"
        f"• 🔄 **रिप्लेस वर्ड्स:** {rep_count}\n"
        f"• 🗑️ **डिलीट वर्ड्स:** {del_count}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💡 किसी भी सेटिंग को बदलने के लिए नीचे दिए गए बटन पर क्लिक करें:"
    )


def get_settings_keyboard() -> PKM:
    return PKM([
        [
            PKB("📢 Set Channel/Chat ID", callback_data="py_setchatid"),
            PKB("❌ Remove Chat ID", callback_data="py_remchatid")
        ],
        [
            PKB("🏷️ Set Rename Tag", callback_data="py_setrename"),
            PKB("📋 Set Caption", callback_data="py_setcaption")
        ],
        [
            PKB("🖼️ Set Thumbnail", callback_data="py_setthumb"),
            PKB("❌ Remove Thumbnail", callback_data="py_remthumb")
        ],
        [
            PKB("🔄 Replace Words", callback_data="py_setreplacement"),
            PKB("🗑️ Delete Words", callback_data="py_deleteword")
        ],
        [
            PKB("👁️ View Full Config", callback_data="py_viewsettings"),
            PKB("🔄 Reset All", callback_data="py_reset_settings")
        ],
        [
            PKB("🔙 मुख्य मेनू (Main Menu)", callback_data="btn_main_menu")
        ]
    ])

@pyapp.on_callback_query(filters.regex("^btn_settings_menu$"))
async def pyrogram_settings_menu(client, callback: CallbackQuery):
    if await sub(client, callback) == 1:
        return
    user_id = callback.from_user.id

    set_settings_step(user_id, None)
    text = await get_settings_text(user_id)
    kb = get_settings_keyboard()
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.reply_text(text, reply_markup=kb)

@pyapp.on_callback_query(filters.regex("^(py_cancel_settings|btn_cancel_settings)$"))
async def py_cancel_settings_cb(client, callback: CallbackQuery):
    user_id = callback.from_user.id
    set_settings_step(user_id, None)
    active_conversations.pop(user_id, None)
    await callback.answer("🛑 इनपुट रद्द कर दिया गया!", show_alert=False)
    await pyrogram_settings_menu(client, callback)

@pyapp.on_callback_query(filters.regex("^py_viewsettings$"))
async def py_viewsettings_cb(client, callback: CallbackQuery):
    if await sub(client, callback) == 1:
        return
    user_id = callback.from_user.id
    
    rename_tag = await get_user_data_key(user_id, 'rename_tag', '')
    caption = await get_user_data_key(user_id, 'caption', '')
    delete_words = await get_user_data_key(user_id, 'delete_words', []) or []
    replacements = await get_user_data_key(user_id, 'replacement_words', {}) or {}
    target_chat = await get_user_data_key(user_id, 'chat_id', '')
    has_thumb = os.path.exists(f"{user_id}.jpg")

    rep_lines = "\n".join([f"  • `{k}` ➔ `{v}`" for k, v in list(replacements.items())[:10]]) if replacements else "  (कोई नियम नहीं)"
    del_lines = ", ".join([f"`{w}`" for w in delete_words[:15]]) if delete_words else "(कोई शब्द नहीं)"

    text = (
        "📋 **विस्तृत सेटिंग्स रिपोर्ट (Current Configuration)**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📢 **टारगेट चैट ID:** {f'`{target_chat}`' if target_chat else '❌ सेट नहीं (बॉट DM)'}\n\n"
        f"🏷️ **रीनेम टैग:** {f'`{rename_tag}`' if rename_tag else '❌ सेट नहीं'}\n\n"
        f"🖼️ **कस्टम थंबनेल:** {'✅ सक्रिय' if has_thumb else '❌ सेट नहीं'}\n\n"
        f"📋 **कस्टम कैप्शन:**\n{caption if caption else '❌ सेट नहीं'}\n\n"
        f"🔄 **रिप्लेस वर्ड्स रूल्स ({len(replacements)}):**\n{rep_lines}\n\n"
        f"🗑️ **डिलीट वर्ड्स ({len(delete_words)}):**\n{del_lines}\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    kb = PKM([
        [PKB("⚙️ सेटिंग्स बदलें (Edit Settings)", callback_data="btn_settings_menu")],
        [PKB("🔙 मुख्य मेनू (Main Menu)", callback_data="btn_main_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

@pyapp.on_callback_query(filters.regex("^py_remchatid$"))
async def py_remchatid_cb(client, callback: CallbackQuery):
    user_id = callback.from_user.id
    await users_collection.update_one(
        {'user_id': user_id},
        {'$unset': {'chat_id': ''}}
    )
    await callback.answer("✅ टारगेट चैट ID हटा दी गई! अब फाइल्स सीधे आपकी चैट में आएंगी।", show_alert=True)
    await pyrogram_settings_menu(client, callback)

@pyapp.on_callback_query(filters.regex("^py_remthumb$"))
async def py_remthumb_cb(client, callback: CallbackQuery):
    user_id = callback.from_user.id
    thumb_path = f"{user_id}.jpg"
    if os.path.exists(thumb_path):
        os.remove(thumb_path)
        await callback.answer("✅ थंबनेल हटा दिया गया!", show_alert=True)
    else:
        await callback.answer("❌ कोई थंबनेल सेट नहीं है।", show_alert=True)
    await pyrogram_settings_menu(client, callback)

@pyapp.on_callback_query(filters.regex("^(py_remdelete|btn_remdelete)$"))
async def py_remdelete_cb(client, callback: CallbackQuery):
    user_id = callback.from_user.id
    await users_collection.update_one(
        {'user_id': user_id},
        {'$unset': {'delete_words': ''}}
    )
    await callback.answer("✅ सभी डिलीट वर्ड्स साफ़ कर दिए गए!", show_alert=True)
    await pyrogram_settings_menu(client, callback)

@pyapp.on_callback_query(filters.regex("^(py_remreplacement|btn_remreplacement)$"))
async def py_remreplacement_cb(client, callback: CallbackQuery):
    user_id = callback.from_user.id
    await users_collection.update_one(
        {'user_id': user_id},
        {'$unset': {'replacement_words': ''}}
    )
    await callback.answer("✅ सभी वर्ड रिप्लेसमेंट साफ़ कर दिए गए!", show_alert=True)
    await pyrogram_settings_menu(client, callback)

@pyapp.on_callback_query(filters.regex("^py_reset_settings$"))
async def py_reset_settings_cb(client, callback: CallbackQuery):
    user_id = callback.from_user.id
    await users_collection.update_one(
        {'user_id': user_id},
        {'$unset': {
            'delete_words': '',
            'replacement_words': '',
            'rename_tag': '',
            'caption': '',
            'chat_id': ''
        }}
    )
    for p in [f"{user_id}.jpg", f"thumb_{user_id}.jpg"]:
        if os.path.exists(p):
            os.remove(p)
    set_settings_step(user_id, None)
    if LOG_GROUP:
        try:
            u_name = f"{callback.from_user.first_name or ''} {callback.from_user.last_name or ''}".strip()
            u_handle = f"@{callback.from_user.username}" if callback.from_user.username else "None"
            await send_to_log_group(
                f"⚙️ **सेटिंग्स रीसेट (Settings Reset)**\n"
                f"👤 **यूज़र:** [{u_name}](tg://user?id={user_id}) ({u_handle})\n"
                f"🆔 **ID:** `{user_id}`\n"
                f"🔄 सभी कस्टम सेटिंग्स रीसेट की गईं।"
            )
        except Exception: pass
    await callback.answer("✅ सभी सेटिंग्स पूरी तरह रीसेट कर दी गई हैं!", show_alert=True)
    await pyrogram_settings_menu(client, callback)

@pyapp.on_callback_query(filters.regex(r"^py_(setrename|setcaption|setthumb|setreplacement|deleteword|setchatid)$"))
async def py_settings_step_trigger(client, callback: CallbackQuery):
    if await sub(client, callback) == 1:
        return
    user_id = callback.from_user.id

    action = callback.data.replace("py_", "")
    set_settings_step(user_id, action)
    active_conversations[user_id] = {'type': action}

    cancel_kb = PKM([
        [PKB("🛑 रद्द करें (Cancel)", callback_data="py_cancel_settings")],
        [PKB("🔙 सेटिंग्स मेनू", callback_data="btn_settings_menu")]
    ])

    if action == "setchatid":
        prompt_text = (
            "📢 **टारगेट चैनल/ग्रुप ID सेटिंग्स (Direct Channel Send)**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👉 फाइल्स को सीधे अपने चैनल या ग्रुप में भेजने के लिए उसकी **Chat ID** भेजें:\n\n"
            "📌 **सही फॉर्मेट (Format):**\n"
            "• चैनल/सुपरग्रुप ID: `-1001234567890`\n"
            "• अगर टॉपिक/थ्रेड है: `-1001234567890/45`\n"
            "• पब्लिक चैनल यूज़रनेम: `@YourChannelUsername`\n\n"
            "💡 **ज़रूरी निर्देश:**\n"
            "1. बॉट को उस चैनल/ग्रुप में **Admin (व्यवस्थापक)** बनाकर 'Post/Send Messages' की अनुमति दें।\n"
            "2. अगर प्राइवेट चैनल है, तो बॉट या आपका लॉग-इन अकाउंट उसमें मेंबर/एडमिन होना चाहिए।\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "*(रद्द करने के लिए नीचे दिए गए बटन पर क्लिक करें या `/cancel` भेजें)*"
        )
    elif action == "setreplacement":
        prompt_text = (
            "🔄 **वर्ड रिप्लेसमेंट सेटिंग्स (Replace Words)**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👉 फ़ाइल के नाम और कैप्शन से पुराने शब्दों को नए शब्दों से बदलने के लिए नीचे दिए गए फॉर्मेट में भेजें:\n\n"
            "📌 **सही फॉर्मेट (Format):**\n"
            "`'पुराना_शब्द' 'नया_शब्द'`\n"
            "या\n"
            "`\"पुराना_शब्द\" \"नया_शब्द\"`\n\n"
            "🔗 **लिंक / हाइपरलिंक सपोर्ट (Link / Hyperlink):**\n"
            "• आप `'नया_शब्द'` पर क्लिक करके **'Create Link'** से लिंक भी लगा सकते हैं!\n"
            "• बॉट आपके नए शब्द को लिंक सहित कैप्शन में बदल देगा!\n\n"
            "💡 **उदाहरण (Examples):**\n"
            "• `'Join @OldChannel' '@MyNewChannel'`\n"
            "• `'OldChannel' '[MyChannel](https://t.me/mychannel)'`\n"
            "• `'Download Free' 'Team Ananomus'`\n"
            "• आप एक साथ कई लाइनें भी भेज सकते हैं:\n"
            "`'OldWord1' 'NewWord1'`\n"
            "`'OldWord2' 'NewWord2'`\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "*(रद्द करने के लिए नीचे दिए गए बटन पर क्लिक करें या `/cancel` भेजें)*"
        )
    elif action == "deleteword":
        prompt_text = (
            "🗑️ **वर्ड रिमूवर सेटिंग्स (Remove / Delete Words)**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👉 फ़ाइल के नाम और कैप्शन से जिन शब्दों को पूरी तरह हटाना चाहते हैं, उन्हें स्पेस देकर या नई लाइन में भेजें:\n\n"
            "📌 **सही फॉर्मेट (Format):**\n"
            "`word1 word2 @spam_channel www.site.com`\n\n"
            "💡 **उदाहरण (Example):**\n"
            "`JoinNow DownloadFree @OldPromo [ClickHere]`\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "*(रद्द करने के लिए नीचे दिए गए बटन पर क्लिक करें या `/cancel` भेजें)*"
        )
    elif action == "setrename":
        prompt_text = (
            "🏷️ **रीनेम टैग सेटिंग्स (Rename Tag)**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👉 डाउनलोड होने वाली सभी फाइल्स के अंत में जोड़ने के लिए अपना **टैग** भेजें:\n\n"
            "💡 **उदाहरण (Example):**\n"
            "• `@AnanomusBro`\n"
            "• `[By MyChannel]`\n"
            "• `@MyMoviesChannel`\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "*(रद्द करने के लिए नीचे दिए गए बटन पर क्लिक करें या `/cancel` भेजें)*"
        )
    elif action == "setcaption":
        prompt_text = (
            "📋 **कस्टम कैप्शन सेटिंग्स (Custom Caption)**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👉 अपनी सभी फाइल्स के साथ भेजा जाने वाला **कस्टम कैप्शन** टाइप करके भेजें:\n\n"
            "💡 *नोट:* आप इमोजी, मल्टी-लाइन और कोई भी टेक्स्ट भेज सकते हैं।\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "*(रद्द करने के लिए नीचे दिए गए बटन पर क्लिक करें या `/cancel` भेजें)*"
        )
    elif action == "setthumb":
        prompt_text = (
            "🖼️ **कस्टम थंबनेल सेटिंग्स (Custom Thumbnail)**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👉 कृपया थंबनेल के रूप में लगाने के लिए एक **फोटो (Photo/Image)** चैट में भेजें।\n\n"
            "💡 *नोट:* यह थंबनेल सभी वीडियो फाइल्स पर अपने आप लगाया जाएगा।\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "*(रद्द करने के लिए नीचे दिए गए बटन पर क्लिक करें या `/cancel` भेजें)*"
        )
    else:
        prompt_text = "👉 कृपया अपना इनपुट भेजें:"

    await callback.message.edit_text(prompt_text, reply_markup=cancel_kb)

@pyapp.on_message(filters.private & settings_in_progress & filters.text & ~filters.command(['cancel', 'stop', 'start']), group=-1)
async def py_settings_text_handler(client, message: Message):
    try: await message.delete()
    except Exception: pass
    if await sub(client, message) == 1:
        return
    user_id = message.from_user.id
    step = get_settings_step(user_id)
    if not step:
        return

    try:
        message.stop_propagation()
    except Exception:
        pass

    raw_text = extract_message_markdown(message).strip()
    text = (message.text or "").strip()

    back_kb = PKM([
        [PKB("⚙️ वापस सेटिंग्स में जाएँ", callback_data="btn_settings_menu")],
        [PKB("🔙 मुख्य मेनू", callback_data="btn_main_menu")]
    ])

    cancel_kb = PKM([
        [PKB("🛑 रद्द करें (Cancel)", callback_data="py_cancel_settings")],
        [PKB("🔙 सेटिंग्स मेनू", callback_data="btn_settings_menu")]
    ])

    if step == "setreplacement":
        matches = parse_replacement_rules(raw_text or text)
        if matches:
            replacements = await get_user_data_key(user_id, 'replacement_words', {}) or {}
            added_rules = []
            for old_w, new_w in matches:
                old_clean = old_w.strip()
                new_clean = new_w.strip()
                if old_clean:
                    replacements[old_clean] = new_clean
                    if new_clean.startswith('[') and '](' in new_clean and new_clean.endswith(')'):
                        added_rules.append(f"• `{old_clean}` ➔ {new_clean}")
                    else:
                        added_rules.append(f"• `{old_clean}` ➔ `{new_clean}`")

            if added_rules:
                await save_user_data(user_id, 'replacement_words', replacements)
                set_settings_step(user_id, None)
                active_conversations.pop(user_id, None)
                res_text = (
                    "✅ **वर्ड रिप्लेसमेंट सफलतापूर्वक सेव हो गया!**\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "🔄 **सहेजे गए नियम:**\n"
                    + "\n".join(added_rules) + "\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"📊 **कुल एक्टिव नियम:** {len(replacements)}\n"
                    "💡 अब आपकी फाइल्स और कैप्शन में ये शब्द अपने आप बदल दिए जाएंगे।"
                )
                if LOG_GROUP:
                    try:
                        u_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
                        u_handle = f"@{message.from_user.username}" if message.from_user.username else "None"
                        await send_to_log_group(
                            f"⚙️ **सेटिंग्स अपडेट: रिप्लेस वर्ड्स**\n"
                            f"👤 **यूज़र:** [{u_name}](tg://user?id={user_id}) ({u_handle})\n"
                            f"🆔 **ID:** `{user_id}`\n"
                            f"🔄 **नियम संख्या:** `{len(replacements)}`"
                        )
                    except Exception: pass
                await message.reply_text(res_text, reply_markup=back_kb)
                return

        error_text = (
            "❌ **अमान्य फॉर्मेट (Invalid Format)!** ❌\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "आपने गलत फॉर्मेट में शब्द भेजे हैं।\n\n"
            "👉 **कृपया इस सही फॉर्मेट में भेजें:**\n"
            "`'पुराना_शब्द' 'नया_शब्द'` या `\"पुराना_शब्द\" \"नया_शब्द\"`\n"
            "या\n"
            "`पुराना_शब्द -> नया_शब्द`\n\n"
            "💡 **उदाहरण (Examples):**\n"
            "• `'Join @OldChannel' '@MyNewChannel'`\n"
            "• `'Download Now' 'Watch Here'`\n\n"
            "*(कृपया ऊपर दिए गए फॉर्मेट के अनुसार दोबारा भेजें या नीचे दिए गए बटन से रद्द करें)*"
        )
        await message.reply_text(error_text, reply_markup=cancel_kb)

    elif step == "deleteword":
        words = parse_delete_words(text)
        if words:
            delete_words = await get_user_data_key(user_id, 'delete_words', []) or []
            delete_words = list(dict.fromkeys(delete_words + words))
            await save_user_data(user_id, 'delete_words', delete_words)
            set_settings_step(user_id, None)
            active_conversations.pop(user_id, None)
            
            res_text = (
                "✅ **डिलीट वर्ड्स सफलतापूर्वक सेव हो गए!**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"🗑️ **हटाए जाने वाले शब्द:**\n`{', '.join(words)}`\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 **कुल एक्टिव डिलीट वर्ड्स:** {len(delete_words)}\n"
                "💡 अब आपकी फाइल्स और कैप्शन से ये शब्द अपने आप मिटा दिए जाएंगे।"
            )
            if LOG_GROUP:
                try:
                    u_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
                    u_handle = f"@{message.from_user.username}" if message.from_user.username else "None"
                    await send_to_log_group(
                        f"⚙️ **सेटिंग्स अपडेट: डिलीट वर्ड्स**\n"
                        f"👤 **यूज़र:** [{u_name}](tg://user?id={user_id}) ({u_handle})\n"
                        f"🆔 **ID:** `{user_id}`\n"
                        f"🗑️ **शब्द:** `{', '.join(words)}`"
                    )
                except Exception: pass
            await message.reply_text(res_text, reply_markup=back_kb)
        else:
            await message.reply_text(
                "❌ **अमान्य इनपुट!**\nकृपया हटाने के लिए कम से कम एक शब्द स्पेस या कॉमा देकर भेजें (जैसे: `word1 word2 @promo`).",
                reply_markup=cancel_kb
            )

    elif step == "setrename":
        tag = text.strip()
        if tag:
            await save_user_data(user_id, 'rename_tag', tag)
            set_settings_step(user_id, None)
            active_conversations.pop(user_id, None)
            res_text = (
                "✅ **रीनेम टैग सफलतापूर्वक सेव हो गया!**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"🏷️ **सेट किया गया टैग:** `{tag}`\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "💡 अब डाउनलोड होने वाली सभी फाइल्स के अंत में यह टैग जोड़ा जाएगा।"
            )
            if LOG_GROUP:
                try:
                    u_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
                    u_handle = f"@{message.from_user.username}" if message.from_user.username else "None"
                    await send_to_log_group(
                        f"⚙️ **सेटिंग्स अपडेट: रीनेम टैग**\n"
                        f"👤 **यूज़र:** [{u_name}](tg://user?id={user_id}) ({u_handle})\n"
                        f"🆔 **ID:** `{user_id}`\n"
                        f"🏷️ **टैग:** `{tag}`"
                    )
                except Exception: pass
            await message.reply_text(res_text, reply_markup=back_kb)
        else:
            await message.reply_text("❌ कृपया एक वैध रीनेम टैग टेक्स्ट भेजें।", reply_markup=cancel_kb)

    elif step == "setcaption":
        caption = text.strip()
        if caption:
            await save_user_data(user_id, 'caption', caption)
            set_settings_step(user_id, None)
            active_conversations.pop(user_id, None)
            res_text = (
                "✅ **कस्टम कैप्शन सफलतापूर्वक सेव हो गया!**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "📋 **कैप्शन प्रीव्यू:**\n"
                f"{caption}\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "💡 अब आपकी सभी फाइल्स के साथ यह कस्टम कैप्शन भेजा जाएगा।"
            )
            if LOG_GROUP:
                try:
                    u_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
                    u_handle = f"@{message.from_user.username}" if message.from_user.username else "None"
                    await send_to_log_group(
                        f"⚙️ **सेटिंग्स अपडेट: कस्टम कैप्शन**\n"
                        f"👤 **यूज़र:** [{u_name}](tg://user?id={user_id}) ({u_handle})\n"
                        f"🆔 **ID:** `{user_id}`\n"
                        f"📋 **कैप्शन:** `{caption[:100]}`"
                    )
                except Exception: pass
            await message.reply_text(res_text, reply_markup=back_kb)
        else:
            await message.reply_text("❌ कृपया एक वैध कैप्शन टेक्स्ट भेजें।", reply_markup=cancel_kb)

    elif step == "setchatid":
        target = clean_chat_id_input(text)
        if target:
            await save_user_data(user_id, 'chat_id', target)
            set_settings_step(user_id, None)
            active_conversations.pop(user_id, None)

            clean_target = target.split('/')[0] if '/' in target else target
            parsed_id = int(clean_target) if (clean_target.startswith('-100') or clean_target.lstrip('-').isdigit()) else clean_target

            chat_title = None
            verified = False
            try:
                chat_obj = await message._client.get_chat(parsed_id)
                chat_title = chat_obj.title or str(parsed_id)
                verified = True
            except Exception:
                from shared_client import userbot
                if userbot:
                    try:
                        chat_obj = await userbot.get_chat(parsed_id)
                        chat_title = chat_obj.title or str(parsed_id)
                        verified = True
                    except Exception:
                        pass

            if verified and chat_title:
                status_str = f"📢 **चैनल/ग्रुप का नाम:** `{chat_title}`\n✅ **स्टेटस:** वेरिफ़ाइड और एक्टिव"
            else:
                status_str = "⚠️ **ध्यान दें:** सुनिश्चित करें कि बॉट आपके चैनल/ग्रुप में **Admin** है और उसके पास **Post Messages** की अनुमति है।"

            res_text = (
                "✅ **टारगेट चैट ID सफलतापूर्वक सेव हो गई!** 📢\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"🎯 **सेट की गई ID:** `{target}`\n"
                f"{status_str}\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "💡 अब बॉट द्वारा डाउनलोड की जाने वाली सभी फाइल्स सीधे इसी चैनल/ग्रुप में भेजी जाएँगी।"
            )
            if LOG_GROUP:
                try:
                    u_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
                    u_handle = f"@{message.from_user.username}" if message.from_user.username else "None"
                    await send_to_log_group(
                        f"⚙️ **सेटिंग्स अपडेट: टारगेट चैट ID**\n"
                        f"👤 **यूज़र:** [{u_name}](tg://user?id={user_id}) ({u_handle})\n"
                        f"🆔 **ID:** `{user_id}`\n"
                        f"🎯 **चैट ID:** `{target}`"
                    )
                except Exception: pass
            await message.reply_text(res_text, reply_markup=back_kb)
        else:
            await message.reply_text(
                "❌ **अमान्य Chat ID!**\n\n"
                "👉 कृपया सही फॉर्मेट में Chat ID भेजें:\n"
                "• `-1001234567890` (चैनल / सुपरग्रुप)\n"
                "• `-1001234567890/123` (टॉपिक / थ्रेड के साथ)\n"
                "• `@YourChannelUsername`\n\n"
                "*(रद्द करने के लिए नीचे दिए गए बटन पर क्लिक करें या `/cancel` भेजें)*",
                reply_markup=cancel_kb
            )

    elif step == "setthumb":
        await message.reply_text(
            "❌ **गलत इनपुट!**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "थंबनेल सेट करने के लिए कृपया टेक्स्ट के बजाय एक **फोटो (Photo/Image)** भेजें।\n"
            "*(या रद्द करने के लिए नीचे दिए गए बटन पर क्लिक करें)*",
            reply_markup=cancel_kb
        )

@pyapp.on_message(filters.private & settings_in_progress & (filters.photo | filters.document))
async def py_settings_photo_handler(client, message: Message):
    if await sub(client, message) == 1:
        return
    user_id = message.from_user.id
    step = get_settings_step(user_id)

    if step != "setthumb":
        return

    try:
        download_msg = await message.reply_text("⏳ थंबनेल डाउनलोड और प्रोसेस हो रहा है...")
        temp_path = await message.download()
        thumb_path = f"{user_id}.jpg"
        
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
        os.rename(temp_path, thumb_path)
        set_settings_step(user_id, None)

        back_kb = PKM([
            [PKB("⚙️ वापस सेटिंग्स में जाएँ", callback_data="btn_settings_menu")],
            [PKB("🔙 मुख्य मेनू", callback_data="btn_main_menu")]
        ])

        await download_msg.edit_text(
            "✅ **कस्टम थंबनेल सफलतापूर्वक सेव हो गया!** 🖼️\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "💡 अब सभी वीडियो फाइल्स पर यह थंबनेल अपने आप लगाया जाएगा।",
            reply_markup=back_kb
        )
        if LOG_GROUP:
            try:
                u_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
                u_handle = f"@{message.from_user.username}" if message.from_user.username else "None"
                await send_to_log_group(
                    f"⚙️ **सेटिंग्स अपडेट: कस्टम थंबनेल**\n"
                    f"👤 **यूज़र:** [{u_name}](tg://user?id={user_id}) ({u_handle})\n"
                    f"🆔 **ID:** `{user_id}`\n"
                    f"🖼️ नया थंबनेल सेट किया गया।"
                )
            except Exception: pass
    except Exception as e:
        logger.error(f"Thumbnail save error: {e}")
        await message.reply_text(f"❌ थंबनेल सेव करने में त्रुटि: {str(e)[:50]}")

@pyapp.on_message(filters.command(["settings", "setting", "config"]) & filters.private)
async def pyrogram_settings_command(client, message: Message):
    try: await message.delete()
    except Exception: pass
    if await sub(client, message) == 1: return
    user_id = message.from_user.id
    set_settings_step(user_id, None)
    active_conversations.pop(user_id, None)
    text = await get_settings_text(user_id)
    kb = get_settings_keyboard()
    await message.reply_text(text, reply_markup=kb)

@pyapp.on_message(filters.command(["setrename", "rename"]) & filters.private)
async def direct_setrename_cmd(client, message: Message):
    try: await message.delete()
    except Exception: pass
    if await sub(client, message) == 1: return
    user_id = message.from_user.id
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        set_settings_step(user_id, "setrename")
        active_conversations[user_id] = {'type': 'setrename'}
        return await message.reply_text(
            "🏷️ **रीनेम टैग सेट करें (Set Rename Tag)**\n\n"
            "👉 कृपया अपनी फाइलों के अंत में जोड़ने के लिए नया टैग भेजें:\n"
            "💡 *उदाहरण:* `@AnanomusBro`\n\n"
            "*(रद्द करने के लिए `/cancel` भेजें)*"
        )
    tag = parts[1].strip()
    await save_user_data(user_id, 'rename_tag', tag)
    set_settings_step(user_id, None)
    active_conversations.pop(user_id, None)
    await message.reply_text(f"✅ **रीनेम टैग सेट किया गया:** `{tag}`")

@pyapp.on_message(filters.command(["setcaption", "caption"]) & filters.private)
async def direct_setcaption_cmd(client, message: Message):
    try: await message.delete()
    except Exception: pass
    if await sub(client, message) == 1: return
    user_id = message.from_user.id
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        set_settings_step(user_id, "setcaption")
        active_conversations[user_id] = {'type': 'setcaption'}
        return await message.reply_text(
            "📋 **कस्टम कैप्शन सेट करें (Set Custom Caption)**\n\n"
            "👉 कृपया अपनी फाइलों के लिए नया कैप्शन भेजें।\n\n"
            "*(रद्द करने के लिए `/cancel` भेजें)*"
        )
    cap = parts[1].strip()
    await save_user_data(user_id, 'caption', cap)
    set_settings_step(user_id, None)
    active_conversations.pop(user_id, None)
    await message.reply_text(f"✅ **कस्टम कैप्शन सेट किया गया!**\n\n{cap}")

@pyapp.on_message(filters.command(["setthumb", "thumb"]) & filters.private)
async def direct_setthumb_cmd(client, message: Message):
    try: await message.delete()
    except Exception: pass
    if await sub(client, message) == 1: return
    user_id = message.from_user.id
    if message.reply_to_message and message.reply_to_message.photo:
        download_path = f"{user_id}.jpg"
        if os.path.exists(download_path):
            os.remove(download_path)
        await client.download_media(message.reply_to_message, file_name=download_path)
        set_settings_step(user_id, None)
        active_conversations.pop(user_id, None)
        await message.reply_text("✅ **कस्टम थंबनेल सफलतापूर्वक सेव हुआ!**")
    else:
        set_settings_step(user_id, "setthumb")
        active_conversations[user_id] = {'type': 'setthumb'}
        await message.reply_text("🖼️ **कृपया थंबनेल के रूप में लगाने के लिए एक फोटो भेजें:**\n*(या फोटो को रिप्लाई करके `/thumb` भेजें)*")

@pyapp.on_message(filters.command(["remthumb", "delthumb"]) & filters.private)
async def direct_remthumb_cmd(client, message: Message):
    try: await message.delete()
    except Exception: pass
    user_id = message.from_user.id
    thumb_path = f"{user_id}.jpg"
    if os.path.exists(thumb_path):
        os.remove(thumb_path)
        await message.reply_text("✅ **थंबनेल हटा दिया गया!**")
    else:
        await message.reply_text("❌ कोई थंबनेल सेट नहीं है।")

@pyapp.on_message(filters.command(["setchatid", "chatid", "setchannel", "channel", "target", "settarget"]) & filters.private)
async def direct_setchatid_cmd(client, message: Message):
    try: await message.delete()
    except Exception: pass
    if await sub(client, message) == 1: return
    user_id = message.from_user.id
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        set_settings_step(user_id, "setchatid")
        active_conversations[user_id] = {'type': 'setchatid'}
        return await message.reply_text(
            "📢 **टारगेट चैनल/ग्रुप ID सेट करें:**\n\n"
            "👉 कृपया अपने चैनल या ग्रुप की **Chat ID** भेजें:\n"
            "• `-1001234567890` (चैनल / सुपरग्रुप)\n"
            "• `-1001234567890/123` (टॉपिक / थ्रेड)\n"
            "• `@YourChannelUsername`\n\n"
            "💡 *उदाहरण:* `/chatid -1001234567890`\n"
            "*(रद्द करने के लिए `/cancel` भेजें)*"
        )
    cid = clean_chat_id_input(parts[1])
    if not cid:
        return await message.reply_text("❌ **अमान्य Chat ID!** कृपया `-1001234567890` या `@ChannelUsername` भेजें।")
    await save_user_data(user_id, 'chat_id', cid)
    set_settings_step(user_id, None)
    active_conversations.pop(user_id, None)
    await message.reply_text(
        f"✅ **टारगेट चैट ID सफलतापूर्वक सेट की गई:** `{cid}`\n\n"
        "💡 अब आपकी डाउनलोड की गई सभी फाइलें सीधे इसी चैनल/ग्रुप में भेजी जाएँगी।"
    )

@pyapp.on_message(filters.command(["remchatid", "delchatid", "clearchatid"]) & filters.private)
async def direct_remchatid_cmd(client, message: Message):
    try: await message.delete()
    except Exception: pass
    user_id = message.from_user.id
    await users_collection.update_one({'user_id': user_id}, {'$unset': {'chat_id': ''}})
    set_settings_step(user_id, None)
    active_conversations.pop(user_id, None)
    await message.reply_text("✅ **टारगेट चैट ID हटा दी गई! अब फाइल्स सीधे आपकी चैट में आएंगी।**")

@pyapp.on_message(filters.command(["deleteword", "deletewords", "delete", "del", "delword", "remword"]) & filters.private)
async def direct_deleteword_cmd(client, message: Message):
    try: await message.delete()
    except Exception: pass
    if await sub(client, message) == 1: return
    user_id = message.from_user.id
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        set_settings_step(user_id, "deleteword")
        active_conversations[user_id] = {'type': 'deleteword'}
        return await message.reply_text(
            "🗑️ **वर्ड रिमूवर (Delete Words):**\n\n"
            "👉 जिन शब्दों को फाइल के नाम या कैप्शन से हटाना चाहते हैं, उन्हें भेजें:\n"
            "💡 *उदाहरण:* `word1 word2 @promo www.site.com`\n\n"
            "*(या सीधे कमांड: `/delete word1 word2`)*\n"
            "*(रद्द करने के लिए `/cancel` भेजें)*"
        )
    words = parse_delete_words(parts[1])
    if not words:
        return await message.reply_text("❌ कृपया कम से कम एक शब्द दें (उदा: `/delete word1 word2`).")
    delete_words = await get_user_data_key(user_id, 'delete_words', []) or []
    delete_words = list(dict.fromkeys(delete_words + words))
    await save_user_data(user_id, 'delete_words', delete_words)
    set_settings_step(user_id, None)
    active_conversations.pop(user_id, None)
    await message.reply_text(
        f"✅ **डिलीट लिस्ट में जोड़े गए शब्द:**\n`{', '.join(words)}`\n\n"
        f"📊 **कुल एक्टिव डिलीट वर्ड्स:** {len(delete_words)}\n"
        "💡 अब आपकी फाइल्स और कैप्शन से ये शब्द अपने आप हटा दिए जाएंगे।"
    )

@pyapp.on_message(filters.command(["remdelete", "cleardelete", "clearwords"]) & filters.private)
async def direct_remdelete_cmd(client, message: Message):
    try: await message.delete()
    except Exception: pass
    user_id = message.from_user.id
    await users_collection.update_one({'user_id': user_id}, {'$unset': {'delete_words': ''}})
    set_settings_step(user_id, None)
    active_conversations.pop(user_id, None)
    await message.reply_text("✅ **सभी डिलीट वर्ड्स साफ़ कर दिए गए!**")

@pyapp.on_message(filters.command(["setreplacement", "setreplace", "replace", "replaceword", "replacement"]) & filters.private)
async def direct_setreplacement_cmd(client, message: Message):
    try: await message.delete()
    except Exception: pass
    if await sub(client, message) == 1: return
    user_id = message.from_user.id
    raw_text = extract_message_markdown(message)
    parts = raw_text.strip().split(maxsplit=1)
    if len(parts) < 2:
        set_settings_step(user_id, "setreplacement")
        active_conversations[user_id] = {'type': 'setreplacement'}
        return await message.reply_text(
            "🔄 **वर्ड रिप्लेसमेंट सेट करें (Word Replacement):**\n\n"
            "👉 जिन शब्दों को बदलना चाहते हैं, उन्हें इस तरह भेजें:\n"
            "`'पुराना_शब्द' 'नया_शब्द'` या `\"पुराना_शब्द\" \"नया_शब्द\"`\n"
            "या\n"
            "`पुराना_शब्द -> नया_शब्द`\n\n"
            "💡 *उदाहरण:* `/replace 'Join @OldChannel' '@MyNewChannel'`\n"
            "*(रद्द करने के लिए `/cancel` भेजें)*"
        )
    matches = parse_replacement_rules(parts[1])
    if matches:
        replacements = await get_user_data_key(user_id, 'replacement_words', {}) or {}
        added = []
        for old_w, new_w in matches:
            old_clean = old_w.strip()
            new_clean = new_w.strip()
            if old_clean:
                replacements[old_clean] = new_clean
                if new_clean.startswith('[') and '](' in new_clean and new_clean.endswith(')'):
                    added.append(f"• `{old_clean}` ➔ {new_clean}")
                else:
                    added.append(f"• `{old_clean}` ➔ `{new_clean}`")
        await save_user_data(user_id, 'replacement_words', replacements)
        set_settings_step(user_id, None)
        active_conversations.pop(user_id, None)
        await message.reply_text(
            "✅ **वर्ड रिप्लेसमेंट सफलतापूर्वक सेव हो गया!**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🔄 **सहेजे गए नियम:**\n"
            + "\n".join(added) + "\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 **कुल एक्टिव नियम:** {len(replacements)}"
        )
    else:
        await message.reply_text(
            "❌ **अमान्य फॉर्मेट!**\n"
            "कृपया `'पुराना_शब्द' 'नया_शब्द'` या `पुराना -> नया` फॉर्मेट में भेजें।\n"
            "💡 उदाहरण: `/replace 'Join @OldChannel' '@MyNewChannel'`"
        )

@pyapp.on_message(filters.command(["remreplacement", "clearreplacement", "clearreplace"]) & filters.private)
async def direct_remreplacement_cmd(client, message: Message):
    try: await message.delete()
    except Exception: pass
    user_id = message.from_user.id
    await users_collection.update_one({'user_id': user_id}, {'$unset': {'replacement_words': ''}})
    set_settings_step(user_id, None)
    active_conversations.pop(user_id, None)
    await message.reply_text("✅ **सभी वर्ड रिप्लेसमेंट साफ़ कर दिए गए!**")

@pyapp.on_message(filters.command(["reset", "resetall"]) & filters.private)
async def direct_reset_cmd(client, message: Message):
    try: await message.delete()
    except Exception: pass
    user_id = message.from_user.id
    await users_collection.update_one(
        {'user_id': user_id},
        {'$unset': {'delete_words': '', 'replacement_words': '', 'rename_tag': '', 'caption': '', 'chat_id': ''}}
    )
    for p in [f"{user_id}.jpg", f"thumb_{user_id}.jpg"]:
        if os.path.exists(p):
            os.remove(p)
    set_settings_step(user_id, None)
    active_conversations.pop(user_id, None)
    await message.reply_text("✅ **आपकी सभी सेटिंग्स पूरी तरह रीसेट कर दी गई हैं!**")

if gf:
    @gf.on(events.NewMessage(incoming=True, pattern=r'^/settings'))
    async def telethon_settings_command(event):
        try: await event.delete()
        except Exception: pass
        user_id = event.sender_id
        is_prem = await is_premium_user(user_id)
        if not is_prem:
            await event.respond("❌ **प्रीमियम केवल!** कृपया पहले /plan से अपग्रेड करें।")
            return
        await send_telethon_settings_message(event.chat_id, user_id)

async def send_telethon_settings_message(chat_id, user_id):
    if not gf: return
    buttons = [
        [Button.inline('📢 Set Chat ID', b'setchatid'), Button.inline('❌ Remove Chat ID', b'remchatid')],
        [Button.inline('🏷️ Set Rename Tag', b'setrename'), Button.inline('📋 Set Caption', b'setcaption')],
        [Button.inline('🔄 Replace Words', b'setreplacement'), Button.inline('🗑️ Remove Words', b'delete')],
        [Button.inline('🖼️ Set Thumbnail', b'setthumb'), Button.inline('❌ Remove Thumbnail', b'remthumb')],
        [Button.inline('🔄 Reset Settings', b'reset'), Button.url('🆘 Support', 'https://t.me/ananomusbro')]
    ]
    text = await get_settings_text(user_id)
    await gf.send_message(chat_id, text, buttons=buttons)

if gf:
    @gf.on(events.CallbackQuery)
    async def telethon_callback_query_handler(event):
        user_id = event.sender_id
        callback_actions = {
            b'setchatid': {
                'type': 'setchatid',
                'message': "📢 **टारगेट चैनल/ग्रुप की Chat ID भेजें (जैसे: `-1001234567890`):**"
            },
            b'setrename': {
                'type': 'setrename',
                'message': "🏷️ **रीनेम टैग भेजें (जैसे: `@MyChannel`):**"
            },
            b'setcaption': {
                'type': 'setcaption',
                'message': "📋 **कस्टम कैप्शन टेक्स्ट भेजें:**"
            },
            b'setreplacement': {
                'type': 'setreplacement',
                'message': "🔄 **वर्ड रिप्लेसमेंट फॉर्मेट:**\n`'पुराना_शब्द' 'नया_शब्द'` या `\"पुराना_शब्द\" \"नया_शब्द\"`"
            },
            b'delete': {
                'type': 'deleteword',
                'message': "🗑️ **हटाने वाले शब्द स्पेस देकर भेजें (जैसे: `word1 word2`):**"
            },
            b'setthumb': {
                'type': 'setthumb',
                'message': "🖼️ **कृपया थंबनेल के लिए एक फोटो भेजें:**"
            }
        }
        
        if event.data in callback_actions:
            action = callback_actions[event.data]
            msg = await event.respond(f"{action['message']}\n\n*(रद्द करने के लिए /cancel भेजें)*")
            active_conversations[user_id] = {'type': action['type'], 'message_id': msg.id}
        elif event.data == b'remchatid':
            await users_collection.update_one({'user_id': user_id}, {'$unset': {'chat_id': ''}})
            await event.answer('✅ टारगेट चैट ID हटा दी गई!', alert=True)
        elif event.data == b'reset':
            await users_collection.update_one(
                {'user_id': user_id},
                {'$unset': {'delete_words': '', 'replacement_words': '', 'rename_tag': '', 'caption': '', 'chat_id': ''}}
            )
            if os.path.exists(f'{user_id}.jpg'):
                os.remove(f'{user_id}.jpg')
            await event.answer('✅ सेटिंग्स रीसेट हो गईं!', alert=True)
        elif event.data == b'remthumb':
            if os.path.exists(f'{user_id}.jpg'):
                os.remove(f'{user_id}.jpg')
                await event.respond('✅ थंबनेल हटा दिया गया!')
            else:
                await event.respond('❌ कोई थंबनेल सेट नहीं है।')

if gf:
    @gf.on(events.NewMessage())
    async def telethon_handle_conversation_input(event):
        user_id = event.sender_id
        text = (event.text or "").strip()
        if user_id not in active_conversations or text.startswith('/'):
            return
            
        conv_type = active_conversations[user_id]['type']
        
        if conv_type == 'setchatid':
            cid = clean_chat_id_input(text)
            if cid:
                await save_user_data(user_id, 'chat_id', cid)
                await event.respond(f'✅ **टारगेट चैट ID सेट:** `{cid}`')
                del active_conversations[user_id]
                set_settings_step(user_id, None)
            else:
                await event.respond("❌ **अमान्य Chat ID!** कृपया `-1001234567890` या `@ChannelUsername` भेजें।")

        elif conv_type == 'setrename':
            await save_user_data(user_id, 'rename_tag', text)
            await event.respond(f'✅ रीनेम टैग सेट: `{text}`')
            del active_conversations[user_id]
            set_settings_step(user_id, None)
            
        elif conv_type == 'setcaption':
            await save_user_data(user_id, 'caption', text)
            await event.respond('✅ कस्टम कैप्शन सेट!')
            del active_conversations[user_id]
            set_settings_step(user_id, None)
            
        elif conv_type == 'setthumb' and event.photo:
            temp_path = await event.download_media()
            thumb_path = f'{user_id}.jpg'
            if os.path.exists(thumb_path):
                os.remove(thumb_path)
            os.rename(temp_path, thumb_path)
            await event.respond('✅ कस्टम थंबनेल सेव हुआ!')
            del active_conversations[user_id]
            set_settings_step(user_id, None)
            
        elif conv_type == 'deleteword':
            words = parse_delete_words(text)
            if words:
                delete_words = await get_user_data_key(user_id, 'delete_words', []) or []
                delete_words = list(dict.fromkeys(delete_words + words))
                await save_user_data(user_id, 'delete_words', delete_words)
                await event.respond(f"✅ डिलीट लिस्ट में जोड़े गए: `{', '.join(words)}`")
                del active_conversations[user_id]
                set_settings_step(user_id, None)
            else:
                await event.respond("❌ कृपया कम से कम एक शब्द स्पेस या कॉमा देकर भेजें।")
                
        elif conv_type == 'setreplacement':
            raw_text = ""
            if hasattr(event.message, 'entities') and event.message.entities:
                try:
                    from telethon.extensions import markdown
                    raw_text = markdown.unparse(event.message.message, event.message.entities)
                except Exception:
                    raw_text = event.text or event.message.message or ""
            else:
                raw_text = event.text or event.message.message or ""
            matches = parse_replacement_rules(raw_text)
            if matches:
                replacements = await get_user_data_key(user_id, 'replacement_words', {}) or {}
                added = []
                for old_w, new_w in matches:
                    old_clean = old_w.strip()
                    new_clean = new_w.strip()
                    if old_clean:
                        replacements[old_clean] = new_clean
                        if new_clean.startswith('[') and '](' in new_clean and new_clean.endswith(')'):
                            added.append(f"• `{old_clean}` ➔ {new_clean}")
                        else:
                            added.append(f"• `{old_clean}` ➔ `{new_clean}`")
                await save_user_data(user_id, 'replacement_words', replacements)
                await event.respond(f"✅ वर्ड रिप्लेसमेंट सेव हुआ!\n" + "\n".join(added))
                del active_conversations[user_id]
                set_settings_step(user_id, None)
            else:
                await event.respond("❌ **अमान्य फॉर्मेट!** कृपया `'पुराना_शब्द' 'नया_शब्द'` या `पुराना -> नया` फॉर्मेट में भेजें।")

async def rename_file(file, sender, edit=None):
    try:
        delete_words = await get_user_data_key(int(sender), 'delete_words', []) or []
        custom_rename_tag = await get_user_data_key(int(sender), 'rename_tag', '') or ''
        replacements = await get_user_data_key(int(sender), 'replacement_words', {}) or {}
        
        dirname, filename = os.path.split(str(file))
        file_base, file_ext = os.path.splitext(filename)
        ext = file_ext.lstrip('.') or 'mp4'
        
        clean_name = file_base
        
        # 1. Apply replacements (case-insensitive, stripping any markdown links for clean filenames)
        for word, replace_word in replacements.items():
            if word:
                rep_str = strip_markdown_link(str(replace_word or ''))
                try:
                    pattern = re.compile(re.escape(word), re.IGNORECASE)
                    clean_name = pattern.sub(lambda m, r=rep_str: r, clean_name)
                except Exception:
                    clean_name = clean_name.replace(word, rep_str)
                    
        # 2. Apply delete words (case-insensitive)
        for word in delete_words:
            if word:
                try:
                    pattern = re.compile(re.escape(word), re.IGNORECASE)
                    clean_name = pattern.sub('', clean_name)
                except Exception:
                    clean_name = clean_name.replace(word, '')
                    
        # 3. Clean up empty brackets and consecutive spaces/underscores
        clean_name = re.sub(r'\[\s*\]|\(\s*\)|\{\s*\}', '', clean_name)
        clean_name = re.sub(r'[\s_]+', ' ', clean_name).strip(' .-_')
        if not clean_name:
            clean_name = f"file_{int(time.time())}"
            
        # 4. Append custom tag
        if custom_rename_tag:
            clean_name = f"{clean_name} {custom_rename_tag}".strip()
            
        new_filename = f"{clean_name}.{ext}"
        new_file_path = os.path.join(dirname, new_filename) if dirname else new_filename
        
        if new_file_path != file and os.path.exists(file):
            os.rename(file, new_file_path)
            return new_file_path
        return file
    except Exception as e:
        logger.error(f"Rename error: {e}")
        return file
