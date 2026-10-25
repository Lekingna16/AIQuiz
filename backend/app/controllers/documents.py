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

import asyncio
import logging
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, HTTPException, Query, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import get_settings
from app.database import get_db
from app.education_catalog import EXAM_TYPES
from app.models.document import DocumentResponse
from app.models.quiz import QuizResponse, Difficulty
from app.models.user import UserResponse
from app.dependencies import get_current_user, get_current_user_optional
from app.services.ai_service import (
    DeepSeekService,
    FailoverAIService,
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

# Small Render instances should process one expensive AI request at a time.
# Rejecting immediately is safer than allowing concurrent generations to
# exhaust memory/CPU and make every request time out.
_generation_semaphore = asyncio.Semaphore(1)


async def _generate_in_available_slot(quiz_service: QuizService, **kwargs):
    # Jobs wait in memory instead of making the browser retry while a single
    # small instance is already generating another quiz.
    async with _generation_semaphore:
        return await quiz_service.upload_and_generate_quiz(**kwargs)


# ============================================
# HELPERS
# ============================================

def _get_file_extension(filename: str) -> str:
    """Extract file extension từ filename (lowercase, không có dấu chấm)."""
    if not filename or "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


def _create_ai_service(settings) -> DeepSeekService | FailoverAIService:
    """Build the configured OpenAI-compatible generation client."""
    provider = getattr(settings, "AI_PROVIDER", "deepseek").strip().lower()
    if provider == "gemini":
        primary = DeepSeekService(
            api_key=getattr(settings, "GEMINI_API_KEY", None),
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            model=getattr(settings, "GEMINI_MODEL", "gemini-3.8-flash"),
            provider_name="Gemini",
        )
        fallback_key = getattr(settings, "DEEPSEEK_API_KEY", None)
        if fallback_key and not fallback_key.startswith("your_"):
            return FailoverAIService(
                primary=primary,
                fallback=DeepSeekService(api_key=fallback_key),
            )
        return primary

    return DeepSeekService(api_key=getattr(settings, "DEEPSEEK_API_KEY", None))


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


async def _process_upload_job(
    *,
    db: AsyncIOMotorDatabase,
    job_id: ObjectId,
    file_bytes: bytes,
    filename: str,
    file_type: str,
    options: dict,
) -> None:
    """Run the expensive extraction and AI generation after the upload responds."""
    await db.upload_jobs.update_one(
        {"_id": job_id},
        {"$set": {"status": "processing", "started_at": datetime.now(timezone.utc)}},
    )

    try:
        settings = get_settings()
        quiz_service = QuizService(db=db, gemini_service=_create_ai_service(settings))
        result = await _generate_in_available_slot(
            quiz_service,
            file_bytes=file_bytes,
            filename=filename,
            file_type=file_type,
            **options,
        )
        await db.upload_jobs.update_one(
            {"_id": job_id},
            {"$set": {
                "status": "completed",
                "quiz_id": result["quiz"]["id"],
                "document_id": result["document_id"],
                "completed_at": datetime.now(timezone.utc),
            }},
        )
        return
    except ValueError as exc:
        logger.info("Upload job %s rejected: %s", job_id, exc)
        error = str(exc)
    except (QuizGenerationError, APIConnectionError, DeepSeekServiceError) as exc:
        logger.error("Upload job %s failed in AI service: %s", job_id, exc)
        error = "Dịch vụ AI tạm thời không phản hồi. Vui lòng thử lại sau."
    except Exception:
        logger.exception("Unexpected failure in upload job %s", job_id)
        error = "Không thể xử lý tài liệu lúc này. Vui lòng thử lại sau."

    await db.upload_jobs.update_one(
        {"_id": job_id},
        {"$set": {
            "status": "failed",
            "error": error,
            "completed_at": datetime.now(timezone.utc),
        }},
    )


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


@router.get("/jobs/{job_id}", summary="Get asynchronous upload job status")
async def get_upload_job(
    job_id: str,
    current_user: UserResponse | None = Depends(get_current_user_optional),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    if not ObjectId.is_valid(job_id):
        raise HTTPException(status_code=404, detail="Upload job not found")

    job = await db.upload_jobs.find_one({"_id": ObjectId(job_id)})
    if not job or (
        job.get("user_id")
        and (not current_user or job["user_id"] != str(current_user.id))
    ):
        raise HTTPException(status_code=404, detail="Upload job not found")

    return {
        "job_id": str(job["_id"]),
        "status": job["status"],
        "quiz_id": job.get("quiz_id"),
        "error": job.get("error"),
    }

@router.post(
    "/upload",
    response_model=dict,
    status_code=202,
    summary="Upload document and queue quiz generation",
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
    background_tasks: BackgroundTasks,
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

    if exam_type not in EXAM_TYPES:
        raise HTTPException(
            status_code=422,
            detail="Exam type must be selected from the provided catalog.",
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
    # Queue expensive OCR and AI generation after responding to the browser.
    job = {
        "status": "queued",
        "user_id": str(current_user.id) if current_user else None,
        "original_filename": file.filename,
        "created_at": datetime.now(timezone.utc),
    }
    insert_result = await db.upload_jobs.insert_one(job)
    job_id = insert_result.inserted_id

    background_tasks.add_task(
        _process_upload_job,
        db=db,
        job_id=job_id,
        file_bytes=file_bytes,
        filename=file.filename,
        file_type=file_ext,
        options={
            "num_questions": num_questions,
            "difficulty": difficulty.value,
            "language": language,
            "mode": mode,
            "user_id": str(current_user.id) if current_user else None,
            "is_public": is_public,
            "subject": subject,
            "major": major,
            "exam_type": exam_type,
            "school": school,
        },
    )
    return {"job_id": str(job_id), "status": "queued"}
