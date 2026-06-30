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
    
    query = {"is_public": True, "is_approved": True}
    quizzes = await db.quizzes.find(query).to_list(None)
    
    with open("quizzes_test.json", "w", encoding="utf-8") as f:
        json.dump([{
            "id": str(q["_id"]),
            "title": q.get("title"),
            "subject": q.get("subject"),
            "chapter": q.get("chapter"),
            "school": q.get("school"),
            "exam_type": q.get("exam_type")
        } for q in quizzes], f, ensure_ascii=False)

if __name__ == "__main__":
    asyncio.run(main())
