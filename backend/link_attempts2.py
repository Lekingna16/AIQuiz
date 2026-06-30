import asyncio
import os
import sys
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from motor.motor_asyncio import AsyncIOMotorClient
from app.config import get_settings

async def main():
    settings = get_settings()
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    
    users = await db.users.find({}).to_list(None)
    user_list = [{"id": str(u["_id"]), "email": u["email"]} for u in users]
    
    with open("users_test.json", "w", encoding="utf-8") as f:
        json.dump(user_list, f, ensure_ascii=False)
        
    if len(users) == 1:
        user_id = str(users[0]['_id'])
        res = await db.quiz_attempts.update_many({"user_id": None}, {"$set": {"user_id": user_id}})
        with open("update_res.json", "w", encoding="utf-8") as f:
            json.dump({"modified": res.modified_count}, f)
        
if __name__ == "__main__":
    asyncio.run(main())
