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

import logging

from bson import ObjectId
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import get_settings
from app.database import get_db
from app.education_catalog import EXAM_TYPES
from app.services.education_catalog_service import is_known_major
from app.models.document import DocumentResponse
from app.models.quiz import QuizResponse, Difficulty
from app.models.user import UserResponse
from app.dependencies import get_current_user, get_current_user_optional
from app.services.ai_service import (
    DeepSeekService,
    DeepSeekServiceError,
    QuizGenerationError,
    APIConnectionError,
)
from app.services.quiz_service import QuizService

logger = logging.getLogger(__name__)


# ============================================
# CONSTANTS
# ============================================

# Các loại file được phép upload
ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}

# MIME type mapping (validate cả extension và content-type)
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}


# ============================================
# ROUTER
# ============================================

# Tạo router với prefix "/api/documents"
# Tất cả routes trong file này sẽ bắt đầu bằng /api/documents
router = APIRouter(
    prefix="/api/documents",
    tags=["Documents"],  # Nhóm trong Swagger UI
)


# ============================================
# HELPERS
# ============================================

def _get_file_extension(filename: str) -> str:
    """Extract file extension từ filename (lowercase, không có dấu chấm)."""
    if not filename or "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


def _validate_file(file: UploadFile, max_size_bytes: int) -> tuple[str, bytes]:
    """
    Validate file upload.

    Không thể dùng async vì cần đọc file_bytes trước.
    Được gọi sau khi đã read content.

    Returns: (file_extension, ) — file_bytes được đọc ở caller
    """
    # Validate filename
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Filename is required.",
        )

    # Validate extension
    ext = _get_file_extension(file.filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File type '.{ext}' is not supported. "
                f"Allowed types: {', '.join('.' + e for e in sorted(ALLOWED_EXTENSIONS))}"
            ),
        )

    return ext


# ============================================
# ENDPOINTS
# ============================================

@router.get(
    "/me",
    response_model=dict,
    summary="List the current user's uploaded documents",
)
async def get_my_documents(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Return upload metadata only; extracted source text is never exposed."""
    cursor = db.documents.find({"user_id": str(current_user.id)}).sort("created_at", -1)
    documents = await cursor.to_list(length=None)

    result = []
    for document in documents:
        document_id = str(document["_id"])
        quiz_count = await db.quizzes.count_documents({"document_id": document_id})
        result.append({
            "id": document_id,
            "original_filename": document["original_filename"],
            "file_type": document["file_type"],
            "upload_status": document.get("upload_status", "completed"),
            "quiz_count": quiz_count,
            "created_at": document["created_at"].isoformat(),
        })
    return {"documents": result}


@router.delete(
    "/{document_id}",
    summary="Delete an uploaded document and every quiz created from it",
)
async def delete_document(
    document_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Delete only the authenticated owner's upload and dependent records."""
    if not ObjectId.is_valid(document_id):
        raise HTTPException(status_code=400, detail="Invalid document ID")

    document = await db.documents.find_one({
        "_id": ObjectId(document_id),
        "user_id": str(current_user.id),
    })
    if not document:
        raise HTTPException(status_code=404, detail="Uploaded document not found")

    quizzes = await db.quizzes.find({"document_id": document_id}).to_list(length=None)
    quiz_ids = [str(quiz["_id"]) for quiz in quizzes]
    if quiz_ids:
        questions = await db.questions.find({"quiz_id": {"$in": quiz_ids}}).to_list(length=None)
        await db.questions.delete_many({"quiz_id": {"$in": quiz_ids}})
        await db.quizzes.delete_many({"_id": {"$in": [ObjectId(quiz_id) for quiz_id in quiz_ids]}})
        await db.quiz_attempts.delete_many({"quiz_id": {"$in": [ObjectId(quiz_id) for quiz_id in quiz_ids]}})

    await db.documents.delete_one({"_id": ObjectId(document_id)})
    return {"message": "Uploaded document deleted", "deleted_quizzes": len(quiz_ids)}

@router.post(
    "/upload",
    response_model=dict,
    status_code=200,
    summary="Upload document & generate quiz",
    description="""
    Upload file PDF/DOCX/TXT → Extract text → Gemini AI sinh câu hỏi.
    
    Flow: File → Validate → Extract Text → AI Generate → Save DB → Response
    
    **Giới hạn:**
    - File tối đa 50MB
    - Hỗ trợ: .pdf, .docx, .txt
    - Số câu hỏi: 5-30
    
    **Response** trả về quiz với danh sách câu hỏi (KHÔNG kèm đáp án).
    """,
    responses={
        400: {"description": "File type not supported / Invalid input"},
        413: {"description": "File too large (max 50MB)"},
        422: {"description": "Could not extract text from file"},
        503: {"description": "AI service unavailable"},
    },
)
async def upload_document(
    file: UploadFile = File(
        ...,
        description="File tài liệu (PDF, DOCX, TXT). Max 50MB.",
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
    mode: str = Query(
        default="generate",
        description="Chế độ xử lý: generate (sinh câu mới) hoặc extract (trích xuất và lọc trùng)",
    ),
    is_public: bool = Query(
        default=True,
        description="Cho phép quiz hiển thị công khai",
    ),
    subject: str = Query(min_length=1, max_length=150),
    major: str = Query(min_length=1, max_length=150),
    exam_type: str = Query(min_length=1, max_length=150),
    school: str | None = None,
    current_user: UserResponse | None = Depends(get_current_user_optional),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Endpoint chính: Upload file → Extract text → AI sinh quiz.

    Pipeline hoàn chỉnh xử lý từ file bytes đến quiz data.
    """
    settings = get_settings()
    subject = subject.strip()
    major = major.strip()
    exam_type = exam_type.strip()
    school = school.strip() if school else None

    if not await is_known_major(db, major) or exam_type not in EXAM_TYPES:
        raise HTTPException(
            status_code=422,
            detail="Major and exam type must be selected from the provided catalog.",
        )

    # =====================
    # Step 1: Validate file type (trước khi đọc content)
    # =====================
    file_ext = _validate_file(file, settings.MAX_FILE_SIZE_BYTES)

    # =====================
    # Step 2: Read file content & validate size
    # =====================
    try:
        file_bytes = await file.read()
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to read uploaded file: {str(e)}",
        )

    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty.",
        )

    if len(file_bytes) > settings.MAX_FILE_SIZE_BYTES:
        size_mb = len(file_bytes) / (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=(
                f"File size ({size_mb:.1f}MB) exceeds the "
                f"{settings.MAX_FILE_SIZE_MB}MB limit."
            ),
        )

    # =====================
    # Step 3: Initialize services & run pipeline
    # =====================
    try:
        ai_service = DeepSeekService(api_key=settings.DEEPSEEK_API_KEY)
        quiz_service = QuizService(db=db, gemini_service=ai_service)

        result = await quiz_service.upload_and_generate_quiz(
            file_bytes=file_bytes,
            filename=file.filename,
            file_type=file_ext,
            num_questions=num_questions,
            difficulty=difficulty.value,
            language=language,
            mode=mode,
            user_id=str(current_user.id) if current_user else None,
            is_public=is_public,
            subject=subject,
            major=major,
            exam_type=exam_type,
            school=school,
        )

        return result

    except ValueError as e:
        # Text extraction / validation errors
        raise HTTPException(status_code=422, detail=str(e))

    except QuizGenerationError as e:
        # Keep internal model details out of the user-facing response.
        logger.error(f"Quiz generation error: {e}")
        raise HTTPException(
            status_code=422,
            detail=(
                "Không thể tạo đủ số câu như yêu cầu từ tài liệu này. "
                "Vui lòng giảm số câu hoặc chọn tài liệu có nhiều nội dung hơn."
            ),
        )

    except APIConnectionError as e:
        # Keep implementation details out of the user-facing response.
        logger.error(f"DeepSeek API connection error: {e}")
        raise HTTPException(
            status_code=503,
            detail="Dịch vụ tạo bài quiz đang tạm thời không phản hồi. Vui lòng thử lại sau.",
        )

    except DeepSeekServiceError as e:
        # Generic DeepSeek errors
        logger.error(f"DeepSeek service error: {e}")
        raise HTTPException(
            status_code=503,
            detail="Không thể tạo bài quiz vào lúc này. Vui lòng thử lại sau.",
        )

    except Exception as e:
        logger.exception(f"Unexpected error in upload: {e}")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred. Please try again.",
        )
