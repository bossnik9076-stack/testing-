import os
import sys
import logging
import urllib.request
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s"
)
logger = logging.getLogger("RestrictedSaverBot")

HTML_DASHBOARD = """<!DOCTYPE html>
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

class StatusHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_DASHBOARD.encode("utf-8"))

    def log_message(self, format, *args):
        # Suppress noisy access log spam in console
        pass

def start_http_server(port: int):
    try:
        server = HTTPServer(("0.0.0.0", port), StatusHandler)
        logger.info(f"Web dashboard started on port {port}.")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server
    except Exception as e:
        logger.warning(f"Failed to start HTTP server on port {port}: {e}")
        return None

# Import config
try:
    from config import BOT_TOKEN, DEFAULT_THUMB, DEFAULT_THUMB_URL, THUMB_DIR
except ImportError:
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    DEFAULT_THUMB = os.getenv("DEFAULT_THUMB", "default_thumb.jpg")
    DEFAULT_THUMB_URL = "https://i.postimg.cc/2ysJtXKC/nikhil.png"
    THUMB_DIR = os.path.join(os.path.dirname(__file__), "thumbnails")

os.makedirs(THUMB_DIR, exist_ok=True)

if not os.path.exists(DEFAULT_THUMB):
    try:
        logger.info(f"Downloading default thumbnail from {DEFAULT_THUMB_URL}...")
        urllib.request.urlretrieve(DEFAULT_THUMB_URL, DEFAULT_THUMB)
        logger.info("Default thumbnail downloaded successfully.")
    except Exception as e:
        logger.warning(f"Failed to download default thumbnail: {e}")

# Try importing bot plugins and shared client
has_bot_deps = False
try:
    from shared_client import app, client as tele_client, userbot
    import plugins.start
    import plugins.login
    import plugins.settings
    import plugins.gencode
    import plugins.stats
    import plugins.admin
    import plugins.batch
    from utils.func import clean_stale_thumbnails, auto_clean_thumbnails_loop
    has_bot_deps = True
except ImportError as e:
    logger.info(f"Bot dependencies not loaded in this environment: {e}")

async def main():
    is_aistudio = bool(os.environ.get("APPLET_ID") or os.environ.get("K_SERVICE"))
    port = 3000 if is_aistudio else int(os.environ.get("PORT", 3000))
    start_http_server(port)

    if not has_bot_deps:
        logger.info(f"Dev server running in web dashboard mode on port {port}.")
        await asyncio.Event().wait()
        return

    # Clean stale thumbnails on startup
    try:
        purged = clean_stale_thumbnails(max_age_seconds=0)
        if purged > 0:
            logger.info(f"Purged {purged} stale temporary thumbnail(s) on startup.")
    except Exception as e:
        logger.warning(f"Error purging stale thumbnails on startup: {e}")

    # Start auto-cleanup loop for temporary thumbnails
    asyncio.create_task(auto_clean_thumbnails_loop())

    # Check if running in AI Studio development preview environment
    # In AI Studio preview, Telegram bot client startup is disabled to avoid AUTH_KEY_DUPLICATED conflict with Render.
    # On Render (or production VPS), APPLET_ID is not present, so the bot starts automatically!
    if is_aistudio or os.environ.get("RUN_TELEGRAM_BOT", "").lower() in ("0", "false", "no"):
        logger.info("AI Studio environment detected: Telegram Bot polling is STOPPED here so it runs exclusively on Render without session conflicts.")
        await asyncio.Event().wait()
        return

    logger.info("Starting Telegram Restricted Content Saver Bot (Pyrogram + Telethon Engine)...")
    
    if tele_client:
        try:
            await tele_client.start(bot_token=BOT_TOKEN)
            logger.info("Telethon Bot Client started successfully.")
        except Exception as e:
            logger.warning(f"Telethon Bot Client start warning: {e}")
    
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
    
    try:
        from utils.func import load_db_peers_into_storage
        await load_db_peers_into_storage(app)
    except Exception as e:
        logger.warning(f"Error loading cached peers into bot storage: {e}")
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Stopping bot...")
    except Exception as e:
        logger.error(f"Error running bot: {e}")
