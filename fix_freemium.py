import re
with open("plugins/batch.py", "r") as f:
    code = f.read()

# Fix batch empty space display in prog
old_prog = """        try:
            await C.edit_message_text(h, m, f"__**Transferring File...**__\\n\\n{bar}\\n\\n⚡ **Completed**: {c_mb:.2f} MB / {t_mb:.2f} MB\\n📊 **Progress**: {p:.2f}%\\n🚀 **Speed**: {speed:.2f} MB/s\\n⏳ **ETA**: {eta}")
        except Exception:"""

new_prog = """        try:
            await C.edit_message_text(h, m, f"__**Processing...**__\\n\\n{bar}\\n\\n⚡ **Completed**: {c_mb:.2f} MB / {t_mb:.2f} MB\\n🚀 **Speed**: {speed:.2f} MB/s\\n⏳ **ETA**: {eta}")
        except Exception:"""

code = code.replace(old_prog, new_prog)

# Fix maxlimit checks
old_check1 = """        maxlimit = PREMIUM_LIMIT if await is_premium_user(uid) else FREEMIUM_LIMIT
        if count > maxlimit:
            await m.reply_text(f'⚠️ Maximum batch limit is {maxlimit}.')
            return"""
            
old_check2 = """        maxlimit = PREMIUM_LIMIT
        if count > maxlimit:
            await m.reply_text(f'⚠️ Maximum batch limit is {maxlimit}.')
            return"""

new_check = """        is_prem = await is_premium_user(uid)
        maxlimit = PREMIUM_LIMIT if is_prem else FREEMIUM_LIMIT
        if not is_prem and count > 1:
            await m.reply_text("⚠️ **Premium Required**\\n\\nFree users can only extract 1 file at a time.\\nPurchase premium to extract unlimited files! 💎")
            return
        elif is_prem and count > maxlimit:
            await m.reply_text(f'⚠️ Maximum batch limit is {maxlimit}.')
            return"""

code = code.replace(old_check1, new_check).replace(old_check2, new_check)


with open("plugins/batch.py", "w") as f:
    f.write(code)

