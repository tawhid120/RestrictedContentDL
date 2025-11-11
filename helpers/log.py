# helpers/log.py (সংশোধিত)

from pyrogram import Client
from pyrogram.types import Message
from pyrogram.errors import FloodWait, UserIsBlocked, ChatAdminRequired, PeerIdInvalid
from config import PyroConf
from logger import LOGGER
import asyncio

async def send_log_to_group(bot: Client, forwarding_client: Client, user_message: Message, source_message: Message, post_url: str):
    """
    বটকে পাঠানো কন্টেন্ট এবং ইউজারের তথ্য লগ গ্রুপে ফরোয়ার্ড করে।
    """
    if PyroConf.LOG_GROUP_ID == 0:
        return

    try:
        # --- ধাপ ১: কন্টেন্ট ফরোয়ার্ড করা ---
        # ফিক্স: forwarding_client (admin/user) এখন ফরোয়ার্ড করছে
        await forwarding_client.forward_messages(
            chat_id=PyroConf.LOG_GROUP_ID,
            from_chat_id=source_message.chat.id,
            message_ids=source_message.id
        )

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
        
        # ফিক্স: bot ক্লায়েন্ট এখন শুধু টেক্সট পাঠাচ্ছে
        await bot.send_message(
            chat_id=PyroConf.LOG_GROUP_ID,
            text=log_message_text,
            disable_web_page_preview=True
        )

    except FloodWait as e:
        LOGGER(__name__).warning(f"FloodWait in log group: waiting {e.value} seconds")
        await asyncio.sleep(e.value)
    except (UserIsBlocked, ChatAdminRequired, PeerIdInvalid):
        LOGGER(__name__).error(f"Bot was kicked/banned from the LOG_GROUP (ID: {PyroConf.LOG_GROUP_ID}). Disabling logging.")
    except Exception as e:
        LOGGER(__name__).error(f"Failed to send log to group (ID: {PyroConf.LOG_GROUP_ID}): {e}", exc_info=True)
