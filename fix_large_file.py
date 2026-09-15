import re

with open("plugins/batch.py", "r") as f:
    content = f.read()

# Replace fsize_mb logic with fsize > 2GB logic
old_block = """        fsize_mb = os.path.getsize(f) / (1024 * 1024)
        th = thumbnail(d)
        
        if fsize_mb > 50 and Y:
            st = time.time()
            await c.edit_message_text(d, p.id, '⚡ Large file (>50MB). Uploading via userbot...')"""

new_block = """        fsize = os.path.getsize(f) / (1024 * 1024 * 1024)
        th = thumbnail(d)
        
        if fsize > 2 and Y:
            st = time.time()
            await c.edit_message_text(d, p.id, '⚡ File is larger than 2GB. Uploading via userbot...')"""

content = content.replace(old_block, new_block)

# Fix the copy_message in that block to use tcid instead of d just in case
content = content.replace("await c.copy_message(d, LOG_GROUP, sent.id, reply_to_message_id=rtmid)", "await c.copy_message(tcid, LOG_GROUP, sent.id, reply_to_message_id=rtmid)")

with open("plugins/batch.py", "w") as f:
    f.write(content)
