import re
with open("plugins/batch.py", "r") as f:
    code = f.read()

# Fix the batch progress to only show processing and successful files, not errors or missing msgs unless it completely fails
old_batch_loop = """                try:
                    msg = await get_msg(ubot, uc, i, mid, lt)
                    if msg:
                        res = await process_msg(ubot, uc, msg, str(m.chat.id), lt, uid, i)
                        if res and any(x in res for x in ['Done', 'Copied', 'Sent', 'Forwarded']):
                            success += 1
                            try:
                                await pt.edit(f'📦 Batch Progress: {success}/{n} | ✅ Success: {success}')
                            except Exception:
                                pass
                        else:
                            try:
                                await pt.edit(f'📦 Batch Progress: {success}/{n} (Msg {mid} failed) | ✅ Success: {success}')
                            except Exception:
                                pass
                    else:
                        try:
                            await pt.edit(f'📦 Batch Progress: {success}/{n} (Msg {mid} not found) | ✅ Success: {success}')
                        except Exception:
                            pass
                except Exception as e:
                    try:
                        await pt.edit(f'📦 Batch Progress: {success}/{n}: Error - {str(e)[:40]}')
                    except Exception:
                        pass"""

new_batch_loop = """                try:
                    try:
                        await pt.edit(f'⏳ Processing msg {j+1}/{n}...')
                    except Exception:
                        pass
                    msg = await get_msg(ubot, uc, i, mid, lt)
                    if msg:
                        # Skip empty text message (e.g. only text but user requested empty link)
                        if not msg.media and not msg.text:
                            continue
                            
                        res = await process_msg(ubot, uc, msg, str(m.chat.id), lt, uid, i)
                        if res and any(x in res for x in ['Done', 'Copied', 'Sent', 'Forwarded']):
                            success += 1
                except Exception as e:
                    pass"""

code = code.replace(old_batch_loop, new_batch_loop)

# Fix empty message link extraction bug
old_single_msg = """        try:
            msg = await get_msg(ubot, uc, i, s, lt)
            if msg:
                res = await process_msg(ubot, uc, msg, str(m.chat.id), lt, uid, i)
                await pt.edit(f'✅ 1/1: {res}')
            else:
                await pt.edit('❌ Message not found or unable to access.')
        except Exception as e:"""

new_single_msg = """        try:
            msg = await get_msg(ubot, uc, i, s, lt)
            if msg:
                if not msg.media and not msg.text:
                     await pt.edit('❌ This message is completely empty or just an unsupported type.')
                else:
                     res = await process_msg(ubot, uc, msg, str(m.chat.id), lt, uid, i)
                     await pt.edit(f'✅ 1/1: {res}')
            else:
                await pt.edit('❌ Message not found or unable to access.')
        except Exception as e:"""
        
code = code.replace(old_single_msg, new_single_msg)


with open("plugins/batch.py", "w") as f:
    f.write(code)

