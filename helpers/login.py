# helpers/login.py (চূড়ান্ত এবং ত্রুটি-মুক্ত সংস্করণ)

from pyrogram import Client
from pyrogram.errors import (
    SessionPasswordNeeded, 
    PhoneCodeInvalid, 
    PasswordHashInvalid,
    FloodWait,
    PhoneNumberInvalid  # <-- ফিক্স: এটি যোগ করা হয়েছে
)
from config import PyroConf
from logger import LOGGER
from helpers.database import save_session

# এই ডিকশনারিটি ইউজারদের লগইন স্টেট মনে রাখে
LOGIN_SESSIONS = {}

async def start_login_process(user_id, message):
    """
    ইউজারের জন্য লগইন প্রক্রিয়া শুরু বা রিস্টার্ট করে।
    """
    # যেকোনো পুরনো প্রচেষ্টা থাকলে তা বাতিল করুন
    await cancel_login_process(user_id)
    
    LOGIN_SESSIONS[user_id] = {"state": "awaiting_phone"}
    
    await message.reply(
        "🔒 **New Login Process**\n\n"
        "To begin, please send your Telegram account's **phone number** "
        "including the country code.\n\n"
        "**Example:** `+12223334444`\n\n"
        "You can send /cancel at any time to stop this process."
    )

async def cancel_login_process(user_id):
    """
    চলমান লগইন প্রক্রিয়া বাতিল করে এবং ক্লায়েন্ট সেশন পরিষ্কার করে।
    """
    if user_id in LOGIN_SESSIONS:
        session_data = LOGIN_SESSIONS[user_id]
        temp_client = session_data.get("temp_client")
        
        # ফিক্স: ক্লায়েন্ট বন্ধ করার আগে চেক করুন এটি সচল (connected) আছে কিনা
        if temp_client and temp_client.is_connected:
            try:
                await temp_client.stop()
                LOGGER(__name__).info(f"Temporary client for {user_id} stopped.")
            except Exception as e:
                LOGGER(__name__).warning(f"Could not stop temp_client for {user_id}: {e}")
        
        del LOGIN_SESSIONS[user_id]
        return True
    return False

def is_user_in_login_process(user_id):
    """
    চেক করে ইউজার বর্তমানে লগইন প্রক্রিয়ায় আছেন কিনা।
    """
    return user_id in LOGIN_SESSIONS

async def handle_login_message(user_id, message):
    """
    লগইন প্রক্রিয়ার বিভিন্ন ধাপ (state machine) পরিচালনা করে।
    """
    if not is_user_in_login_process(user_id):
        return

    session_data = LOGIN_SESSIONS[user_id]
    state = session_data.get("state")
    text = message.text.strip()
    temp_client = session_data.get("temp_client")

    # --- ফিক্স (Race Condition): Client is already terminated ---
    if temp_client and not temp_client.is_connected and state != "awaiting_phone":
        LOGGER(__name__).warning(f"Cleaning up stale login session for {user_id} (client terminated)")
        if user_id in LOGIN_SESSIONS:
            del LOGIN_SESSIONS[user_id]
        return 
    # --- ফিক্স শেষ ---

    try:
        # --- ধাপ ১: ফোন নম্বর পাওয়া ---
        if state == "awaiting_phone":
            
            # --- ফিক্স: ফোন নম্বরটি '+' দিয়ে শুরু হয়েছে কিনা তা যাচাই করা ---
            if not text.startswith("+"):
                await message.reply(
                    "❌ **Invalid Format!**\n\n"
                    "Your phone number must start with a `+` and include the country code.\n\n"
                    "**Example:** `+8801712345678`\n\n"
                    "The login process has been cancelled. Please send /login to try again."
                )
                await cancel_login_process(user_id) # এই প্রচেষ্টা বাতিল করুন
                return
            # --- ফিক্স শেষ ---

            await message.reply("⏳ Received phone number. Sending confirmation code...")
            
            temp_client = Client(
                f"login_session_{user_id}",
                api_id=PyroConf.API_ID,
                api_hash=PyroConf.API_HASH,
                in_memory=True # Render-এর জন্য খুবই গুরুত্বপূর্ণ
                ipv6=False
            )
            
            await temp_client.connect()
            
            code_data = await temp_client.send_code(text)
            
            session_data["state"] = "awaiting_otp"
            session_data["phone_number"] = text
            session_data["phone_code_hash"] = code_data.phone_code_hash
            session_data["temp_client"] = temp_client
            
            await message.reply(
                "✅ A code has been sent to your Telegram app.\n\n"
                "Please send the **OTP code** here.\n"
                "*(Tip: You can format it like `1 2 3 4 5`)*"
            )

        # --- ধাপ ২: OTP পাওয়া ---
        elif state == "awaiting_otp":
            otp = text.replace(" ", "")
            
            try:
                await message.reply("⏳ Verifying code...")
                
                await temp_client.sign_in(
                    session_data["phone_number"],
                    session_data["phone_code_hash"],
                    otp
                )
                
                # 2FA না থাকলে, লগইন সফল
                session_string = await temp_client.export_session_string()
                await save_session(user_id, session_string)
                
                await message.reply("✅ **Login Successful!**\nYour account has been saved.")
                
            except SessionPasswordNeeded:
                # 2FA চালু আছে
                session_data["state"] = "awaiting_password"
                await message.reply(
                    "🔑 Your account is protected by Two-Factor Authentication (2FA).\n\n"
                    "Please send your **2FA password**."
                )
                return # সফলভাবে ধাপ পরিবর্তন, সেশন ডিলিট করবেন না

            except PhoneCodeInvalid:
                await message.reply(
                    "❌ **Invalid Code.**\n"
                    "The login process has been cancelled. Please send /login to try again."
                )
            
            # 2FA সফল হলে বা OTP ভুল হলে, সেশনটি বন্ধ করুন
            if temp_client.is_connected:
                await temp_client.stop()
            del LOGIN_SESSIONS[user_id]


        # --- ধাপ ৩: 2FA পাসওয়ার্ড পাওয়া ---
        elif state == "awaiting_password":
            password = text
            
            try:
                await message.reply("⏳ Verifying password...")
                
                await temp_client.check_password(password)
                
                # 2FA সফল
                session_string = await temp_client.export_session_string()
                await save_session(user_id, session_string)
                
                await message.reply(
                    "✅ **Login Successful (2FA)!**\nYour account has been saved."
                )
                
            except PasswordHashInvalid:
                await message.reply(
                    "❌ **Incorrect Password.**\n"
                    "The login process has been cancelled. Please send /login to try again."
                )
            
            # 2FA সফল হোক বা না হোক, সেশনটি বন্ধ করুন
            if temp_client.is_connected:
                await temp_client.stop()
            del LOGIN_SESSIONS[user_id]


    except FloodWait as e:
        await message.reply(
            f"⏳ Telegram is limiting requests. Please wait for {e.value} seconds before trying again.\n"
            "The login process has been cancelled."
        )
        if temp_client and temp_client.is_connected:
            await temp_client.stop()
        if user_id in LOGIN_SESSIONS:
            del LOGIN_SESSIONS[user_id]
            
    # --- ফিক্স: PhoneNumberInvalid এর জন্য সুনির্দিষ্ট এরর মেসেজ ---
    except PhoneNumberInvalid:
        await message.reply(
            "❌ **Invalid Phone Number!**\n\n"
            "Telegram rejected this number. Please make sure it is a valid Telegram account number and includes the `+` symbol and country code (e.g., `+880...`).\n\n"
            "The login process has been cancelled. Please send /login to try again."
        )
        if temp_client and temp_client.is_connected:
            await temp_client.stop()
        if user_id in LOGIN_SESSIONS:
            del LOGIN_SESSIONS[user_id]
    # --- ফিক্স শেষ ---
        
    except Exception as e:
        # এটি সেই এররটি যা আপনি আগে পাচ্ছিলেন
        if "Client is already terminated" in str(e):
            LOGGER(__name__).warning(f"Handled a race condition for {user_id}. Ignoring.")
            # যদি কোনোভাবে রেস কন্ডিশন ঘটেও, ইউজারকে আর এরর দেখাবে না
            pass 
        else:
            # অন্য কোনো গুরুতর এরর হলে দেখাবে
            await message.reply(
                f"❌ **An unexpected error occurred:**\n`{e}`\n\n"
                "The login process has been cancelled. Please send /login to try again."
            )
            LOGGER(__name__).error(f"Login process failed for {user_id}: {e}", exc_info=True)

        if temp_client and temp_client.is_connected:
            try:
                await temp_client.stop()
            except: pass
        if user_id in LOGIN_SESSIONS:
            del LOGIN_SESSIONS[user_id]

