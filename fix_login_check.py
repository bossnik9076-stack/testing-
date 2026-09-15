import re

with open("plugins/batch.py", "r") as f:
    content = f.read()

# Modify process_cmd to check login
process_cmd_code = """async def process_cmd(c, m):
    uid = m.from_user.id
    cmd = m.command[0]
    
    if await sub(c, m) == 1: return
    
    uc = await get_uclient(uid)
    if not uc:
        await m.reply_text('⚠️ **Login Required**\\n\\nYou must login using /login to extract links. The bot\\'s internal session is disabled for downloading.')
        return
        
    if is_user_active(uid):"""

content = re.sub(r'async def process_cmd\(c, m\):\n    uid = m\.from_user\.id\n    cmd = m\.command\[0\]\n    \n    if await sub\(c, m\) == 1: return\n    \n    if is_user_active\(uid\):', process_cmd_code, content)

with open("plugins/batch.py", "w") as f:
    f.write(content)
