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
    
    # get attempts where user_id is NOT null
    atts = await db.quiz_attempts.find({"user_id": {"$ne": None}}).to_list(None)
    
    with open("atts_with_user.json", "w", encoding="utf-8") as f:
        json.dump([{
            "id": str(a["_id"]),
            "user_id": str(a.get("user_id")),
            "quiz_id": str(a.get("quiz_id")),
            "percentage": a.get("percentage")
        } for a in atts], f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    asyncio.run(main())
