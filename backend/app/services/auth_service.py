from datetime import datetime, timedelta
import jwt
from google.oauth2 import id_token
from google.auth.transport import requests
from fastapi import HTTPException
from bson import ObjectId

from app.config import get_settings
from app.database import Database
from app.models.user import UserInDB, UserResponse

settings = get_settings()

class AuthService:
    @staticmethod
    def verify_google_token(token: str) -> dict:
        """
        Xác thực token từ Google trả về
        """
        try:
            # Nếu chạy local và chưa có GOOGLE_CLIENT_ID thật, có thể cho qua lúc dev
            if settings.GOOGLE_CLIENT_ID == "YOUR_GOOGLE_CLIENT_ID":
                # Mock data for testing when no real client ID is provided
                import json
                try:
                    # Very simple JWT decode without verification for dev mode only
                    payload_part = token.split('.')[1]
                    # Add padding if needed
                    payload_part += "=" * ((4 - len(payload_part) % 4) % 4)
                    import base64
                    payload = json.loads(base64.urlsafe_b64decode(payload_part).decode('utf-8'))
                    return payload
                except:
                    raise ValueError("Invalid mock token")
            
            # Real validation
            clean_client_id = settings.GOOGLE_CLIENT_ID.replace('"', '').replace("'", "").strip()
            idinfo = id_token.verify_oauth2_token(
                token, 
                requests.Request(), 
                clean_client_id,
                clock_skew_in_seconds=60  # Cho phép lệch giờ lên tới 60 giây
            )

            if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                raise ValueError('Wrong issuer.')

            return idinfo
        except ValueError as e:
            raise HTTPException(status_code=401, detail=f"Invalid Google token: {str(e)}")

    @staticmethod
    async def get_or_create_user(idinfo: dict) -> UserResponse:
        """
        Tìm user trong DB bằng google_id. Nếu chưa có thì tạo mới.
        """
        db = Database.get_db()
        google_id = idinfo.get("sub")
        email = idinfo.get("email")
        name = idinfo.get("name")
        picture = idinfo.get("picture")

        if not google_id or not email:
            raise HTTPException(status_code=400, detail="Incomplete Google profile info")

        # Tìm user
        user_doc = await db.users.find_one({"google_id": google_id})

        if user_doc:
            user_doc["_id"] = str(user_doc["_id"])
            return UserResponse(
                id=user_doc["_id"],
                email=user_doc["email"],
                full_name=user_doc["full_name"],
                picture=user_doc.get("picture")
            )

        # Tạo user mới
        new_user = {
            "google_id": google_id,
            "email": email,
            "full_name": name,
            "picture": picture,
            "created_at": datetime.utcnow()
        }

        result = await db.users.insert_one(new_user)
        
        return UserResponse(
            id=str(result.inserted_id),
            email=email,
            full_name=name,
            picture=picture
        )

    @staticmethod
    def create_access_token(data: dict) -> str:
        """
        Tạo JWT token cho session của app
        """
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})
        
        encoded_jwt = jwt.encode(
            to_encode, 
            settings.JWT_SECRET_KEY, 
            algorithm=settings.JWT_ALGORITHM
        )
        return encoded_jwt
