import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from motor.motor_asyncio import AsyncIOMotorClient
from app.config import get_settings
from bson import ObjectId
from app.dependencies import get_current_user

async def test_me():
    settings = get_settings()
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    
    # fake a user_id
    user = await db.users.find_one({})
    if not user:
        print("No users found in db.")
        return
        
    user_id = str(user["_id"])
    print(f"Testing with user_id: {user_id}")
    
    query = {"user_id": user_id}
    try:
        total = await db.quiz_attempts.count_documents(query)
        print(f"Total attempts: {total}")
        cursor = db.quiz_attempts.find(query).sort("completed_at", -1).skip(0).limit(10)
        attempts = await cursor.to_list(length=10)
        
        result = []
        for att in attempts:
            quiz = await db.quizzes.find_one({"_id": att["quiz_id"]})
            result.append({
                "id": str(att["_id"]),
                "quiz_id": str(att["quiz_id"]),
                "quiz_title": quiz["title"] if quiz else "Quiz đã xóa",
                "score": att["score"],
                "total": att["total"],
                "percentage": att.get("percentage", 0),
                "completed_at": att["completed_at"].isoformat()
            })
        print(result)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_me())
