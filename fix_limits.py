import re
with open("config.py", "r") as f:
    config_code = f.read()

config_code = re.sub(r'FREEMIUM_LIMIT\s*=\s*int\(os\.getenv\("FREEMIUM_LIMIT",\s*"1000"\)\)', 'FREEMIUM_LIMIT = int(os.getenv("FREEMIUM_LIMIT", "1"))', config_code)
config_code = re.sub(r'PREMIUM_LIMIT\s*=\s*int\(os\.getenv\("PREMIUM_LIMIT",\s*"1000"\)\)', 'PREMIUM_LIMIT  = int(os.getenv("PREMIUM_LIMIT", "50000"))', config_code)

with open("config.py", "w") as f:
    f.write(config_code)
