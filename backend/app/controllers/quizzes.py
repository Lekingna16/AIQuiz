"""
Quiz Router - API endpoints cho Quiz CRUD và Submit bài
========================================================

Endpoints:
- GET  /api/quizzes          → Danh sách quiz (có pagination)
- GET  /api/quizzes/{id}     → Chi tiết 1 quiz (để làm bài)
- POST /api/quizzes/{id}/submit → Nộp bài và chấm điểm
"""

import asyncio
import logging
import math
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, Depends, Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_db
from app.education_catalog import EXAM_TYPES, SUBJECTS
from app.services.education_catalog_service import get_courses_by_major
from app.models.quiz import (
    QuizSubmitRequest,
    AnswerCheckRequest,
    AnswerResult,
)
from app.models.user import UserResponse
from app.dependencies import get_current_user, get_current_user_optional

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/quizzes",
    tags=["Quizzes"],
)


QUIZ_SUMMARY_FIELDS = {
    "title": 1,
    "description": 1,
    "total_questions": 1,
    "difficulty": 1,
    "subject": 1,
    "major": 1,
    "exam_type": 1,
    "school": 1,
    "created_at": 1,
}


def _serialize_quiz_summary(quiz: dict) -> dict:
    """Return only the small payload needed by quiz listing cards."""
    return {
        "id": str(quiz["_id"]),
        "title": quiz["title"],
        "description": quiz.get("description", ""),
        "total_questions": quiz["total_questions"],
        "difficulty": quiz["difficulty"],
        "subject": quiz.get("subject"),
        "major": quiz.get("major"),
        "exam_type": quiz.get("exam_type"),
        "school": quiz.get("school"),
        "created_at": quiz["created_at"].isoformat(),
    }


@router.get(
    "/filters",
    response_model=dict,
    summary="Get filter options",
    description="Lấy danh sách các môn học, chương, trường đang có trong database (public).",
)
async def get_quiz_filters(
    include_catalog: bool = Query(default=False),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Return small home-page filters, or the full upload catalogue on demand."""
    query = {"is_public": True, "is_approved": True}

    if not include_catalog:
        subjects = await db.quizzes.distinct("subject", query)
        return {
            "subjects": sorted((subject for subject in subjects if subject), key=str.casefold),
            "exam_types": EXAM_TYPES,
        }

    courses_by_major = await get_courses_by_major(db)
    subjects = list(dict.fromkeys(SUBJECTS + [
        course
        for courses in courses_by_major.values()
        for course in courses
    ]))
    return {
        "subjects": [subject for subject in subjects if subject],
        "majors": sorted(courses_by_major, key=str.casefold),
        "courses_by_major": courses_by_major,
        "exam_types": EXAM_TYPES,
    }


@router.get(
    "/home",
    response_model=dict,
    summary="Get initial home-page data",
    description="Trả danh sách quiz và bộ lọc trong một request nhẹ, có thể cache công khai.",
)
async def get_home_page_data(
    response: Response,
    limit: int = Query(default=20, ge=1, le=50),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Load all data needed for the first home render with one round trip."""
    query = {"is_public": True, "is_approved": True}
    cursor = (
        db.quizzes.find(query, QUIZ_SUMMARY_FIELDS)
        .sort("created_at", -1)
        .limit(limit)
    )

    subjects, quizzes_db = await asyncio.gather(
        db.quizzes.distinct("subject", query),
        cursor.to_list(length=limit),
    )

    # Vercel's public API proxy can serve this snapshot immediately while a
    # sleeping Render instance wakes and refreshes it in the background.
    response.headers["Cache-Control"] = (
        "public, max-age=60, s-maxage=300, stale-while-revalidate=86400"
    )
    return {
        "quizzes": [_serialize_quiz_summary(quiz) for quiz in quizzes_db],
        "filters": {
            "subjects": sorted(
                (subject for subject in subjects if subject),
                key=str.casefold,
            ),
            "exam_types": EXAM_TYPES,
        },
    }

@router.get(
    "",
    response_model=dict,
    summary="List all quizzes",
    description="Lấy danh sách quiz với pagination.",
)
async def list_quizzes(
    page: int = Query(default=1, ge=1, description="Trang hiện tại"),
    limit: int = Query(default=10, ge=1, le=50, description="Số quiz/trang"),
    subject: str | None = Query(default=None, description="Lọc theo môn học"),
    exam_type: str | None = Query(default=None, description="Lọc theo loại kỳ thi"),
    school: str | None = Query(default=None, description="Lọc theo trường"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Trả về danh sách quiz tóm tắt (không kèm câu hỏi).
    """
    skip = (page - 1) * limit
    
    # Base query: public and approved
    query = {"is_public": True, "is_approved": True}
    
    if subject:
        query["subject"] = {"$regex": subject, "$options": "i"}
    if exam_type:
        query["exam_type"] = {"$regex": exam_type, "$options": "i"}
    if school:
        query["school"] = {"$regex": school, "$options": "i"}

    total = await db.quizzes.count_documents(query)
    
    cursor = (
        db.quizzes.find(query, QUIZ_SUMMARY_FIELDS)
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    quizzes_db = await cursor.to_list(length=limit)
    quizzes = [_serialize_quiz_summary(quiz) for quiz in quizzes_db]
        
    return {
        "quizzes": quizzes,
        "total": total,
        "page": page,
        "pages": math.ceil(total / limit) if limit else 0,
    }


@router.get(
    "/me",
    response_model=dict,
    summary="Get current user's quizzes",
    description="Lấy danh sách quiz do user hiện tại tạo.",
)
async def get_my_quizzes(
    page: int = Query(default=1, ge=1, description="Trang hiện tại"),
    limit: int = Query(default=10, ge=1, le=50, description="Số quiz/trang"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    skip = (page - 1) * limit
    query = {"user_id": str(current_user.id)}

    total = await db.quizzes.count_documents(query)
    
    cursor = db.quizzes.find(query).sort("created_at", -1).skip(skip).limit(limit)
    quizzes_db = await cursor.to_list(length=limit)
    
    quizzes = []
    for q in quizzes_db:
        quizzes.append({
            "id": str(q["_id"]),
            "title": q["title"],
            "description": q.get("description", ""),
            "total_questions": q["total_questions"],
            "difficulty": q["difficulty"],
            "subject": q.get("subject"),
            "major": q.get("major"),
            "exam_type": q.get("exam_type"),
            "school": q.get("school"),
            "is_public": q.get("is_public", False),
            "is_approved": q.get("is_approved", False),
            "created_at": q["created_at"].isoformat(),
        })
        
    return {
        "quizzes": quizzes,
        "total": total,
        "page": page,
        "pages": math.ceil(total / limit) if limit else 0,
    }


@router.get(
    "/{quiz_id}",
    response_model=dict,
    summary="Get quiz for taking",
    description="Lấy chi tiết quiz để làm bài. KHÔNG trả về đáp án đúng.",
)
async def get_quiz(quiz_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    """
    Trả quiz với câu hỏi (ẩn đáp án).
    """
    if not ObjectId.is_valid(quiz_id):
        raise HTTPException(status_code=400, detail="Invalid quiz ID")
        
    quiz = await db.quizzes.find_one({"_id": ObjectId(quiz_id)})
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
        
    questions_cursor = db.questions.find({"quiz_id": quiz_id}).sort("order", 1)
    questions = await questions_cursor.to_list(length=None)
    
    return {
        "id": str(quiz["_id"]),
        "title": quiz["title"],
        "description": quiz.get("description", ""),
        "total_questions": quiz["total_questions"],
        "difficulty": quiz["difficulty"],
        "subject": quiz.get("subject"),
        "major": quiz.get("major"),
        "exam_type": quiz.get("exam_type"),
        "school": quiz.get("school"),
        "created_at": quiz["created_at"].isoformat(),
        "questions": [
            {
                "id": str(q["_id"]),
                "question_text": q["question_text"],
                "options": q["options"],
                "order": q["order"],
            }
            for q in questions
        ]
    }


@router.post(
    "/{quiz_id}/questions/{question_id}/check",
    response_model=AnswerResult,
    summary="Check one answer immediately",
    description="Chấm một lựa chọn và trả đáp án đúng ngay sau khi người dùng chọn.",
)
async def check_quiz_answer(
    quiz_id: str,
    question_id: str,
    payload: AnswerCheckRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Return feedback for a single answer without creating a quiz attempt."""
    if not ObjectId.is_valid(quiz_id) or not ObjectId.is_valid(question_id):
        raise HTTPException(status_code=400, detail="Invalid quiz or question ID")

    question = await db.questions.find_one({
        "_id": ObjectId(question_id),
        "quiz_id": quiz_id,
    })
    if not question:
        raise HTTPException(status_code=404, detail="Question not found in this quiz")

    correct_answer = question.get("correct_answer", "")
    return {
        "question_id": question_id,
        "selected": payload.selected,
        "correct_answer": correct_answer,
        "is_correct": payload.selected == correct_answer,
        "explanation": question.get("explanation", ""),
    }


@router.post(
    "/{quiz_id}/submit",
    response_model=dict,
    summary="Submit quiz answers",
    description="Nộp bài làm, server chấm điểm và trả kết quả chi tiết.",
)
async def submit_quiz(
    quiz_id: str, 
    payload: QuizSubmitRequest,
    current_user: UserResponse | None = Depends(get_current_user_optional),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Nhận answers → so sánh với correct_answer trong DB → trả kết quả.
    """
    if not ObjectId.is_valid(quiz_id):
        raise HTTPException(status_code=400, detail="Invalid quiz ID")
        
    quiz = await db.quizzes.find_one({"_id": ObjectId(quiz_id)})
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
        
    # Lấy tất cả câu hỏi của quiz
    questions_cursor = db.questions.find({"quiz_id": quiz_id})
    questions = await questions_cursor.to_list(length=None)
    
    if not questions:
        raise HTTPException(status_code=404, detail="No questions found for this quiz")
        
    # Tạo map question_id -> question_data
    question_map = {str(q["_id"]): q for q in questions}
    
    score = 0
    results = []
    
    # Map user answers
    user_answers_map = {a.question_id: a.selected for a in payload.answers}
    
    for q_id, q_data in question_map.items():
        selected = user_answers_map.get(q_id)
        
        correct_answer = q_data.get("correct_answer", "")
        
        is_correct = (selected == correct_answer) if selected else False
        if is_correct:
            score += 1
            
        results.append({
            "question_id": q_id,
            "selected": selected,
            "correct_answer": correct_answer,
            "is_correct": is_correct,
            "explanation": q_data.get("explanation", ""),
        })
        
    total = len(questions)
    percentage = (score / total) * 100 if total > 0 else 0
    
    # Optional: Lưu kết quả làm bài vào quiz_attempts collection
    attempt_id = None
    if current_user:
        attempt_doc = {
            "quiz_id": ObjectId(quiz_id),
            "user_id": str(current_user.id),
            "answers": [{"question_id": ObjectId(q_id), "selected": user_answers_map.get(q_id)} for q_id in question_map.keys()],
            "score": score,
            "total": total,
            "percentage": percentage,
            "completed_at": datetime.now(timezone.utc)
        }
        insert_res = await db.quiz_attempts.insert_one(attempt_doc)
        attempt_id = str(insert_res.inserted_id)
    
    return {
        "attempt_id": attempt_id,
        "score": score,
        "total": total,
        "percentage": round(percentage, 2),
        "results": results
    }

@router.get(
    "/attempts/me",
    response_model=dict,
    summary="Get user's quiz attempts",
    description="Lấy danh sách các lần làm bài của user hiện tại",
)
async def get_my_attempts(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=50),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    try:
        skip = (page - 1) * limit
        query = {"user_id": str(current_user.id)}
        total = await db.quiz_attempts.count_documents(query)
        
        cursor = db.quiz_attempts.find(query).sort("completed_at", -1).skip(skip).limit(limit)
        attempts = await cursor.to_list(length=limit)
        
        result = []
        for att in attempts:
            quiz = await db.quizzes.find_one({"_id": att["quiz_id"]})
            result.append({
                "id": str(att["_id"]),
                "quiz_id": str(att["quiz_id"]),
                "quiz_title": quiz["title"] if quiz else "Quiz đã xóa",
                "score": att["score"],
                "total": att["total"],
                "percentage": att.get("percentage", 0),
                "completed_at": att["completed_at"].isoformat() if "completed_at" in att and hasattr(att["completed_at"], "isoformat") else str(att.get("completed_at", ""))
            })
            
        return {
            "attempts": result,
            "total": total,
            "page": page,
            "pages": math.ceil(total / limit) if limit else 0,
        }
    except Exception:
        logger.exception("Error in get_my_attempts for user_id=%s", current_user.id)
        raise

@router.get(
    "/attempts/{attempt_id}",
    response_model=dict,
    summary="Get specific attempt details",
)
async def get_attempt_details(
    attempt_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    if not ObjectId.is_valid(attempt_id):
        raise HTTPException(status_code=400, detail="Invalid attempt ID")
        
    attempt = await db.quiz_attempts.find_one({"_id": ObjectId(attempt_id), "user_id": str(current_user.id)})
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
        
    quiz_id = str(attempt["quiz_id"])
    quiz = await db.quizzes.find_one({"_id": attempt["quiz_id"]})
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
        
    questions_cursor = db.questions.find({"quiz_id": quiz_id})
    questions = await questions_cursor.to_list(length=None)
    question_map = {str(q["_id"]): q for q in questions}
    
    user_answers_map = {str(a["question_id"]): a.get("selected") for a in attempt["answers"]}
    
    results = []
    for q_id, q_data in question_map.items():
        selected = user_answers_map.get(q_id)
        correct_answer = q_data.get("correct_answer", "")
        is_correct = (selected == correct_answer) if selected else False
        
        results.append({
            "question_id": q_id,
            "selected": selected,
            "correct_answer": correct_answer,
            "is_correct": is_correct,
            "explanation": q_data.get("explanation", ""),
        })
        
    return {
        "attempt_id": str(attempt["_id"]),
        "quiz_id": quiz_id,
        "quiz_title": quiz["title"],
        "score": attempt["score"],
        "total": attempt["total"],
        "percentage": attempt.get("percentage", 0),
        "results": results,
        "questions": [
            {
                "id": str(q["_id"]),
                "question_text": q["question_text"],
                "options": q["options"],
                "order": q["order"],
            }
            for q in questions
        ]
    }


@router.delete(
    "/{quiz_id}",
    summary="Delete a quiz",
    description="Xóa quiz và tất cả câu hỏi liên quan khỏi database.",
)
async def delete_quiz(
    quiz_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Xóa quiz.
    """
    if not ObjectId.is_valid(quiz_id):
        raise HTTPException(status_code=400, detail="Invalid quiz ID")
        
    result = await db.quizzes.delete_one({
        "_id": ObjectId(quiz_id),
        "user_id": str(current_user.id),
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Quiz not found")
        
    # Xóa các câu hỏi liên quan
    await db.questions.delete_many({"quiz_id": quiz_id})
    # Xóa các attempts liên quan
    await db.quiz_attempts.delete_many({"quiz_id": ObjectId(quiz_id)})
    
    return {"message": "Quiz deleted successfully"}
