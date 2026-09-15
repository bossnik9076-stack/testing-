import re
with open("plugins/batch.py", "r") as f:
    code = f.read()

# Add task queue logic right after ACTIVE_USERS = load_active_users()
queue_code = """
# Queue system to limit concurrent users to 3
MAX_CONCURRENT_USERS = 3
TASK_QUEUE = asyncio.Queue()
currently_processing_users = set()

async def process_queue():
    while True:
        uid = await TASK_QUEUE.get()
        currently_processing_users.add(uid)
        
        # We don't process it here, we just let the blocked command continue
        # The command itself will run and when done, call release_task_slot
        
def release_task_slot(uid):
    if uid in currently_processing_users:
        currently_processing_users.remove(uid)
        TASK_QUEUE.task_done()

async def acquire_task_slot(uid, pt_message=None):
    if uid in currently_processing_users:
        return True
        
    if len(currently_processing_users) < MAX_CONCURRENT_USERS:
        currently_processing_users.add(uid)
        return True
        
    if pt_message:
        try:
            await pt_message.edit('⏳ **Queue Full!**\\n\\nAll servers are busy (Max 3 concurrent users).\\nYou are in the queue. Please wait, your task will start automatically soon...')
        except: pass
        
    await TASK_QUEUE.put(uid)
    
    # Wait until it's our turn
    while uid not in currently_processing_users:
        await asyncio.sleep(1)
        
    if pt_message:
        try:
            await pt_message.edit('🚀 **Your turn!**\\n\\nStarting extraction now...')
        except: pass
    return True
"""

if "MAX_CONCURRENT_USERS" not in code:
    code = code.replace("ACTIVE_USERS = load_active_users()", "ACTIVE_USERS = load_active_users()\n" + queue_code)
    
    # Start the queue processor in process_cmd
    old_cmd = """async def process_cmd(c, m):
    uid = m.from_user.id"""
    
    new_cmd = """async def process_cmd(c, m):
    # Ensure queue processor is running
    if not hasattr(process_cmd, "queue_started"):
        asyncio.create_task(process_queue())
        process_cmd.queue_started = True
    uid = m.from_user.id"""
    code = code.replace(old_cmd, new_cmd)

# Add queue logic to text_handler single processing
old_single_start = """        if is_user_active(uid):
            await pt.edit('⚠️ Active task exists. Use /stop first.')
            Z.pop(uid, None)
            return

        try:
            msg = await get_msg(ubot, uc, i, s, lt)"""
            
new_single_start = """        if is_user_active(uid):
            await pt.edit('⚠️ Active task exists. Use /stop first.')
            Z.pop(uid, None)
            return

        await acquire_task_slot(uid, pt)

        try:
            msg = await get_msg(ubot, uc, i, s, lt)"""
code = code.replace(old_single_start, new_single_start)

old_single_end = """            else:
                await pt.edit('❌ Message not found or unable to access.')
        except Exception as e:
            await pt.edit(f'❌ Error: {str(e)[:100]}')
        finally:
            Z.pop(uid, None)"""

new_single_end = """            else:
                await pt.edit('❌ Message not found or unable to access.')
        except Exception as e:
            await pt.edit(f'❌ Error: {str(e)[:100]}')
        finally:
            release_task_slot(uid)
            Z.pop(uid, None)"""
code = code.replace(old_single_end, new_single_end)

# Add queue logic to batch processing
old_batch_start = """        pt = await m.reply_text(f'⏳ Starting batch of {n} messages...')
        uc = await get_uclient(uid)
        if not uc:
            await pt.edit('⚠️ **Login Required**\\n\\nYou must login using /login to extract links. The bot\\'s internal session is disabled for downloading.')
            Z.pop(uid, None)
            return
            
        if is_user_active(uid):
            await pt.edit('⚠️ Active task exists')
            Z.pop(uid, None)
            return
        
        await add_active_batch(uid, {"""
        
new_batch_start = """        pt = await m.reply_text(f'⏳ Checking requirements...')
        uc = await get_uclient(uid)
        if not uc:
            await pt.edit('⚠️ **Login Required**\\n\\nYou must login using /login to extract links. The bot\\'s internal session is disabled for downloading.')
            Z.pop(uid, None)
            return
            
        if is_user_active(uid):
            await pt.edit('⚠️ Active task exists')
            Z.pop(uid, None)
            return
            
        await acquire_task_slot(uid, pt)
        
        await add_active_batch(uid, {"""
code = code.replace(old_batch_start, new_batch_start)

old_batch_end = """            if attempts >= max_attempts and success < n:
                await m.reply_text(f'⚠️ **Batch Stopped!**\\n\\nReached maximum scan attempts. Successfully saved: {success}/{n}')
            else:
                await m.reply_text(f'🎉 **Batch Completed!**\\n\\n✅ Successfully saved: {success}/{n}')
        finally:
            await remove_active_batch(uid)
            Z.pop(uid, None)"""
            
new_batch_end = """            if attempts >= max_attempts and success < n:
                await m.reply_text(f'⚠️ **Batch Stopped!**\\n\\nReached maximum scan attempts. Successfully saved: {success}/{n}')
            else:
                await m.reply_text(f'🎉 **Batch Completed!**\\n\\n✅ Successfully saved: {success}/{n}')
        finally:
            release_task_slot(uid)
            await remove_active_batch(uid)
            Z.pop(uid, None)"""
code = code.replace(old_batch_end, new_batch_end)

with open("plugins/batch.py", "w") as f:
    f.write(code)

