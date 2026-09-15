import re
with open("plugins/batch.py", "r") as f:
    code = f.read()

old_loop = """                    msg = await get_msg(c, uc, i, mid, lt)
                    if msg:
                        has_media = getattr(msg, "media", None) is not None
                        if not has_media:
                            try:
                                await pt.edit(f'📦 Batch Progress: {success}/{n} (Msg {mid} text/empty skipped) | ✅ Success: {success}')
                            except Exception:
                                pass
                            continue
                            
                        res = await process_msg(c, uc, msg, str(m.chat.id), lt, uid, i)
                        if 'Done' in res or 'Copied' in res or 'Sent' in res or 'Forwarded' in res:
                            success += 1
                        try:
                            await pt.edit(f'📦 Batch Progress: {success}/{n} | ✅ Success: {success}')
                        except Exception:
                            pass
                    else:
                        try:
                            await pt.edit(f'📦 Batch Progress: {success}/{n} (Msg {mid} not found) | ✅ Success: {success}')
                        except Exception:
                            pass
                except asyncio.CancelledError:
                    await pt.edit(f'🛑 Batch cancelled. Success: {success}/{n}')
                    break
                except Exception as e:
                    try:
                        await pt.edit(f'📦 Batch Progress: {success}/{n}: Error - {str(e)[:40]}')
                    except Exception:
                        pass"""

new_loop = """                    try:
                        await pt.edit(f'⏳ Processing msg {j+1}/{n}...')
                    except Exception:
                        pass
                    msg = await get_msg(c, uc, i, mid, lt)
                    if msg:
                        has_media = getattr(msg, "media", None) is not None
                        # Don't skip if it has text, let it process
                        if not has_media and not getattr(msg, "text", None):
                            continue
                            
                        res = await process_msg(c, uc, msg, str(m.chat.id), lt, uid, i)
                        if res and any(x in res for x in ['Done', 'Copied', 'Sent', 'Forwarded']):
                            success += 1
                except asyncio.CancelledError:
                    await pt.edit(f'🛑 Batch cancelled. Success: {success}/{n}')
                    break
                except Exception as e:
                    pass"""

code = code.replace(old_loop, new_loop)

# Fix single empty msg bug
old_single_check = """        try:
            msg = await get_msg(ubot, uc, i, s, lt)
            if msg:
                res = await process_msg(ubot, uc, msg, str(m.chat.id), lt, uid, i)
                await pt.edit(f'✅ 1/1: {res}')
            else:
                await pt.edit('❌ Message not found or unable to access.')
        except Exception as e:"""

new_single_check = """        try:
            msg = await get_msg(ubot, uc, i, s, lt)
            if msg:
                if not getattr(msg, "media", None) and not getattr(msg, "text", None):
                     await pt.edit('❌ This message is completely empty or just an unsupported type.')
                else:
                     res = await process_msg(ubot, uc, msg, str(m.chat.id), lt, uid, i)
                     await pt.edit(f'✅ 1/1: {res}')
            else:
                await pt.edit('❌ Message not found or unable to access.')
        except Exception as e:"""
        
code = code.replace(old_single_check, new_single_check)

with open("plugins/batch.py", "w") as f:
    f.write(code)

