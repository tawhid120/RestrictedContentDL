# Copyright (C) @TheSmartBisnu
# Channel: https://t.me/itsSmartDev

from os import getenv
from time import time
from dotenv import load_dotenv

try:
    load_dotenv("config.env")
except:
    pass

    if not getenv("BOT_TOKEN") or not getenv("BOT_TOKEN").count(":") == 1:
        print("Error: BOT_TOKEN must be in format '123456:abcdefghijklmnopqrstuvwxyz'")
        exit(1)

    if (
        not getenv("ADMIN_SESSION_STRING")
        or getenv("ADMIN_SESSION_STRING") == "xxxxxxxxxxxxxxxxxxxxxxx"
    ):
        print("Error: ADMIN_SESSION_STRING must be set with a valid string")
        exit(1)

    if not getenv("DATABASE_URI"):
        print("Error: DATABASE_URI must be set")
        exit(1)


# Pyrogram setup
class PyroConf(object):
    API_ID = int(getenv("API_ID", "6"))
    API_HASH = getenv("API_HASH", "eb06d4abfb49dc3eeb1aeb98ae0f581e")
    BOT_TOKEN = getenv("BOT_TOKEN")
    
    # SESSION_STRING এর বদলে ADMIN_SESSION_STRING
    ADMIN_SESSION_STRING = getenv("ADMIN_SESSION_STRING")
    
    # নতুন ডেটাবেস ভেরিয়েবল
    DATABASE_URI = getenv("DATABASE_URI")
    LOG_GROUP_ID = int(getenv("LOG_GROUP_ID", "-4977978574"))
    BOT_START_TIME = time()

    MAX_CONCURRENT_DOWNLOADS = int(getenv("MAX_CONCURRENT_DOWNLOADS", "3"))
    BATCH_SIZE = int(getenv("BATCH_SIZE", "10"))
    FLOOD_WAIT_DELAY = int(getenv("FLOOD_WAIT_DELAY", "3"))
