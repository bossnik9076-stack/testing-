import os
import sys
import logging
import urllib.request
import asyncio
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from config import BOT_TOKEN, DEFAULT_THUMB, DEFAULT_THUMB_URL, THUMB_DIR
from shared_client import app, client as tele_client

import plugins.start
import plugins.login
import plugins.settings
import plugins.gencode
import plugins.stats
import plugins.admin
import plugins.batch

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s"
)
logger = logging.getLogger("RestrictedSaverBot")

os.makedirs(THUMB_DIR, exist_ok=True)

if not os.path.exists(DEFAULT_THUMB):
    try:
        logger.info(f"Downloading default thumbnail from {DEFAULT_THUMB_URL}...")
        urllib.request.urlretrieve(DEFAULT_THUMB_URL, DEFAULT_THUMB)
        logger.info("Default thumbnail downloaded successfully.")
    except Exception as e:
        logger.warning(f"Failed to download default thumbnail: {e}")

async def main():
    # Start web dashboard on port 3000 for AI Studio health check and live preview
    try:
        from aiohttp import web
        async def web_handler(request):
            html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Telegram Content Saver Bot</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0b0f19; color: #f1f5f9; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; }
        .card { background: #131c31; border: 1px solid #233253; border-radius: 16px; padding: 32px; max-width: 520px; width: 100%; box-shadow: 0 10px 30px rgba(0,0,0,0.5); text-align: center; }
        .badge { display: inline-flex; align-items: center; background: rgba(34,197,94,0.15); color: #4ade80; border: 1px solid rgba(34,197,94,0.3); border-radius: 9999px; padding: 6px 16px; font-size: 13px; font-weight: 600; margin-bottom: 20px; }
        .dot { width: 8px; height: 8px; background: #22c55e; border-radius: 50%; margin-right: 8px; animation: pulse 2s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(0.85); } }
        h1 { font-size: 24px; margin: 0 0 10px; color: #ffffff; }
        p { color: #94a3b8; font-size: 14px; line-height: 1.6; margin: 0 0 24px; }
        .features { display: flex; flex-direction: column; gap: 10px; text-align: left; background: #0d1527; padding: 18px; border-radius: 12px; border: 1px solid #1c2b48; }
        .feat-item { font-size: 13px; color: #cbd5e1; display: flex; align-items: center; gap: 10px; }
        .feat-item span { color: #38bdf8; font-weight: bold; }
        .bot-link { display: inline-block; margin-top: 24px; background: #0284c7; color: white; text-decoration: none; padding: 12px 24px; border-radius: 10px; font-weight: 600; font-size: 14px; transition: background 0.2s; }
        .bot-link:hover { background: #0369a1; }
    </style>
</head>
<body>
    <div class="card">
        <div class="badge"><div class="dot"></div> BOT IS LIVE & RUNNING</div>
        <h1>Telegram Restricted Content Saver</h1>
        <p>Pyrogram & Telethon Dual-Engine Bot is active. Public links forward directly, and private channel links download and upload smoothly.</p>
        <div class="features">
            <div class="feat-item"><span>✓</span> Public Links: Direct Forward / Fast Copy</div>
            <div class="feat-item"><span>✓</span> Private Links: Auto-fetch & Download / Upload</div>
            <div class="feat-item"><span>✓</span> Commands: /single, /batch, /start, /login</div>
            <div class="feat-item"><span>✓</span> Session: UserBot engine connected</div>
        </div>
        <a href="https://t.me/nikhilkeliyebot" target="_blank" class="bot-link">Open Bot @nikhilkeliyebot</a>
    </div>
</body>
</html>"""
            return web.Response(text=html, content_type="text/html")

        web_app = web.Application()
        web_app.router.add_get('/', web_handler)
        web_app.router.add_get('/health', lambda r: web.Response(text="OK"))
        runner = web.AppRunner(web_app)
        await runner.setup()
        port = int(os.environ.get("PORT", 8080))
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        logger.info(f"Web dashboard started on port {port}.")
    except Exception as e:
        logger.warning(f"Failed to start web server: {e}")

    logger.info("Starting Telegram Restricted Content Saver Bot (Pyrogram + Telethon Engine)...")
    
    if tele_client:
        try:
            await tele_client.start(bot_token=BOT_TOKEN)
            logger.info("Telethon Bot Client started successfully.")
        except Exception as e:
            logger.warning(f"Telethon Bot Client start warning: {e}")
    
    from shared_client import userbot
    if userbot:
        try:
            await userbot.start()
            logger.info("Pyrogram UserBot Client started successfully.")
            try:
                async for _ in userbot.get_dialogs(limit=50): pass
                logger.info("UserBot dialogs cached.")
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"UserBot start warning: {e}")

    await app.start()
    logger.info("Pyrogram Bot Client started successfully. Bot is fully online!")
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Stopping bot...")
    except Exception as e:
        logger.error(f"Error running bot: {e}")
