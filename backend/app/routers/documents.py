"""
Document Router - API endpoints xử lý file upload
====================================================

Tại sao tách Router ra file riêng thay vì viết hết trong main.py?
1. Separation of Concerns: mỗi file phụ trách 1 nhóm endpoints
2. Scalability: thêm router mới không ảnh hưởng code cũ
3. Testing: test từng router độc lập
4. Team work: nhiều người làm song song không conflict

FastAPI APIRouter hoạt động giống "mini FastAPI app":
- Định nghĩa routes với prefix và tags
- Sau đó include vào main app
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Query

from app.models.document import DocumentResponse
from app.models.quiz import QuizResponse, Difficulty


# Tạo router với prefix "/api/documents"
# Tất cả routes trong file này sẽ bắt đầu bằng /api/documents
router = APIRouter(
    prefix="/api/documents",
    tags=["Documents"],  # Nhóm trong Swagger UI
)


@router.post(
    "/upload",
    response_model=dict,  # Sẽ cập nhật response model ở Phase 2
    status_code=200,
    summary="Upload document & generate quiz",
    description="""
    Upload file PDF/DOCX/TXT → Extract text → Gemini AI sinh câu hỏi.
    
    Flow: File → Validate → Extract Text → AI Generate → Save DB → Response
    """,
)
async def upload_document(
    file: UploadFile = File(
        ...,
        description="File tài liệu (PDF, DOCX, TXT). Max 10MB.",
    ),
    num_questions: int = Query(
        default=10,
        ge=5,       # Tối thiểu 5 câu
        le=30,      # Tối đa 30 câu
        description="Số lượng câu hỏi muốn tạo",
    ),
    difficulty: Difficulty = Query(
        default=Difficulty.MIXED,
        description="Mức độ khó",
    ),
    language: str = Query(
        default="vi",
        description="Ngôn ngữ câu hỏi (vi, en)",
    ),
):
    """
    Endpoint chính của app - Upload file và sinh quiz.
    
    Sẽ implement đầy đủ ở Phase 2. Hiện tại trả về stub response
    để verify routing hoạt động.
    """
    # --- Stub response (Phase 1) ---
    # Phase 2 sẽ thay bằng logic thực:
    # 1. Validate file type & size
    # 2. Extract text
    # 3. Call Gemini API
    # 4. Save to MongoDB
    # 5. Return quiz data
    return {
        "message": "Upload endpoint ready",
        "filename": file.filename,
        "num_questions": num_questions,
        "difficulty": difficulty,
        "language": language,
        "status": "stub - will be implemented in Phase 2",
    }
