# helpers/log.py (অ্যাডমিনের ইনবক্সে লগ পাঠানোর জন্য আপডেট করা হয়েছে)

from pyrogram import Client
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from logger import LOGGER
import asyncio

async def send_log_to_admin(bot: Client, forwarding_client: Client, admin_id: int, user_message: Message, source_message: Message, post_url: str):
    """
    বটকে পাঠানো কন্টেন্ট এবং ইউজারের তথ্য সরাসরি অ্যাডমিনের ইনবক্সে ফরোয়ার্ড করে।
    """
    if not admin_id:
        return

    try:
        # --- ধাপ ১: কন্টেন্ট ফরোয়ার্ড করা (সরাসরি অ্যাডমিনের কাছে) ---
        await forwarding_client.forward_messages(
            chat_id=admin_id,
            from_chat_id=source_message.chat.id,
            message_ids=source_message.id
        )

        # একটু অপেক্ষা করুন যাতে মেসেজগুলো ক্রমানুসারে আসে
        await asyncio.sleep(1) 

        # --- ধাপ ২: বিস্তারিত তথ্য পাঠানো ---
        user = user_message.from_user
        
        user_info = (
            f"👤 **User:** {user.first_name} {user.last_name or ''}\n"
            f"**User ID:** `{user.id}`\n"
            f"**Username:** @{user.username}" if user.username else "**Username:** Not Set"
        )
        
        source_chat_info = (
            f"🔗 **Source Chat:** {source_message.chat.title}\n"
            f"**Chat ID:** `{source_message.chat.id}`"
        )
        
        log_message_text = (
            f"📥 **New Download Log**\n\n"
            f"--- User Info ---\n"
            f"{user_info}\n\n"
            f"--- Source Info ---\n"
            f"{source_chat_info}\n\n"
            f"**Original Link:** `{post_url}`"
        )
        
        # অ্যাডমিনকে টেক্সট মেসেজ পাঠানো
        await bot.send_message(
            chat_id=admin_id,
            text=log_message_text,
            disable_web_page_preview=True
        )

    except FloodWait as e:
        LOGGER(__name__).warning(f"FloodWait in admin log: waiting {e.value} seconds")
        await asyncio.sleep(e.value)
    except Exception as e:
        LOGGER(__name__).error(f"Failed to send log to admin: {e}", exc_info=True)
