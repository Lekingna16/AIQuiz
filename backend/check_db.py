import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from motor.motor_asyncio import AsyncIOMotorClient
from app.config import get_settings
from datetime import datetime

async def main():
    settings = get_settings()
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    
    # 1. Check distinct
    query = {"is_public": True, "is_approved": True}
    print("Filter Query:", query)
    subjects = await db.quizzes.distinct("subject", query)
    print("Subjects:", subjects)
    
    # Check all public/approved quizzes
    quizzes = await db.quizzes.find(query).to_list(None)
    print(f"Total public & approved quizzes: {len(quizzes)}")
    
    # 2. Check quiz attempts
    atts = await db.quiz_attempts.find({}).to_list(None)
    print(f"Total attempts in DB: {len(atts)}")
    for a in atts:
        print("Attempt ID:", a.get("_id"))
        print("Completed at type:", type(a.get("completed_at")))
        print("Has score:", "score" in a)
        break

if __name__ == "__main__":
    asyncio.run(main())
