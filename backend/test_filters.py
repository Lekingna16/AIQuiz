import asyncio
import traceback
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import get_settings

async def main():
    settings = get_settings()
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    try:
        query = {"is_public": True, "is_approved": True}
        
        subjects = await db.quizzes.distinct("subject", query)
        chapters = await db.quizzes.distinct("chapter", query)
        schools = await db.quizzes.distinct("school", query)
        
        subjects = [s for s in subjects if s]
        chapters = [c for c in chapters if c]
        schools = [s for s in schools if s]
        
        print({
            "subjects": sorted(subjects),
            "chapters": sorted(chapters),
            "schools": sorted(schools),
        })
    except Exception as e:
        print("ERROR:", traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(main())
