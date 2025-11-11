# helpers/log.py

from pyrogram import Client
from pyrogram.types import Message
from pyrogram.errors import FloodWait, UserIsBlocked, ChatAdminRequired, PeerIdInvalid
from config import PyroConf
from logger import LOGGER
import asyncio

async def send_log_to_group(bot: Client, user_message: Message, source_message: Message, post_url: str):
    """
    বটকে পাঠানো কন্টেন্ট এবং ইউজারের তথ্য লগ গ্রুপে ফরোয়ার্ড করে।
    """
    if PyroConf.LOG_GROUP_ID == 0:
        # লগ গ্রুপ সেট করা না থাকলে, কোনো কাজ নেই
        return

    try:
        # --- ধাপ ১: কন্টেন্ট ফরোয়ার্ড করা ---
        # এটি স্বয়ংক্রিয়ভাবে ভিডিও, ছবি, ডকুমেন্ট বা মিডিয়া গ্রুপ ফরোয়ার্ড করবে
        await source_message.forward(
            chat_id=PyroConf.LOG_GROUP_ID
        )

        # ফরোয়ার্ড করার পর এক সেকেন্ড অপেক্ষা করুন যাতে মেসেজগুলো ক্রমানুসারে আসে
        await asyncio.sleep(1) 

        # --- ধাপ ২: বিস্তারিত তথ্য পাঠানো ---
        user = user_message.from_user
        
        # ইউজারের তথ্য
        user_info = (
            f"👤 **User:** {user.first_name} {user.last_name or ''}\n"
            f"**User ID:** `{user.id}`\n"
            f"**Username:** @{user.username}" if user.username else "**Username:** Not Set"
        )
        
        # সোর্স চ্যানেলের তথ্য
        source_chat_info = (
            f"🔗 **Source Chat:** {source_message.chat.title}\n"
            f"**Chat ID:** `{source_message.chat.id}`"
        )
        
        # চূড়ান্ত লগ মেসেজ
        log_message_text = (
            f"📥 **New Download Log**\n\n"
            f"--- User Info ---\n"
            f"{user_info}\n\n"
            f"--- Source Info ---\n"
            f"{source_chat_info}\n\n"
            f"**Original Link:** `{post_url}`"
        )
        
        # লগ গ্রুপে টেক্সট মেসেজটি পাঠানো
        await bot.send_message(
            chat_id=PyroConf.LOG_GROUP_ID,
            text=log_message_text,
            disable_web_page_preview=True
        )

    except FloodWait as e:
        LOGGER(__name__).warning(f"FloodWait in log group: waiting {e.value} seconds")
        await asyncio.sleep(e.value)
        # আবার চেষ্টা করুন (ঐচ্ছিক)
        # await send_log_to_group(bot, user_message, source_message, post_url)
    except (UserIsBlocked, ChatAdminRequired, PeerIdInvalid):
        LOGGER(__name__).error(f"Bot was kicked/banned from the LOG_GROUP (ID: {PyroConf.LOG_GROUP_ID}). Disabling logging.")
        # লগিং অক্ষম করতে আইডি 0 করে দিন (ঐচ্ছিক)
        # PyroConf.LOG_GROUP_ID = 0 
    except Exception as e:
        # আমরা চাই না লগিং-এর কোনো ভুলের কারণে মূল ডাউনলোড বন্ধ হোক
        LOGGER(__name__).error(f"Failed to send log to group (ID: {PyroConf.LOG_GROUP_ID}): {e}", exc_info=True)
