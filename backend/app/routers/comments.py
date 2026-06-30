from typing import List
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime, timezone

from app.database import get_db
from app.models.comment import CommentCreate, CommentResponse
from app.models.user import UserResponse
from app.dependencies import get_current_user, get_current_user_optional

router = APIRouter(
    prefix="/api/comments",
    tags=["Comments"],
)

@router.get("/question/{question_id}", response_model=List[CommentResponse])
async def get_comments(question_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    if not ObjectId.is_valid(question_id):
        raise HTTPException(status_code=400, detail="Invalid question ID")
        
    cursor = db.comments.find({"question_id": question_id}).sort("created_at", 1)
    comments_db = await cursor.to_list(length=None)
    
    comments = []
    for c in comments_db:
        comments.append({
            "id": str(c["_id"]),
            "question_id": c["question_id"],
            "user_id": c.get("user_id"),
            "guest_name": c.get("guest_name"),
            "content": c["content"],
            "created_at": c["created_at"].isoformat()
        })
    return comments

@router.post("/question/{question_id}", response_model=CommentResponse)
async def create_comment(
    question_id: str,
    payload: CommentCreate,
    current_user: UserResponse | None = Depends(get_current_user_optional),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    if not ObjectId.is_valid(question_id):
        raise HTTPException(status_code=400, detail="Invalid question ID")
        
    user_id = str(current_user.id) if current_user else None
    guest_name = payload.guest_name if not current_user else current_user.name

    if not user_id and not guest_name:
        guest_name = "Khách"

    comment_doc = {
        "question_id": question_id,
        "user_id": user_id,
        "guest_name": guest_name,
        "content": payload.content,
        "created_at": datetime.now(timezone.utc)
    }
    
    result = await db.comments.insert_one(comment_doc)
    comment_doc["id"] = str(result.inserted_id)
    comment_doc["created_at"] = comment_doc["created_at"].isoformat()
    return comment_doc
