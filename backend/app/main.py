"""
FastAPI Main Application - Entry Point
========================================

Đây là file "trái tim" của backend:
1. Khởi tạo FastAPI app
2. Cấu hình CORS (cho phép Frontend gọi API)
3. Quản lý lifecycle (startup/shutdown events)
4. Mount tất cả routers

Để chạy server:
    cd backend
    uvicorn app.main:app --reload --port 8000

--reload: tự restart khi code thay đổi (chỉ dùng trong dev)
--port 8000: chạy trên port 8000

Sau khi chạy, truy cập:
- API: http://localhost:8000
- Swagger Docs: http://localhost:8000/docs    (interactive)
- ReDoc: http://localhost:8000/redoc           (read-only)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import Database
from app.routers import documents, quizzes, auth, comments


# ============================================
# LIFESPAN - Quản lý Startup/Shutdown
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Async context manager quản lý vòng đời của app.
    
    Tại sao dùng lifespan thay vì @app.on_event("startup")?
    → @app.on_event() đã deprecated từ FastAPI 0.103
    → lifespan là cách mới, clean hơn, dùng async context manager
    
    Flow:
    1. Code TRƯỚC yield → chạy khi app STARTUP
    2. yield → app đang chạy, phục vụ requests
    3. Code SAU yield → chạy khi app SHUTDOWN
    """
    # --- STARTUP ---
    settings = get_settings()
    print(f"[START] Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f"[CONFIG] Debug mode: {settings.DEBUG}")

    # Kết nối MongoDB (non-blocking: warn if unavailable)
    try:
        await Database.connect()
    except Exception as e:
        print(f"[WARN] MongoDB not available: {e}")
        print("[WARN] Running without database - some features won't work")

    yield  # ← App đang chạy ở đây

    # --- SHUTDOWN ---
    await Database.disconnect()
    print("[SHUTDOWN] Application shutdown complete")


# ============================================
# APP INITIALIZATION
# ============================================

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
    🧠 **AIQuiz** - AI-Powered MCQ Generator
    
    Upload tài liệu → AI tự động sinh câu hỏi trắc nghiệm.
    
    **Features:**
    - 📄 Hỗ trợ PDF, DOCX, TXT
    - 🤖 Powered by Google Gemini AI
    - ✅ Chấm điểm tự động
    - 📊 Lịch sử làm bài
    """,
    lifespan=lifespan,
    # Swagger UI config
    docs_url="/docs",
    redoc_url="/redoc",
)


# ============================================
# CORS MIDDLEWARE
# ============================================
"""
CORS (Cross-Origin Resource Sharing):
- Browser mặc định CHẶN request từ domain khác (security)
- Frontend (localhost:5173) gọi Backend (localhost:8000) = khác origin
- Phải cấu hình CORS để cho phép

allow_origins: danh sách origin được phép
allow_methods: HTTP methods được phép (GET, POST, PUT, DELETE)
allow_headers: Headers được phép gửi
allow_credentials: cho phép gửi cookies (cần cho auth)
"""
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip().rstrip("/") for origin in settings.FRONTEND_URL.split(",") if origin.strip()
    ] + [
        "http://localhost:5173",  # Backup nếu env chưa set
        "http://127.0.0.1:5173",  # Handle cases where user visits 127.0.0.1
    ],
    allow_credentials=True,
    allow_methods=["*"],  # Cho phép tất cả methods
    allow_headers=["*"],  # Cho phép tất cả headers
)


# ============================================
# INCLUDE ROUTERS
# ============================================
"""
Mount routers vào app chính.
Mỗi router đã có prefix riêng:
- documents: /api/documents/*
- quizzes: /api/quizzes/*
"""
app.include_router(documents.router)
app.include_router(quizzes.router)
app.include_router(auth.router)
app.include_router(comments.router)


# ============================================
# ERROR HANDLING MIDDLEWARE
# ============================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler for unexpected errors.
    Returns a standardized 500 JSON response instead of a raw traceback.
    """
    # In a real app, you would log the traceback here using logging
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected server error occurred. Please try again later."},
    )


# ============================================
# ROOT ENDPOINT - Health Check
# ============================================

@app.get(
    "/",
    tags=["Health"],
    summary="Health check",
)
async def root():
    """
    Health check endpoint.
    Dùng để verify server đang chạy.
    Monitoring tools (Docker, k8s) sẽ gọi endpoint này định kỳ.
    """
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "healthy",
        "docs": "/docs",
    }


@app.get(
    "/health",
    tags=["Health"],
    summary="Detailed health check",
)
async def health_check():
    """
    Health check chi tiết hơn - kiểm tra cả MongoDB connection.
    """
    db_status = "connected"
    try:
        db = Database.get_db()
        await db.command("ping")
    except Exception:
        db_status = "disconnected"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": db_status,
    }
