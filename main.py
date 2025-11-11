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
from pyrogram.errors import (
    PeerIdInvalid, 
    BadRequest, 
    SessionPasswordNeeded,
    FloodWait,
    PhoneCodeInvalid, 
    PasswordHashInvalid,
    UserNotParticipant # --- ধাপ ৩ এ নতুন ইম্পোর্ট ---
)
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from helpers.utils import (
    processMediaGroup,
    progressArgs,
    send_media
)
# (helpers.database ইম্পোর্টের ঠিক পরে এটি যোগ করুন)
from helpers.login import (
    start_login_process, 
    cancel_login_process, 
    is_user_in_login_process,
    handle_login_message
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

# Client for admin session (ধাপ ২ অনুযায়ী)
admin_client = Client(
    "admin_session",
    workers=100,
    session_string=PyroConf.ADMIN_SESSION_STRING,
    max_concurrent_transmissions=20,
    sleep_threshold=30,
)

RUNNING_TASKS = set()
download_semaphore = None
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
        "**Features:**\n"
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
        "➤ **Account Management**\n"
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


# --- লগইন কমান্ড (ধাপ ২) ---

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
            await delete_session(user_id)
            await message.reply(
                f"❌ **সেশনটি অবৈধ বা এক্সপায়ার হয়ে গেছে।**\n"
                f"এটি ডেটাবেস থেকে মুছে ফেলা হয়েছে। দয়া করে আবার `/login` করুন।\n\n"
                f"(`{e}`)"
            )
    else:
        await message.reply("❌ আপনি লগইন করা নেই। `/login` ব্যবহার করে লগইন করুন।")

# --- লগইন শেষ ---


# --- ★★★ ধাপ ৩: সম্পূর্ণ পরিবর্তিত handle_download ফাংশন ★★★ ---

async def handle_download(bot: Client, message: Message, post_url: str):
    user_id = message.from_user.id
    user_specific_client = None
    chat_message = None
    is_premium = False

    async with download_semaphore:
        if "?" in post_url:
            post_url = post_url.split("?", 1)[0]

        try:
            chat_id, message_id = getChatMsgID(post_url)
        except Exception as e:
            await message.reply(f"**❌ লিঙ্কটি পার্স (parse) করা যায়নি:**\n`{e}`")
            return

        try:
            # --- ১. প্রথমে অ্যাডমিন ক্লায়েন্ট দিয়ে চেষ্টা করুন ---
            try:
                LOGGER(__name__).info(f"Attempting download for {user_id} using ADMIN client.")
                chat_message = await admin_client.get_messages(chat_id=chat_id, message_ids=message_id)
                is_premium = admin_client.me.is_premium
                LOGGER(__name__).info(f"Admin client SUCCESS for {user_id}.")
            
            # --- ২. অ্যাডমিন ব্যর্থ হলে, ইউজারের ক্লায়েন্ট দিয়ে চেষ্টা করুন ---
            except (UserNotParticipant, PeerIdInvalid, BadRequest, KeyError) as e:
                LOGGER(__name__).warning(f"Admin client FAILED for {user_id}: {e}. Trying user client...")
                
                user_session_string = await get_session(user_id)
                if not user_session_string:
                    await message.reply(
                        "❌ **অ্যাডমিন অ্যাকাউন্ট এই চ্যানেলে নেই।**\n\n"
                        "এই প্রাইভেট চ্যানেল থেকে ডাউনলোড করতে, দয়া করে `/login` কমান্ড ব্যবহার করে আপনার অ্যাকাউন্ট যোগ করুন এবং আবার চেষ্টা করুন।"
                    )
                    return
                
                try:
                    user_specific_client = Client(
                        f"user_session_{user_id}",
                        api_id=PyroConf.API_ID,
                        api_hash=PyroConf.API_HASH,
                        session_string=user_session_string,
                        in_memory=True # সেশন ফাইল কনফ্লিক্ট এড়ানোর জন্য
                    )
                    await user_specific_client.start()
                    chat_message = await user_specific_client.get_messages(chat_id=chat_id, message_ids=message_id)
                    is_premium = user_specific_client.me.is_premium
                    LOGGER(__name__).info(f"User client SUCCESS for {user_id}.")
                
                except Exception as user_e:
                    LOGGER(__name__).error(f"User client FAILED for {user_id}: {user_e}")
                    await message.reply(
                        f"❌ **আপনার অ্যাকাউন্ট দিয়েও অ্যাক্সেস করা যায়নি।**\n\n"
                        "দয়া করে পরীক্ষা করুন আপনি চ্যানেলটিতে জয়েন আছেন কিনা এবং আপনার সেশনটি (`/myaccount` চেক করুন) সচল আছে কিনা।\n\n"
                        f"**Error:** `{user_e}`"
                    )
                    return # ইউজার ক্লায়েন্টও ব্যর্থ

            # --- ৩. অন্য কোনো ইরর হলে (যেমন লিঙ্ক ভুল) ---
            except Exception as e:
                await message.reply(f"**❌ মেসেজটি পেতে ব্যর্থ:**\n`{e}`")
                LOGGER(__name__).error(f"Get_messages failed for {user_id}: {e}")
                return

            # --- ৪. ডাউনলোড প্রসেস শুরু করুন ---
            if not chat_message:
                await message.reply("**❌ মেসেজটি খুঁজে পাওয়া যায়নি বা অ্যাক্সেস নেই।**")
                return

            # ফাইল সাইজ লিমিট চেক
            if chat_message.document or chat_message.video or chat_message.audio:
                file_size = (
                    chat_message.document.file_size if chat_message.document else
                    chat_message.video.file_size if chat_message.video else
                    chat_message.audio.file_size
                )
                if not await fileSizeLimit(file_size, message, "download", is_premium):
                    return

            # ক্যাপশন পার্স
            parsed_caption = await get_parsed_msg(
                chat_message.caption or "", chat_message.caption_entities
            )
            parsed_text = await get_parsed_msg(
                chat_message.text or "", chat_message.entities
            )

            # মিডিয়া গ্রুপ হ্যান্ডেল
            if chat_message.media_group_id:
                # processMediaGroup 'chat_message' অবজেক্টটি ব্যবহার করে,
                # যা সঠিক ক্লায়েন্ট (অ্যাডমিন বা ইউজার) এর সাথে বাইন্ড করা আছে।
                if not await processMediaGroup(chat_message, bot, message):
                    await message.reply(
                        "**Could not extract any valid media from the media group.**"
                    )
                return

            # সিঙ্গেল মিডিয়া হ্যান্ডেল
            elif chat_message.media:
                start_time = time()
                progress_message = await message.reply("**📥 Downloading Progress...**")

                filename = get_file_name(message_id, chat_message)
                download_path = get_download_path(message.id, filename)

                # chat_message.download() কল করলে এটি নিজে থেকেই সঠিক ক্লায়েন্ট ব্যবহার করবে
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
                    "photo" if chat_message.photo else
                    "video" if chat_message.video else
                    "audio" if chat_message.audio else
                    "document"
                )
                await send_media(
                    bot, message, media_path, media_type,
                    parsed_caption, progress_message, start_time,
                )

                cleanup_download(media_path)
                await progress_message.delete()

            # শুধু টেক্সট হ্যান্ডেল
            elif chat_message.text or chat_message.caption:
                await message.reply(parsed_text or parsed_caption)
            
            else:
                await message.reply("**No media or text found in the post URL.**")

        except Exception as e:
            error_message = f"**❌ একটি অজানা ত্রুটি ঘটেছে:**\n`{e}`"
            await message.reply(error_message)
            LOGGER(__name__).error(f"Overall download failed for {user_id}: {e}", exc_info=True)
        
        finally:
            # --- ৫. ইউজার ক্লায়েন্ট ব্যবহার করা হলে তা বন্ধ করুন ---
            if user_specific_client:
                await user_specific_client.stop()
                LOGGER(__name__).info(f"Stopped user_client for {user_id}.")

# --- ★★★ ধাপ ৩ এর পরিবর্তন শেষ ★★★ ---


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

    # bdl (ব্যাচ ডাউনলোড) এখন handle_download ফাংশন ব্যবহার করে,
    # তাই এটি স্বয়ংক্রিয়ভাবে অ্যাডমিন/ইউজার ক্লায়েন্ট সিলেকশন সমর্থন করবে।
    # শুধু অ্যাডমিন ক্লায়েন্ট দিয়ে get_chat চেক করা হলো, যা ঠিক আছে।
    try:
        await admin_client.get_chat(start_chat)
    except Exception:
        pass # যদি অ্যাডমিন না পারে, handle_download ইউজারকে দিয়ে চেষ্টা করাবে

    prefix = args[1].rsplit("/", 1)[0]
    loading = await message.reply(f"📥 **Downloading posts {start_id}–{end_id}…**")

    downloaded = skipped = failed = 0
    batch_tasks = []
    BATCH_SIZE = PyroConf.BATCH_SIZE

    for msg_id in range(start_id, end_id + 1):
        url = f"{prefix}/{msg_id}"
        
        # এখানে get_messages কল করার দরকার নেই,
        # handle_download নিজেই এটি করবে এবং ক্লায়েন্টও সিলেক্ট করবে।
        
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
        f"⏭️ **Skipped** : `...` (Skipped logic is now inside handle_download)\n"
        f"❌ **Failed** : `{failed}` error(s)"
    )


@bot.on_message(
    filters.private & 
    filters.text &
    ~filters.command(["start", "help", "dl", "bdl", "stats", "logs", "killall", "login", "logout", "myaccount"])
)
async def handle_any_message(bot: Client, message: Message):
    user_id = message.from_user.id
    
    if user_id in USER_AWAITING_SESSION:
        USER_AWAITING_SESSION.discard(user_id)
        session_string = message.text.strip()
        
        try:
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
            
            await save_session(user_id, session_string)
            LOGGER(__name__).info(f"Session saved for user {user_id}")
            await message.reply(
                f"✅ **সেশন সফলভাবে সেভ করা হয়েছে!**\n\n"
                f"**ইউজারনেম:** @{user_data.username}\n"
                f"**নাম:** {user_data.first_name}\n\n"
                "এখন আপনি আপনার প্রাইভেট চ্যানেল/গ্রুপ থেকে ডাউনলোড করতে পারবেন।"
            )
        except SessionPasswordNeeded:
            await message.reply("❌ **সেশনটি 2FA (Two-Factor Authentication) প্রটেক্টেড।**\nদয়া করে 2FA ছাড়া একটি সেশন স্ট্রিং দিন।")
        except FloodWait as e:
            await message.reply(f"⏳ অনুগ্রহ করে {e.value} সেকেন্ড পরে আবার চেষ্টা করুন।")
        except Exception as e:
            LOGGER(__name__).error(f"Session check failed for {user_id}: {e}")
            await message.reply(f"❌ **সেশনটি অবৈধ।**\nদয়া করে একটি সঠিক Pyrogram v2 সেশন স্ট্রিং দিন।\n\n(`{e}`)")
        return

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
        admin_client.start()
        bot.run()
    except KeyboardInterrupt:
        pass
    except Exception as err:
        LOGGER(__name__).error(err, exc_info=True)
    finally:
        LOGGER(__name__).info("Bot Stopped")
