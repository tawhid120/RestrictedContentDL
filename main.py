# Copyright (C) @TheSmartBisnu
# Channel: https://t.me/itsSmartDev

import os
import shutil
import psutil
import asyncio
from time import time

from pyleaves import Leaves
from pyrogram.enums import ParseMode
from pyrogram import Client, filters
from pyrogram.errors import PeerIdInvalid, BadRequest, SessionPasswordNeeded, PhoneCodeNeeded, FloodWait
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from helpers.utils import (
    processMediaGroup,
    progressArgs,
    send_media
)

import os

from helpers.files import (
    get_download_path,
    fileSizeLimit,
    get_readable_file_size,
    get_readable_time,
    cleanup_download
)

from helpers.msg import (
    getChatMsgID,
    get_file_name,
    get_parsed_msg
)

# ধাপ ১ থেকে নতুন ইম্পোর্ট
from helpers.database import save_session, get_session, delete_session

from config import PyroConf
from logger import LOGGER

# Initialize the bot client
bot = Client(
    "media_bot",
    api_id=PyroConf.API_ID,
    api_hash=PyroConf.API_HASH,
    bot_token=PyroConf.BOT_TOKEN,
    workers=100,
    parse_mode=ParseMode.MARKDOWN,
    max_concurrent_transmissions=20,
    sleep_threshold=30,
)

# Client for user session (ধাপ ১ অনুযায়ী পরিবর্তিত)
# 'user' এর বদলে 'admin_client' এবং 'ADMIN_SESSION_STRING' ব্যবহার করা হচ্ছে
admin_client = Client(
    "admin_session", # সেশনের নাম পরিবর্তন করা হয়েছে
    workers=100,
    session_string=PyroConf.ADMIN_SESSION_STRING, # ADMIN_SESSION_STRING ব্যবহার করা হচ্ছে
    max_concurrent_transmissions=20,
    sleep_threshold=30,
)

RUNNING_TASKS = set()
download_semaphore = None

# নতুন: ইউজার স্টেট ট্র্যাক করার জন্য
USER_AWAITING_SESSION = set()

def track_task(coro):
    task = asyncio.create_task(coro)
    RUNNING_TASKS.add(task)
    def _remove(_):
        RUNNING_TASKS.discard(task)
    task.add_done_callback(_remove)
    return task


@bot.on_message(filters.command("start") & filters.private)
async def start(_, message: Message):
    welcome_text = (
        "👋 **Welcome to Media Downloader Bot!**\n\n"
        "I can grab photos, videos, audio, and documents from any Telegram post.\n"
        "Just send me a link (paste it directly or use `/dl <link>`),\n"
        "or reply to a message with `/dl`.\n\n"
        "**New Features:**\n"
        "➤ Use `/login` to add your own account for private channels.\n"
        "➤ Use `/myaccount` to check your login status.\n"
        "➤ Use `/logout` to remove your account.\n\n"
        "ℹ️ Use `/help` to view all commands and examples.\n"
        "🔒 Make sure your account (or bot's admin account) is part of the chat.\n\n"
        "Ready? Send me a Telegram post link!"
    )

    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Update Channel", url="https://t.me/itsSmartDev")]]
    )
    await message.reply(welcome_text, reply_markup=markup, disable_web_page_preview=True)


@bot.on_message(filters.command("help") & filters.private)
async def help_command(_, message: Message):
    help_text = (
        "💡 **Media Downloader Bot Help**\n\n"
        "➤ **Download Media**\n"
        "   – Send `/dl <post_URL>` **or** just paste a Telegram post link to fetch photos, videos, audio, or documents.\n\n"
        "➤ **Batch Download**\n"
        "   – Send `/bdl start_link end_link` to grab a series of posts in one go.\n"
        "     💡 Example: `/bdl https://t.me/mychannel/100 https://t.me/mychannel/120`\n"
        "**It will download all posts from ID 100 to 120.**\n\n"
        "➤ **Account Management (New!)**\n"
        "   – `/login`: Add your personal account to access private chats.\n"
        "   – `/myaccount`: Check if you have an account linked.\n"
        "   – `/logout`: Remove your account from the bot.\n\n"
        "➤ **Requirements**\n"
        "   – Make sure the admin account (for public links) or your personal account (for private links) is part of the chat.\n\n"
        "➤ **If the bot hangs**\n"
        "   – Send `/killall` to cancel any pending downloads.\n\n"
        "➤ **Logs**\n"
        "   – Send `/logs` to download the bot’s logs file.\n\n"
        "➤ **Stats**\n"
        "   – Send `/stats` to view current status."
    )
    
    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Update Channel", url="https://t.me/itsSmartDev")]]
    )
    await message.reply(help_text, reply_markup=markup, disable_web_page_preview=True)


# --- নতুন লগইন কমান্ড (ধাপ ২) ---

@bot.on_message(filters.command("login") & filters.private)
async def login(_, message: Message):
    if message.from_user.id in USER_AWAITING_SESSION:
        USER_AWAITING_SESSION.discard(message.from_user.id)
        
    await message.reply(
        "🔒 **Account Login**\n\n"
        "দয়া করে আপনার Pyrogram v2 (String) সেশনটি পরবর্তী মেসেজে পাঠান।\n\n"
        "**সতর্কতা:** আপনার সেশন স্ট্রিং সরাসরি আমাদের ডেটাবেসে সেভ করা হবে। এটি দিয়ে আপনার অ্যাকাউন্টে সম্পূর্ণ অ্যাক্সেস নেওয়া সম্ভব।\n"
        "প্রয়োজন হলে `/logout` ব্যবহার করে সেশনটি ডিলিট করতে পারবেন।\n\n"
        "ℹ️ সেশন জেনারেট করতে @SmartUtilBot এ /pyro কমান্ডটি ব্যবহার করুন।"
    )
    USER_AWAITING_SESSION.add(message.from_user.id)


@bot.on_message(filters.command("logout") & filters.private)
async def logout(_, message: Message):
    user_id = message.from_user.id
    if await get_session(user_id):
        await delete_session(user_id)
        await message.reply("✅ আপনার অ্যাকাউন্ট সফলভাবে লগআউট করা হয়েছে।")
    else:
        await message.reply("❌ আপনি লগইন করা নেই।")


@bot.on_message(filters.command("myaccount") & filters.private)
async def my_account(_, message: Message):
    user_id = message.from_user.id
    session_string = await get_session(user_id)
    
    if session_string:
        try:
            # সেশনটি ভ্যালিড কিনা তা পরীক্ষা করুন
            temp_client = Client(
                f"check_session_{user_id}",
                api_id=PyroConf.API_ID,
                api_hash=PyroConf.API_HASH,
                session_string=session_string,
                in_memory=True
            )
            await temp_client.start()
            user_data = await temp_client.get_me()
            await temp_client.stop()
            
            await message.reply(
                f"✅ **আপনি লগইন আছেন।**\n\n"
                f"**ইউজারনেম:** @{user_data.username}\n"
                f"**নাম:** {user_data.first_name}\n"
                f"**ID:** `{user_data.id}`"
            )
        except FloodWait as e:
            await message.reply(f"⏳ অনুগ্রহ করে {e.value} সেকেন্ড পরে আবার চেষ্টা করুন।")
        except Exception as e:
            await delete_session(user_id) # ভাঙা সেশন ডিলিট করুন
            await message.reply(
                f"❌ **সেশনটি অবৈধ বা এক্সপায়ার হয়ে গেছে।**\n"
                f"এটি ডেটাবেস থেকে মুছে ফেলা হয়েছে। দয়া করে আবার `/login` করুন।\n\n"
                f"(`{e}`)"
            )
    else:
        await message.reply("❌ আপনি লগইন করা নেই। `/login` ব্যবহার করে লগইন করুন।")

# --- লগইন শেষ ---


async def handle_download(bot: Client, message: Message, post_url: str):
    async with download_semaphore:
        if "?" in post_url:
            post_url = post_url.split("?", 1)[0]

        try:
            chat_id, message_id = getChatMsgID(post_url)
            
            # --- এখানে পরিবর্তন করা হয়েছে ---
            # এখন শুধু 'admin_client' ব্যবহার করা হচ্ছে। 
            # ধাপ ৩-এ আমরা এখানে ইউজার-স্পেসিফিক ক্লায়েন্ট যোগ করব।
            chat_message = await admin_client.get_messages(chat_id=chat_id, message_ids=message_id)

            LOGGER(__name__).info(f"Downloading media from URL: {post_url}")

            if chat_message.document or chat_message.video or chat_message.audio:
                file_size = (
                    chat_message.document.file_size
                    if chat_message.document
                    else chat_message.video.file_size
                    if chat_message.video
                    else chat_message.audio.file_size
                )
                
                # 'user.me.is_premium' এর বদলে 'admin_client.me.is_premium'
                if not await fileSizeLimit(
                    file_size, message, "download", admin_client.me.is_premium
                ):
                    return

            parsed_caption = await get_parsed_msg(
                chat_message.caption or "", chat_message.caption_entities
            )
            parsed_text = await get_parsed_msg(
                chat_message.text or "", chat_message.entities
            )

            if chat_message.media_group_id:
                if not await processMediaGroup(chat_message, bot, message):
                    await message.reply(
                        "**Could not extract any valid media from the media group.**"
                    )
                return

            elif chat_message.media:
                start_time = time()
                progress_message = await message.reply("**📥 Downloading Progress...**")

                filename = get_file_name(message_id, chat_message)
                download_path = get_download_path(message.id, filename)

                # 'chat_message.download' ব্যবহার করা হচ্ছে, যা সঠিক ক্লায়েন্ট (admin_client) থেকেই কল হবে
                media_path = await chat_message.download(
                    file_name=download_path,
                    progress=Leaves.progress_for_pyrogram,
                    progress_args=progressArgs(
                        "📥 Downloading Progress", progress_message, start_time
                    ),
                )

                if not media_path or not os.path.exists(media_path):
                    await progress_message.edit("**❌ Download failed: File not saved properly**")
                    return

                file_size = os.path.getsize(media_path)
                if file_size == 0:
                    await progress_message.edit("**❌ Download failed: File is empty**")
                    cleanup_download(media_path)
                    return

                LOGGER(__name__).info(f"Downloaded media: {media_path} (Size: {file_size} bytes)")

                media_type = (
                    "photo"
                    if chat_message.photo
                    else "video"
                    if chat_message.video
                    else "audio"
                    if chat_message.audio
                    else "document"
                )
                await send_media(
                    bot,
                    message,
                    media_path,
                    media_type,
                    parsed_caption,
                    progress_message,
                    start_time,
                )

                cleanup_download(media_path)
                await progress_message.delete()

            elif chat_message.text or chat_message.caption:
                await message.reply(parsed_text or parsed_caption)
            else:
                await message.reply("**No media or text found in the post URL.**")

        except (PeerIdInvalid, BadRequest, KeyError):
            # ধাপ ৩-এ আমরা এই মেসেজটি পরিবর্তন করব
            await message.reply("**Make sure the admin client is part of the chat.**")
        except Exception as e:
            error_message = f"**❌ {str(e)}**"
            await message.reply(error_message)
            LOGGER(__name__).error(e)


@bot.on_message(filters.command("dl") & filters.private)
async def download_media(bot: Client, message: Message):
    if len(message.command) < 2:
        await message.reply("**Provide a post URL after the /dl command.**")
        return

    post_url = message.command[1]
    await track_task(handle_download(bot, message, post_url))


@bot.on_message(filters.command("bdl") & filters.private)
async def download_range(bot: Client, message: Message):
    args = message.text.split()

    if len(args) != 3 or not all(arg.startswith("https://t.me/") for arg in args[1:]):
        await message.reply(
            "🚀 **Batch Download Process**\n"
            "`/bdl start_link end_link`\n\n"
            "💡 **Example:**\n"
            "`/bdl https://t.me/mychannel/100 https://t.me/mychannel/120`"
        )
        return

    try:
        start_chat, start_id = getChatMsgID(args[1])
        end_chat,   end_id   = getChatMsgID(args[2])
    except Exception as e:
        return await message.reply(f"**❌ Error parsing links:\n{e}**")

    if start_chat != end_chat:
        return await message.reply("**❌ Both links must be from the same channel.**")
    if start_id > end_id:
        return await message.reply("**❌ Invalid range: start ID cannot exceed end ID.**")

    try:
        # 'user' এর বদলে 'admin_client'
        await admin_client.get_chat(start_chat)
    except Exception:
        pass

    prefix = args[1].rsplit("/", 1)[0]
    loading = await message.reply(f"📥 **Downloading posts {start_id}–{end_id}…**")

    downloaded = skipped = failed = 0
    batch_tasks = []
    BATCH_SIZE = PyroConf.BATCH_SIZE

    for msg_id in range(start_id, end_id + 1):
        url = f"{prefix}/{msg_id}"
        try:
            # 'user' এর বদলে 'admin_client'
            chat_msg = await admin_client.get_messages(chat_id=start_chat, message_ids=msg_id)
            if not chat_msg:
                skipped += 1
                continue

            has_media = bool(chat_msg.media_group_id or chat_msg.media)
            has_text  = bool(chat_msg.text or chat_msg.caption)
            if not (has_media or has_text):
                skipped += 1
                continue

            task = track_task(handle_download(bot, message, url))
            batch_tasks.append(task)

            if len(batch_tasks) >= BATCH_SIZE:
                results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, asyncio.CancelledError):
                        await loading.delete()
                        return await message.reply(
                            f"**❌ Batch canceled** after downloading `{downloaded}` posts."
                        )
                    elif isinstance(result, Exception):
                        failed += 1
                        LOGGER(__name__).error(f"Error: {result}")
                    else:
                        downloaded += 1

                batch_tasks.clear()
                await asyncio.sleep(PyroConf.FLOOD_WAIT_DELAY)

        except Exception as e:
            failed += 1
            LOGGER(__name__).error(f"Error at {url}: {e}")

    if batch_tasks:
        results = await asyncio.gather(*batch_tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                failed += 1
            else:
                downloaded += 1

    await loading.delete()
    await message.reply(
        "**✅ Batch Process Complete!**\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"📥 **Downloaded** : `{downloaded}` post(s)\n"
        f"⏭️ **Skipped** : `{skipped}` (no content)\n"
        f"❌ **Failed** : `{failed}` error(s)"
    )


@bot.on_message(
    filters.private & 
    filters.text &
    ~filters.command(["start", "help", "dl", "bdl", "stats", "logs", "killall", "login", "logout", "myaccount"])
)
async def handle_any_message(bot: Client, message: Message):
    user_id = message.from_user.id
    
    # নতুন: ইউজার সেশন স্ট্রিং সেভ করা
    if user_id in USER_AWAITING_SESSION:
        USER_AWAITING_SESSION.discard(user_id)
        session_string = message.text.strip()
        
        try:
            # সেশনটি ভ্যালিড কিনা তা পরীক্ষা করুন
            LOGGER(__name__).info(f"Checking session for user {user_id}")
            temp_client = Client(
                f"check_session_{user_id}",
                api_id=PyroConf.API_ID,
                api_hash=PyroConf.API_HASH,
                session_string=session_string,
                in_memory=True
            )
            await temp_client.start()
            user_data = await temp_client.get_me()
            await temp_client.stop()
            
            # সেশন সেভ করুন
            await save_session(user_id, session_string)
            LOGGER(__name__).info(f"Session saved for user {user_id}")
            await message.reply(
                f"✅ **সেশন সফলভাবে সেভ করা হয়েছে!**\n\n"
                f"**ইউজারনেম:** @{user_data.username}\n"
                f"**নাম:** {user_data.first_name}\n\n"
                "এখন আপনি আপনার প্রাইভেট চ্যানেল/গ্রুপ থেকে ডাউনলোড করতে পারবেন।"
            )
        except (SessionPasswordNeeded, PhoneCodeNeeded):
            await message.reply("❌ **সেশনটি 2FA (Two-Factor Authentication) প্রটেক্টেড।**\nদয়া করে 2FA ছাড়া একটি সেশন স্ট্রিং দিন।")
        except FloodWait as e:
            await message.reply(f"⏳ অনুগ্রহ করে {e.value} সেকেন্ড পরে আবার চেষ্টা করুন।")
        except Exception as e:
            LOGGER(__name__).error(f"Session check failed for {user_id}: {e}")
            await message.reply(f"❌ **সেশনটি অবৈধ।**\nদয়া করে একটি সঠিক Pyrogram v2 সেশন স্ট্রিং দিন।\n\n(`{e}`)")
        return

    # পুরানো লজিক: যদি সেশন স্ট্রিং না হয়, তবে লিংক হিসেবে গণ্য করুন
    if message.text and message.text.startswith("https://t.me/"):
        await track_task(handle_download(bot, message, message.text))
    else:
        await message.reply("দয়া করে একটি বৈধ টেলিগ্রাম পোস্ট লিঙ্ক পাঠান অথবা `/help` দেখুন।")


@bot.on_message(filters.command("stats") & filters.private)
async def stats(_, message: Message):
    currentTime = get_readable_time(time() - PyroConf.BOT_START_TIME)
    total, used, free = shutil.disk_usage(".")
    total = get_readable_file_size(total)
    used = get_readable_file_size(used)
    free = get_readable_file_size(free)
    sent = get_readable_file_size(psutil.net_io_counters().bytes_sent)
    recv = get_readable_file_size(psutil.net_io_counters().bytes_recv)
    cpuUsage = psutil.cpu_percent(interval=0.5)
    memory = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent
    process = psutil.Process(os.getpid())

    stats = (
        "**≧◉◡◉≦ Bot is Up and Running successfully.**\n\n"
        f"**➜ Bot Uptime:** `{currentTime}`\n"
        f"**➜ Total Disk Space:** `{total}`\n"
        f"**➜ Used:** `{used}`\n"
        f"**➜ Free:** `{free}`\n"
        f"**➜ Memory Usage:** `{round(process.memory_info()[0] / 1024**2)} MiB`\n\n"
        f"**➜ Upload:** `{sent}`\n"
        f"**➜ Download:** `{recv}`\n\n"
        f"**➜ CPU:** `{cpuUsage}%` | "
        f"**➜ RAM:** `{memory}%` | "
        f"**➜ DISK:** `{disk}%`"
    )
    await message.reply(stats)


@bot.on_message(filters.command("logs") & filters.private)
async def logs(_, message: Message):
    if os.path.exists("logs.txt"):
        await message.reply_document(document="logs.txt", caption="**Logs**")
    else:
        await message.reply("**Not exists**")


@bot.on_message(filters.command("killall") & filters.private)
async def cancel_all_tasks(_, message: Message):
    cancelled = 0
    for task in list(RUNNING_TASKS):
        if not task.done():
            task.cancel()
            cancelled += 1
    await message.reply(f"**Cancelled {cancelled} running task(s).**")


async def initialize():
    global download_semaphore
    download_semaphore = asyncio.Semaphore(PyroConf.MAX_CONCURRENT_DOWNLOADS)

if __name__ == "__main__":
    try:
        LOGGER(__name__).info("Bot Started!")
        asyncio.get_event_loop().run_until_complete(initialize())
        # 'user' এর বদলে 'admin_client' স্টার্ট করা হচ্ছে
        admin_client.start()
        bot.run()
    except KeyboardInterrupt:
        pass
    except Exception as err:
        LOGGER(__name__).error(err)
    finally:
        LOGGER(__name__).info("Bot Stopped")

