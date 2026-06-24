"""
Database Connection - Kết nối MongoDB với Motor (Async Driver)
==============================================================

Tại sao dùng Motor thay vì PyMongo trực tiếp?
- FastAPI là async framework → cần async database driver
- PyMongo là synchronous → sẽ block event loop, làm chậm toàn bộ app
- Motor wrap PyMongo thành async → non-blocking I/O
- Khi 1 request đang chờ MongoDB, server vẫn xử lý request khác

Pattern sử dụng: Singleton Connection
- Tạo 1 client duy nhất khi app startup
- Đóng client khi app shutdown
- Tất cả requests dùng chung connection pool
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import get_settings


class Database:
    """
    Singleton class quản lý kết nối MongoDB.
    
    Lifecycle:
    1. App startup → gọi connect() → tạo client + ping test
    2. App running → dùng get_db() để lấy database instance
    3. App shutdown → gọi disconnect() → đóng client
    """

    # Class-level variables: shared giữa tất cả instances
    client: AsyncIOMotorClient | None = None
    db: AsyncIOMotorDatabase | None = None

    @classmethod
    async def connect(cls) -> None:
        """
        Khởi tạo kết nối tới MongoDB.
        
        Được gọi 1 lần duy nhất trong FastAPI lifespan event.
        Motor tự quản lý connection pool (default: 100 connections).
        """
        settings = get_settings()

        # Tạo client - chưa thực sự kết nối, chỉ cấu hình
        cls.client = AsyncIOMotorClient(
            settings.MONGODB_URL,
            # Timeout kết nối: 5 giây (tránh treo app nếu MongoDB chết)
            serverSelectionTimeoutMS=5000,
        )

        # Lấy reference tới database cụ thể
        # MongoDB tự tạo database nếu chưa tồn tại (lazy creation)
        cls.db = cls.client[settings.MONGODB_DB_NAME]

        # Ping để verify kết nối thực sự hoạt động
        # Nếu MongoDB không chạy → raise exception → app không start
        try:
            await cls.client.admin.command("ping")
            print(f"[OK] Connected to MongoDB: {settings.MONGODB_DB_NAME}")
        except Exception as e:
            print(f"[ERROR] MongoDB connection failed: {e}")
            raise

    @classmethod
    async def disconnect(cls) -> None:
        """
        Đóng kết nối MongoDB.
        
        Quan trọng để giải phóng resources khi app shutdown.
        Nếu không đóng → connection leak → MongoDB từ chối kết nối mới.
        """
        if cls.client:
            cls.client.close()
            print("[CLOSED] MongoDB connection closed")

    @classmethod
    def get_db(cls) -> AsyncIOMotorDatabase:
        """
        Lấy database instance để thao tác với collections.
        
        Usage trong route handlers:
            db = Database.get_db()
            result = await db.quizzes.find_one({"_id": quiz_id})
        
        Raises:
            RuntimeError nếu chưa gọi connect()
        """
        if cls.db is None:
            raise RuntimeError(
                "Database not initialized. Call Database.connect() first."
            )
        return cls.db


def get_db() -> AsyncIOMotorDatabase:
    """
    Dependency injection function cho FastAPI.
    
    Dùng trong route handlers:
        @router.get("/quizzes")
        async def list_quizzes(db = Depends(get_db)):
            ...
    
    Tại sao dùng Depends() pattern?
    → Dễ mock trong testing (thay thế bằng test database)
    → Không cần import Database class ở mọi nơi
    → FastAPI tự gọi function này và inject kết quả
    """
    return Database.get_db()
