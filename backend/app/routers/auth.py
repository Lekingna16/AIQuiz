from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any

from app.services.auth_service import AuthService
from app.models.user import UserResponse
from app.dependencies import get_current_user

router = APIRouter(prefix="/api/auth", tags=["Auth"])

class GoogleLoginRequest(BaseModel):
    credential: str

class AuthResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

@router.post("/google", response_model=AuthResponse)
async def google_login(request: GoogleLoginRequest):
    """
    Xác thực Google ID Token, tạo user nếu chưa có và trả về JWT token
    """
    try:
        # 1. Verify token with Google
        idinfo = AuthService.verify_google_token(request.credential)
        
        # 2. Find or create user
        user = await AuthService.get_or_create_user(idinfo)
        
        # 3. Create our own JWT token
        access_token = AuthService.create_access_token(
            data={"sub": str(user.id)}
        )
        
        return AuthResponse(
            access_token=access_token,
            token_type="bearer",
            user=user
        )
    except HTTPException as e:
        with open("debug.log", "a", encoding="utf-8") as f:
            f.write(f"HTTPException: {e.detail}\n")
        raise
    except Exception as e:
        with open("debug.log", "a", encoding="utf-8") as f:
            f.write(f"Exception: {str(e)}\n")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: UserResponse = Depends(get_current_user)):
    """
    Lấy thông tin của user hiện tại đang login
    """
    return current_user
