"""
Quiz Router - API endpoints cho Quiz CRUD và Submit bài
========================================================

Endpoints:
- GET  /api/quizzes          → Danh sách quiz (có pagination)
- GET  /api/quizzes/{id}     → Chi tiết 1 quiz (để làm bài)
- POST /api/quizzes/{id}/submit → Nộp bài và chấm điểm
"""

from typing import Dict, Any
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
import math
from datetime import datetime, timezone

from app.database import get_db
from app.models.quiz import (
    QuizResponse,
    QuizSummaryResponse,
    QuizSubmitRequest,
    QuizSubmitResponse,
    QuestionResponse,
    AnswerResult,
)
from app.models.user import UserResponse
from app.dependencies import get_current_user


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
    subject: str | None = Query(default=None, description="Lọc theo môn học"),
    chapter: str | None = Query(default=None, description="Lọc theo chương"),
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
    if chapter:
        query["chapter"] = {"$regex": chapter, "$options": "i"}
    if exam_type:
        query["exam_type"] = {"$regex": exam_type, "$options": "i"}
    if school:
        query["school"] = {"$regex": school, "$options": "i"}

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
            "chapter": q.get("chapter"),
            "exam_type": q.get("exam_type"),
            "school": q.get("school"),
            "created_at": q["created_at"].isoformat(),
        })
        
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
            "chapter": q.get("chapter"),
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
        "chapter": quiz.get("chapter"),
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
    "/{quiz_id}/submit",
    response_model=dict,
    summary="Submit quiz answers",
    description="Nộp bài làm, server chấm điểm và trả kết quả chi tiết.",
)
async def submit_quiz(
    quiz_id: str, 
    payload: QuizSubmitRequest,
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
    attempt_doc = {
        "quiz_id": ObjectId(quiz_id),
        "user_id": None, # Will be updated in Phase 5 with auth
        "answers": [{"question_id": ObjectId(q_id), "selected": user_answers_map.get(q_id)} for q_id in question_map.keys()],
        "score": score,
        "total": total,
        "completed_at": datetime.now(timezone.utc)
    }
    await db.quiz_attempts.insert_one(attempt_doc)
    
    return {
        "score": score,
        "total": total,
        "percentage": round(percentage, 2),
        "results": results
    }


@router.delete(
    "/{quiz_id}",
    summary="Delete a quiz",
    description="Xóa quiz và tất cả câu hỏi liên quan khỏi database.",
)
async def delete_quiz(quiz_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    """
    Xóa quiz.
    """
    if not ObjectId.is_valid(quiz_id):
        raise HTTPException(status_code=400, detail="Invalid quiz ID")
        
    result = await db.quizzes.delete_one({"_id": ObjectId(quiz_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Quiz not found")
        
    # Xóa các câu hỏi liên quan
    await db.questions.delete_many({"quiz_id": quiz_id})
    # Xóa các attempts liên quan
    await db.quiz_attempts.delete_many({"quiz_id": ObjectId(quiz_id)})
    
    return {"message": "Quiz deleted successfully"}
