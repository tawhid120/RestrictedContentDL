from motor.motor_asyncio import AsyncIOMotorClient
from config import PyroConf

client = AsyncIOMotorClient(PyroConf.DATABASE_URI)
db = client.restricted_content_dl
users_db = db.users

async def save_session(user_id: int, session_string: str):
    """ইউজারের সেশন স্ট্রিং সেভ বা আপডেট করে"""
    await users_db.update_one(
        {"user_id": user_id},
        {"$set": {"session_string": session_string}},
        upsert=True
    )

async def get_session(user_id: int) -> str | None:
    """ডেটাবেস থেকে ইউজারের সেশন স্ট্রিং খুঁজে বের করে"""
    user = await users_db.find_one({"user_id": user_id})
    return user.get("session_string") if user else None

async def delete_session(user_id: int):
    """ডেটাবেস থেকে ইউজারের সেশন ডিলিট করে"""
    await users_db.delete_one({"user_id": user_id})
