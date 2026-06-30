import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from motor.motor_asyncio import AsyncIOMotorClient
from app.config import get_settings

async def main():
    settings = get_settings()
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    
    users = await db.users.find({}).to_list(None)
    for u in users:
        print(f"User: {u['_id']}, Email: {u['email']}")
        
    if len(users) == 1:
        user_id = str(users[0]['_id'])
        print(f"Assigning all orphaned attempts to {user_id}")
        res = await db.quiz_attempts.update_many({"user_id": None}, {"$set": {"user_id": user_id}})
        print(f"Updated {res.modified_count} attempts.")
        
if __name__ == "__main__":
    asyncio.run(main())
