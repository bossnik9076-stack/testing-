import re

with open("plugins/batch.py", "r") as f:
    content = f.read()

# We need to change the `for j in range(n):` to a while loop in `s == 'count'` branch
old_code = """        try:
            for j in range(n):
                if should_cancel(uid):
                    await pt.edit(f'🛑 Batch cancelled at {j}/{n}. Success: {success}')
                    break
                
                await update_batch_progress(uid, j, success)
                mid = int(s) + j
                
                try:
                    msg = await get_msg(c, uc, i, mid, lt)
                    if msg:
                        res = await process_msg(c, uc, msg, str(m.chat.id), lt, uid, i)
                        if 'Done' in res or 'Copied' in res or 'Sent' in res or 'Forwarded' in res:
                            success += 1
                        try:
                            await pt.edit(f'📦 Batch Progress: {success}/{n} | ✅ Success: {success}')
                        except Exception:
                            pass
                    else:
                        try:
                            await pt.edit(f'📦 Batch Progress: {success}/{n} (Msg {mid} empty/skipped) | ✅ Success: {success}')
                        except Exception:
                            pass
                except asyncio.CancelledError:
                    await pt.edit(f'🛑 Batch cancelled at {success}/{n}. Success: {success}')
                    break
                except Exception as e:
                    try:
                        await pt.edit(f'📦 Batch Progress: {success}/{n}: Error - {str(e)[:40]}')
                    except Exception:
                        pass
                
                await asyncio.sleep(2)
            
            await m.reply_text(f'🎉 **Batch Completed!**\\n\\n✅ Successfully saved: {success}/{n}')"""

# Wait, let me just replace the exact logic by using a custom script that finds the function and replaces it.
