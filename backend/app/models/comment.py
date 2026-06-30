from datetime import datetime, timezone
from pydantic import BaseModel, Field

class CommentInDB(BaseModel):
    id: str = Field(..., alias="_id")
    question_id: str = Field(...)
    user_id: str | None = Field(default=None) # None nếu khách
    guest_name: str | None = Field(default=None) # Tên hiển thị nếu là khách
    content: str = Field(...)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    model_config = {"populate_by_name": True}

class CommentResponse(BaseModel):
    id: str
    question_id: str
    user_id: str | None = None
    guest_name: str | None = None
    content: str
    created_at: datetime

class CommentCreate(BaseModel):
    guest_name: str | None = None
    content: str = Field(..., min_length=1)
