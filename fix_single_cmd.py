import re

with open("plugins/start.py", "r") as f:
    content = f.read()

single_cmd_code = """async def single_cmd(client: Client, message: Message):
    try: await message.delete()
    except Exception: pass
    if await subscribe(client, message) == 1: return
    user_id = message.from_user.id
    from plugins.batch import get_uclient
    uc = await get_uclient(user_id)
    if not uc:
        await message.reply_text('⚠️ **Login Required**\\n\\nYou must login using /login to extract links.')
        return
    from plugins.batch import Z"""

content = re.sub(r'async def single_cmd\(client: Client, message: Message\):\n    try: await message\.delete\(\)\n    except Exception: pass\n    if await subscribe\(client, message\) == 1: return\n    user_id = message\.from_user\.id\n    from plugins\.batch import Z', single_cmd_code, content)

with open("plugins/start.py", "w") as f:
    f.write(content)
