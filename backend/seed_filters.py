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
    
    quizzes = await db.quizzes.find({}).to_list(10)
    for i, q in enumerate(quizzes):
        updates = {}
        if i % 2 == 0:
            updates["exam_type"] = "Cuối kì"
            updates["chapter"] = "Chương 1"
        else:
            updates["exam_type"] = "Giữa kì"
            updates["chapter"] = "Chương 2"
            
        await db.quizzes.update_one({"_id": q["_id"]}, {"$set": updates})
        
    print(f"Updated {len(quizzes)} quizzes with mock exam types and chapters for testing")

if __name__ == "__main__":
    asyncio.run(main())
