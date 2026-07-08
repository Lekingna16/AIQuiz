import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import get_settings

async def main():
    settings = get_settings()
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db_name = settings.MONGODB_DB_NAME
    
    print(f"Bắt đầu xóa toàn bộ dữ liệu trong database: {db_name}")
    # Lấy danh sách các collection
    collections = await client[db_name].list_collection_names()
    
    for coll in collections:
        print(f"Đang xóa collection: {coll}...")
        await client[db_name].drop_collection(coll)
        
    print("Đã xóa hoàn toàn database!")

if __name__ == "__main__":
    asyncio.run(main())
