import asyncio
import os
import sys
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from motor.motor_asyncio import AsyncIOMotorClient
from app.config import get_settings
from datetime import datetime

async def main():
    settings = get_settings()
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    
    query = {"is_public": True, "is_approved": True}
    subjects = await db.quizzes.distinct("subject", query)
    chapters = await db.quizzes.distinct("chapter", query)
    schools = await db.quizzes.distinct("school", query)
    
    with open("db_test.json", "w", encoding="utf-8") as f:
        json.dump({
            "subjects": subjects,
            "chapters": chapters,
            "schools": schools
        }, f, ensure_ascii=False)
        
    atts = await db.quiz_attempts.find({}).to_list(None)
    with open("atts_test.json", "w", encoding="utf-8") as f:
        json.dump([{
            "id": str(a["_id"]),
            "type_completed_at": str(type(a.get("completed_at"))),
            "val_completed_at": str(a.get("completed_at")),
            "quiz_id": str(a.get("quiz_id")),
            "user_id": str(a.get("user_id"))
        } for a in atts], f, ensure_ascii=False)

if __name__ == "__main__":
    asyncio.run(main())
