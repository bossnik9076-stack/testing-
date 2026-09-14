import string
import random
import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import OWNER_ID
from utils.func import users_collection

VALID_KEYS = {}

def generate_key(days: int):
    key = "VIP-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=10))
    VALID_KEYS[key] = days
    return key

@Client.on_message(filters.command("gencode") & filters.user(OWNER_ID))
async def gencode_cmd(client, message):
    if len(message.command) < 2:
        return await message.reply("Usage: /gencode <days>")
    try:
        days = int(message.command[1])
        key = generate_key(days)
        await message.reply(f"✅ **VIP Key Generated**\n\n🔑 Key: `{key}`\n⏳ Validity: `{days} Days`\n\nSend this key to the user. They can use `/redeem {key}`")
    except ValueError:
        await message.reply("Days must be an integer.")

@Client.on_message(filters.command("redeem"))
async def redeem_cmd(client, message):
    if len(message.command) < 2:
        return await message.reply("Usage: /redeem <key>")
    key = message.command[1]
    if key in VALID_KEYS:
        days = VALID_KEYS.pop(key)
        # Update user in DB
        expiry = datetime.datetime.now() + datetime.timedelta(days=days)
        await users_collection.update_one(
            {"user_id": message.from_user.id},
            {"$set": {"is_vip": True, "vip_expiry": expiry}},
            upsert=True
        )
        await message.reply(f"🎉 **Congratulations!**\n\nYou have successfully redeemed the VIP key.\nYour VIP access is valid for {days} days.")
    else:
        await message.reply("❌ Invalid or already used key.")
