import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    dbnames = await client.list_database_names()
    print("Databases:", dbnames)
    
    for dbn in dbnames:
        db = client[dbn]
        users_count = await db.users.count_documents({})
        if users_count > 0:
            print(f"DB {dbn} has {users_count} users")
            users = await db.users.find({}).to_list(10)
            print(users)
            
if __name__ == "__main__":
    asyncio.run(main())
