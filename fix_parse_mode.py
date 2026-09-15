import re

with open("plugins/batch.py", "r") as f:
    content = f.read()

content = content.replace("from pyrogram.errors import UserNotParticipant", "from pyrogram.errors import UserNotParticipant\nfrom pyrogram.enums import ParseMode")

# Add parse_mode=ParseMode.MARKDOWN to copy_message and send_document
content = re.sub(r'caption=(ft if ft else None)', r'caption=\1, parse_mode=ParseMode.MARKDOWN', content)
content = re.sub(r'caption=(ft if m.caption else None)', r'caption=\1, parse_mode=ParseMode.MARKDOWN', content)
content = re.sub(r'caption=(ft if ft else \(m.caption.markdown if m.caption else None\))', r'caption=\1, parse_mode=ParseMode.MARKDOWN', content)

with open("plugins/batch.py", "w") as f:
    f.write(content)
