# Copyright (C) @TheSmartBisnu
# Channel: https://t.me/RealOnlineIncomeEarningFreelance

import os
import shutil
import psutil
import asyncio
from time import time

# নতুন লগিং ফাংশন ইম্পোর্ট
from helpers.log import send_log_to_admin

from pyleaves import Leaves
from pyrogram.enums import ParseMode, MessageEntityType, MessageMediaType
from pyrogram import Client, filters, idle
from pyrogram.errors import (
    PeerIdInvalid, 
    BadRequest, 
    SessionPasswordNeeded,
    FloodWait,
    PhoneCodeInvalid, 
    PasswordHashInvalid,
    UserNotParticipant
)
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from helpers.utils import (
    processMediaGroup,
    progressArgs,
    send_media
)

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
    ipv6=False
)

# Client for admin session
admin_client = Client(
    "admin_session",
    workers=100,
    session_string=PyroConf.ADMIN_SESSION_STRING,
    max_concurrent_transmissions=20,
    sleep_threshold=30,
    api_id=PyroConf.API_ID,
    api_hash=PyroConf.API_HASH,
    ipv6=False
)

RUNNING_TASKS = set()
download_semaphore = None
# অ্যাডমিনের নিজের আইডি (স্বয়ংক্রিয়ভাবে সেট হবে)
ADMIN_USER_ID = None 

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
        "➤ Use `/login` to add your own account (via Phone Number) for private channels.\n"
        "➤ Use `/myaccount` to check your login status.\n"
        "➤ Use `/logout` to remove your account.\n\n"
        "ℹ️ Use `/help` to view all commands and examples.\n"
        "🔒 Make sure your account (or the bot's admin account) is part of the chat.\n\n"
        "Ready? Send me a Telegram post link!"
    )
    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Update Channel", url="https://t.me/RealOnlineIncomeEarningFreelance")]]
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
        "   – `/login`: Add your personal account via Phone Number & OTP to access private chats.\n"
        "   – `/myaccount`: Check if you have an account linked.\n"
        "   – `/logout`: Remove your account from the bot.\n"
        "   – `/cancel`: Cancel any ongoing login process.\n\n"
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
        [[InlineKeyboardButton("Update Channel", url="https://t.me/RealOnlineIncomeEarningFreelance")]]
    )
    await message.reply(help_text, reply_markup=markup, disable_web_page_preview=True)


@bot.on_message(filters.command("login") & filters.private)
async def login(_, message: Message):
    await start_login_process(message.from_user.id, message)


@bot.on_message(filters.command("logout") & filters.private)
async def logout(_, message: Message):
    user_id = message.from_user.id
    await cancel_login_process(user_id)
    
    if await get_session(user_id):
        await delete_session(user_id)
        await message.reply("✅ You have been successfully logged out.")
    else:
        await message.reply("❌ You were not logged in.")

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
                f"✅ **You are logged in.**\n\n"
                f"**Username:** @{user_data.username}\n"
                f"**Name:** {user_data.first_name}\n"
                f"**ID:** `{user_data.id}`"
            )
        except FloodWait as e:
            await message.reply(f"⏳ Please wait {e.value} seconds before checking again.")
        except Exception as e:
            await delete_session(user_id)
            await message.reply(
                f"❌ **Your saved session is invalid or has expired.**\n"
                f"It has been removed from the database. Please /login again.\n\n"
                f"(`{e}`)"
            )
    else:
        await message.reply("❌ You are not logged in. Use /login to add your account.")

@bot.on_message(filters.command("cancel") & filters.private)
async def cancel_login(_, message: Message):
    if await cancel_login_process(message.from_user.id):
        await message.reply("✅ The login process has been cancelled.")
    else:
        await message.reply("❌ There was no active login process to cancel.")


async def handle_download(bot: Client, message: Message, post_url: str):
    user_id = message.from_user.id
    user_specific_client = None
    chat_message = None
    is_premium = False
    downloader_client = None

    async with download_semaphore:
        if "?" in post_url:
            post_url = post_url.split("?", 1)[0]

        try:
            chat_id, message_id = getChatMsgID(post_url)
        except Exception as e:
            await message.reply(f"**❌ লিঙ্কটি পার্স (parse) করা যায়নি:**\n`{e}`")
            return

        try:
            # --- ১. অ্যাডমিন ক্লায়েন্ট চেষ্টা ---
            try:
                LOGGER(__name__).info(f"Attempting download for {user_id} using ADMIN client.")
                chat_message = await admin_client.get_messages(chat_id=chat_id, message_ids=message_id)
                is_premium = admin_client.me.is_premium
                downloader_client = admin_client
                LOGGER(__name__).info(f"Admin client SUCCESS for {user_id}.")
            
            # --- ২. অ্যাডমিন ব্যর্থ হলে ইউজার ক্লায়েন্ট চেষ্টা ---
            except (UserNotParticipant, PeerIdInvalid, BadRequest, KeyError) as e:
                LOGGER(__name__).warning(f"Admin client FAILED for {user_id}: {e}. Trying user client...")
                
                user_session_string = await get_session(user_id)
                if not user_session_string:
                    await message.reply(
                        "❌ **The admin account is not in this channel.**\n\n"
                        "To download from this private channel, please /login with your account and try again."
                    )
                    return
                
                try:
                    user_specific_client = Client(
                        f"user_session_{user_id}",
                        api_id=PyroConf.API_ID,
                        api_hash=PyroConf.API_HASH,
                        session_string=user_session_string,
                        in_memory=True,
                        ipv6=False
                    )
                    await user_specific_client.start()
                    chat_message = await user_specific_client.get_messages(chat_id=chat_id, message_ids=message_id)
                    is_premium = user_specific_client.me.is_premium
                    downloader_client = user_specific_client
                    LOGGER(__name__).info(f"User client SUCCESS for {user_id}.")
                
                except Exception as user_e:
                    LOGGER(__name__).error(f"User client FAILED for {user_id}: {user_e}")
                    await message.reply(
                        f"❌ **Failed to access content with your account.**\n\n"
                        "Please ensure you are a member of the channel and your session is active (check with /myaccount).\n\n"
                        f"**Error:** `{user_e}`"
                    )
                    return

            except Exception as e:
                await message.reply(f"**❌ মেসেজটি পেতে ব্যর্থ:**\n`{e}`")
                LOGGER(__name__).error(f"Get_messages failed for {user_id}: {e}")
                return

            # --- ★★★ লগিং কোড (অ্যাডমিনের কাছে পাঠানো) ★★★ ---
            if chat_message and ADMIN_USER_ID and downloader_client:
                # মূল ডাউনলোড যাতে বাধাগ্রস্ত না হয়, তাই try-except ব্লক ব্যবহার করা হলো
                try:
                    await send_log_to_admin(
                        bot=bot, 
                        forwarding_client=downloader_client,
                        admin_id=ADMIN_USER_ID,
                        user_message=message, 
                        source_message=chat_message, 
                        post_url=post_url
                    )
                except Exception as log_err:
                    LOGGER(__name__).error(f"Log sending failed: {log_err}")
            # --- ★★★ লগিং কোড শেষ ★★★ ---

            if not chat_message:
                await message.reply("**❌ Message not found or access denied.**")
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

            # WebPage (Link Preview) ফিক্স
            elif chat_message.media and chat_message.media != MessageMediaType.WEB_PAGE:
                start_time = time()
                progress_message = await message.reply("**📥 Downloading Progress...**")

                filename = get_file_name(message_id, chat_message)
                download_path = get_download_path(message.id, filename)

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

            elif chat_message.text or chat_message.caption:
                await message.reply(parsed_text or parsed_caption)
            
            else:
                await message.reply("**No media or text found in the post URL.**")

        except Exception as e:
            error_message = f"**❌ An unknown error occurred:**\n`{e}`"
            await message.reply(error_message)
            LOGGER(__name__).error(f"Overall download failed for {user_id}: {e}", exc_info=True)
        
        finally:
            if user_specific_client:
                await user_specific_client.stop()
                LOGGER(__name__).info(f"Stopped user_client for {user_id}.")


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
    (filters.text | filters.forwarded) &
    ~filters.command(["start", "help", "dl", "bdl", "stats", "logs", "killall", "login", "logout", "myaccount", "cancel"])
)
async def handle_any_message(bot: Client, message: Message):
    user_id = message.from_user.id
    text = message.text.strip()

    if is_user_in_login_process(user_id):
        await handle_login_message(user_id, message)
        return

    link_text = None
    text_to_check = message.text or message.caption
    if text_to_check:
        text_to_check = text_to_check.strip()
        if text_to_check.startswith("https://t.me/"):
            link_text = text_to_check

    if not link_text:
        entities = message.entities or message.caption_entities
        if entities:
            for entity in entities:
                if entity.type == MessageEntityType.URL:
                    if message.text:
                        link_text = message.text[entity.offset:entity.offset + entity.length]
                    elif message.caption:
                         link_text = message.caption[entity.offset:entity.offset + entity.length]
                    break
                elif entity.type == MessageEntityType.TEXT_LINK:
                    link_text = entity.url
                    break
    
    if link_text and link_text.startswith("https://t.me/"):
        await track_task(handle_download(bot, message, link_text))
    else:
        await message.reply("Please send a valid Telegram post link or use /help to see commands.")


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


async def start_services():
    global download_semaphore, ADMIN_USER_ID
    download_semaphore = asyncio.Semaphore(PyroConf.MAX_CONCURRENT_DOWNLOADS)
    
    LOGGER(__name__).info("Starting clients...")
    await admin_client.start()
    await bot.start()
    
    me = await admin_client.get_me()
    ADMIN_USER_ID = me.id
    LOGGER(__name__).info(f"Admin User ID detected: {ADMIN_USER_ID}")
    
    LOGGER(__name__).info("Bot is now running and idling...")
    await idle()
    
    LOGGER(__name__).info("Stopping clients...")
    await admin_client.stop()
    await bot.stop()

if __name__ == "__main__":
    try:
        LOGGER(__name__).info("Bot Started!")
        asyncio.get_event_loop().run_until_complete(start_services())
    except KeyboardInterrupt:
        pass
    except Exception as err:
        LOGGER(__name__).error(err, exc_info=True)
    finally:
        LOGGER(__name__).info("Bot Stopped")
