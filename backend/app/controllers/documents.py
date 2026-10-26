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
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, HTTPException, Query, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import get_settings
from app.database import get_db
from app.education_catalog import EXAM_TYPES
from app.models.quiz import Difficulty
from app.models.user import UserResponse
from app.dependencies import get_current_user, get_current_user_optional
logger = logging.getLogger(__name__)

# Loading the AI SDK and document/OCR pipeline adds noticeable cold-start
# time. Keep the upload service lazy so public home requests can be served
# before those modules are needed. The module attribute remains injectable in
# tests.
QuizService = None


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

# Small Render instances process one document pipeline at a time.
_generation_semaphore = asyncio.Semaphore(1)
# One active document and at most one waiting upload per API process. Reserve
# before reading bytes so queued 50 MB files cannot accumulate in memory.
_upload_reservations: set[ObjectId] = set()


async def _generate_in_available_slot(quiz_service: Any, **kwargs):
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


def _create_ai_service(settings):
    """Build the configured OpenAI-compatible generation client."""
    from app.services.ai_service import DeepSeekService, FailoverAIService

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
                fallback=DeepSeekService(api_key=fallback_key, model=getattr(settings, "DEEPSEEK_MODEL", "deepseek-flash")),
            )
        return primary

    return DeepSeekService(
        api_key=getattr(settings, "DEEPSEEK_API_KEY", None),
        model=getattr(settings, "DEEPSEEK_MODEL", "deepseek-flash"),
    )


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
    *, reservation=None, **kwargs,
) -> None:
    try:
        await _run_upload_job(**kwargs)
    finally:
        if reservation is not None:
            _upload_reservations.discard(reservation)


async def _run_upload_job(
    *,
    db: AsyncIOMotorDatabase,
    job_id: ObjectId,
    file_bytes: bytes,
    filename: str,
    file_type: str,
    options: dict,
) -> None:
    """Run the expensive extraction and AI generation after the upload responds."""
    from app.services.ai_service import (
        APIConnectionError,
        DeepSeekServiceError,
        QuizGenerationError,
    )

    quiz_service_factory = QuizService
    if quiz_service_factory is None:
        from app.services.quiz_service import QuizService as quiz_service_factory

    async def progress(stage, **details):
        # Progress reporting must not cause a successful AI read to be repeated.
        try:
            async with asyncio.timeout(2):
                await db.upload_jobs.update_one(
                    {"_id": job_id},
                    {"$set": {"status": "processing", "stage": stage,
                              "updated_at": datetime.now(timezone.utc), **details}},
                )
        except Exception:
            logger.warning("Could not update progress for job %s", job_id)

    try:
        settings = get_settings()
        quiz_service = quiz_service_factory(db=db, gemini_service=_create_ai_service(settings))
        quiz_service.progress_callback = progress
        # Includes queue wait, reading and answer solving. Never leave a live
        # process polling indefinitely after provider retries.
        async with asyncio.timeout(600):
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
    except TimeoutError:
        error = "Xử lý tài liệu quá thời gian chờ. Vui lòng chia file nhỏ hơn và thử lại."
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
        "stage": job.get("stage", job["status"]),
        "completed_pages": job.get("completed_pages"),
        "total_pages": job.get("total_pages"),
        "question_count": job.get("question_count"),
        "elapsed_seconds": job.get("elapsed_seconds"),
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

    if len(_upload_reservations) >= 2:
        raise HTTPException(
            status_code=429,
            detail="Máy chủ đang xử lý đủ số tài liệu. Vui lòng đợi khoảng một phút rồi thử lại.",
            headers={"Retry-After": "60"},
        )
    reservation = ObjectId()
    _upload_reservations.add(reservation)
    try:
        return await _read_and_queue_upload(
            background_tasks=background_tasks, db=db, file=file,
            file_ext=file_ext, settings=settings, reservation=reservation,
            options={
                "num_questions": num_questions, "difficulty": difficulty.value,
                "language": language, "mode": mode,
                "user_id": str(current_user.id) if current_user else None,
                "is_public": is_public, "subject": subject, "major": major,
                "exam_type": exam_type, "school": school,
            },
        )
    except BaseException:
        _upload_reservations.discard(reservation)
        raise


async def _read_and_queue_upload(
    *, background_tasks, db, file, file_ext, settings, reservation, options,
):

    # =====================
    # Step 2: Read file content & validate size
    # =====================
    try:
        file_bytes = await file.read(settings.MAX_FILE_SIZE_BYTES + 1)
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
        "stage": "queued",
        "user_id": options["user_id"],
        "original_filename": file.filename,
        "created_at": datetime.now(timezone.utc),
    }
    insert_result = await db.upload_jobs.insert_one(job)
    job_id = insert_result.inserted_id

    background_tasks.add_task(
        _process_upload_job,
        reservation=reservation,
        db=db,
        job_id=job_id,
        file_bytes=file_bytes,
        filename=file.filename,
        file_type=file_ext,
        options=options,
    )
    return {"job_id": str(job_id), "status": "queued"}
