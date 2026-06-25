from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field

class UserInDB(BaseModel):
    """Model cho User lưu trong MongoDB"""
    id: str = Field(alias="_id", default=None)
    google_id: str
    email: EmailStr
    full_name: str
    picture: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
class UserResponse(BaseModel):
    """Model trả về cho Frontend"""
    id: str
    email: EmailStr
    full_name: str
    picture: Optional[str] = None
