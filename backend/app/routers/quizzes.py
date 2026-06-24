"""
Quiz Router - API endpoints cho Quiz CRUD và Submit bài
========================================================

Endpoints:
- GET  /api/quizzes          → Danh sách quiz (có pagination)
- GET  /api/quizzes/{id}     → Chi tiết 1 quiz (để làm bài)
- POST /api/quizzes/{id}/submit → Nộp bài và chấm điểm
"""

from fastapi import APIRouter, HTTPException, Query

from app.models.quiz import (
    QuizResponse,
    QuizSummaryResponse,
    QuizSubmitRequest,
    QuizSubmitResponse,
)


router = APIRouter(
    prefix="/api/quizzes",
    tags=["Quizzes"],
)


@router.get(
    "",
    response_model=dict,
    summary="List all quizzes",
    description="Lấy danh sách quiz với pagination.",
)
async def list_quizzes(
    page: int = Query(default=1, ge=1, description="Trang hiện tại"),
    limit: int = Query(default=10, ge=1, le=50, description="Số quiz/trang"),
):
    """
    Trả về danh sách quiz tóm tắt (không kèm câu hỏi).
    Sẽ implement query MongoDB ở Phase 3.
    """
    return {
        "quizzes": [],
        "total": 0,
        "page": page,
        "pages": 0,
        "status": "stub - will be implemented in Phase 3",
    }


@router.get(
    "/{quiz_id}",
    response_model=dict,
    summary="Get quiz for taking",
    description="Lấy chi tiết quiz để làm bài. KHÔNG trả về đáp án đúng.",
)
async def get_quiz(quiz_id: str):
    """
    Trả quiz với câu hỏi (ẩn đáp án).
    Phase 3: query MongoDB, map sang QuestionResponse (không có correct_answer).
    """
    return {
        "message": f"Quiz {quiz_id} endpoint ready",
        "status": "stub - will be implemented in Phase 3",
    }


@router.post(
    "/{quiz_id}/submit",
    response_model=dict,
    summary="Submit quiz answers",
    description="Nộp bài làm, server chấm điểm và trả kết quả chi tiết.",
)
async def submit_quiz(quiz_id: str, payload: QuizSubmitRequest):
    """
    Nhận answers → so sánh với correct_answer trong DB → trả kết quả.
    Phase 3: implement scoring logic.
    """
    return {
        "message": f"Submit for quiz {quiz_id} endpoint ready",
        "answers_received": len(payload.answers),
        "status": "stub - will be implemented in Phase 3",
    }
