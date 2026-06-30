import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from motor.motor_asyncio import AsyncIOMotorClient
from app.config import get_settings
from bson import ObjectId

async def main():
    settings = get_settings()
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    
    # Just grab ANY attempt and try to format it like get_my_attempts does
    atts = await db.quiz_attempts.find({}).to_list(None)
    
    result = []
    for att in atts:
        quiz = await db.quizzes.find_one({"_id": att["quiz_id"]})
        
        try:
            r = {
                "id": str(att["_id"]),
                "quiz_id": str(att["quiz_id"]),
                "quiz_title": quiz["title"] if quiz else "Quiz đã xóa",
                "score": att["score"],
                "total": att["total"],
                "percentage": att.get("percentage", 0),
                "completed_at": att["completed_at"].isoformat() if "completed_at" in att and hasattr(att["completed_at"], "isoformat") else str(att.get("completed_at", ""))
            }
            result.append(r)
        except Exception as e:
            print("ERROR formatting attempt:", att["_id"], type(e), e)

    print("Successfully formatted:", len(result))

if __name__ == "__main__":
    asyncio.run(main())
