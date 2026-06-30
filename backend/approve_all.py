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
    
    # Approve tất cả quiz có trong DB để đảm bảo chúng hiển thị trên UI
    res = await db.quizzes.update_many({}, {"$set": {"is_approved": True}})
    print(f"Updated {res.modified_count} quizzes to is_approved=True")

if __name__ == "__main__":
    asyncio.run(main())
