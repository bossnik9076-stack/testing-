import re

with open("plugins/start.py", "r") as f:
    content = f.read()

single_cb = """@app.on_callback_query(filters.regex("^btn_single$"))
async def btn_single_cb(client: Client, callback: CallbackQuery):
    if await subscribe(client, callback) == 1: return
    user_id = callback.from_user.id
    from plugins.batch import get_uclient
    uc = await get_uclient(user_id)
    if not uc:
        await callback.answer("⚠️ Login Required! Please login first.", show_alert=True)
        return
    from plugins.batch import Z"""

batch_cb = """@app.on_callback_query(filters.regex("^btn_batch$"))
async def btn_batch_cb(client: Client, callback: CallbackQuery):
    if await subscribe(client, callback) == 1: return
    user_id = callback.from_user.id
    from plugins.batch import get_uclient
    uc = await get_uclient(user_id)
    if not uc:
        await callback.answer("⚠️ Login Required! Please login first.", show_alert=True)
        return
    from plugins.batch import Z"""

content = re.sub(r'@app\.on_callback_query\(filters\.regex\("\^btn_single\$"\)\)\nasync def btn_single_cb\(client: Client, callback: CallbackQuery\):\n    if await subscribe\(client, callback\) == 1: return\n    user_id = callback\.from_user\.id\n    from plugins\.batch import Z', single_cb, content)

content = re.sub(r'@app\.on_callback_query\(filters\.regex\("\^btn_batch\$"\)\)\nasync def btn_batch_cb\(client: Client, callback: CallbackQuery\):\n    if await subscribe\(client, callback\) == 1: return\n    user_id = callback\.from_user\.id\n    from plugins\.batch import Z', batch_cb, content)

with open("plugins/start.py", "w") as f:
    f.write(content)
