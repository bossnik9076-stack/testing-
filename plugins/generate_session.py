from pyrogram import Client, filters
from config import API_ID, API_HASH

@Client.on_message(filters.command("generate_session") & filters.private)
async def generate_session_cmd(client, message):
    await message.reply(
        "🔑 **Session Generator** 🔑\n\n"
        "To generate a new Pyrogram V2 session string, simply use the `/login` command.\n\n"
        "**Steps:**\n"
        "1. Send `/login`\n"
        "2. Enter your phone number with country code (e.g., +919876543210)\n"
        "3. Enter the OTP sent to your Telegram app\n"
        "4. Enter your 2-Step Password (if enabled)\n\n"
        "Once logged in, the session string will be safely stored in the database for extracting restricted content.\n\n"
        "You can logout anytime using `/logout`."
    )
