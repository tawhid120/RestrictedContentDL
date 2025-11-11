# helpers/login.py (সংশোধিত)

from pyrogram import Client
from pyrogram.errors import (
    SessionPasswordNeeded, 
    PhoneCodeInvalid, 
    PasswordHashInvalid,
    FloodWait
)
from config import PyroConf
from logger import LOGGER
from helpers.database import save_session

LOGIN_SESSIONS = {}

async def start_login_process(user_id, message):
    """
    Starts or restarts the login process for a user.
    """
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
    Cancels any active login process for a user and cleans up.
    """
    if user_id in LOGIN_SESSIONS:
        session_data = LOGIN_SESSIONS[user_id]
        temp_client = session_data.get("temp_client")
        
        # ফিক্স: স্টপ করার আগে ক্লায়েন্ট সচল (connected) কিনা তা চেক করুন
        if temp_client and temp_client.is_connected:
            try:
                await temp_client.stop()
            except Exception as e:
                LOGGER(__name__).warning(f"Could not stop temp_client for {user_id}: {e}")
        
        del LOGIN_SESSIONS[user_id]
        return True
    return False

def is_user_in_login_process(user_id):
    """
    Checks if a user is currently in the middle of a login process.
    """
    return user_id in LOGIN_SESSIONS

async def handle_login_message(user_id, message):
    """
    Handles the multi-step login conversation (state machine).
    """
    if not is_user_in_login_process(user_id):
        return

    session_data = LOGIN_SESSIONS[user_id]
    state = session_data.get("state")
    text = message.text.strip()
    temp_client = session_data.get("temp_client")

    # --- নতুন ফিক্স: Race Condition এড়ানোর জন্য ---
    # যদি ক্লায়েন্টটি কোনো কারণে বন্ধ হয়ে যায়, তবে সেশনটি পরিষ্কার করুন
    if temp_client and not temp_client.is_connected:
        LOGGER(__name__).warning(f"Cleaning up stale login session for {user_id} (client terminated)")
        del LOGIN_SESSIONS[user_id]
        return  # এই মেসেজটি ইগনোর করুন

    try:
        # --- State 1: Awaiting Phone Number ---
        if state == "awaiting_phone":
            await message.reply("⏳ Received phone number. Sending confirmation code...")
            
            temp_client = Client(
                f"login_session_{user_id}",
                api_id=PyroConf.API_ID,
                api_hash=PyroConf.API_HASH,
                in_memory=True
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

        # --- State 2: Awaiting OTP ---
        elif state == "awaiting_otp":
            otp = text.replace(" ", "")
            
            try:
                await message.reply("⏳ Verifying code...")
                
                await temp_client.sign_in(
                    session_data["phone_number"],
                    session_data["phone_code_hash"],
                    otp
                )
                
                session_string = await temp_client.export_session_string()
                await save_session(user_id, session_string)
                
                # ফিক্স: স্টপ করার আগে চেক
                if temp_client.is_connected:
                    await temp_client.stop()
                
                await message.reply("✅ **Login Successful!**\nYour account has been saved.")
                del LOGIN_SESSIONS[user_id]

            except SessionPasswordNeeded:
                session_data["state"] = "awaiting_password"
                await message.reply(
                    "🔑 Your account is protected by Two-Factor Authentication (2FA).\n\n"
                    "Please send your **2FA password**."
                )
            
            except PhoneCodeInvalid:
                await message.reply(
                    "❌ **Invalid Code.**\n"
                    "The login process has been cancelled. Please send /login to try again."
                )
                if temp_client.is_connected:
                    await temp_client.stop()
                del LOGIN_SESSIONS[user_id]

        # --- State 3: Awaiting 2FA Password ---
        elif state == "awaiting_password":
            password = text
            
            try:
                await message.reply("⏳ Verifying password...")
                
                await temp_client.check_password(password)
                
                session_string = await temp_client.export_session_string()
                await save_session(user_id, session_string)
                
                if temp_client.is_connected:
                    await temp_client.stop()
                
                await message.reply(
                    "✅ **Login Successful (2FA)!**\nYour account has been saved."
                )
                del LOGIN_SESSIONS[user_id]
            
            except PasswordHashInvalid:
                await message.reply(
                    "❌ **Incorrect Password.**\n"
                    "The login process has been cancelled. Please send /login to try again."
                )
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
        
    except Exception as e:
        # এটি সেই ব্লক যা আপনি দেখছেন
        await message.reply(
            f"❌ **An unexpected error occurred:**\n`{e}`\n\n"
            "The login process has been cancelled. Please send /login to try again."
        )
        if temp_client and temp_client.is_connected:
            try:
                await temp_client.stop()
            except: pass # এখানে এরর ইগনোর করুন
        if user_id in LOGIN_SESSIONS:
            del LOGIN_SESSIONS[user_id]
        LOGGER(__name__).error(f"Login process failed for {user_id}: {e}", exc_info=True)
