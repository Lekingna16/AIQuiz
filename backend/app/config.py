"""
Config Management - Quản lý cấu hình ứng dụng
===============================================

Sử dụng Pydantic Settings để:
1. Load biến môi trường từ file .env (development)
2. Override bằng biến môi trường thật (production/Docker)
3. Validate kiểu dữ liệu tự động (str, int, bool)
4. Cung cấp giá trị mặc định an toàn

Tại sao dùng Pydantic Settings thay vì os.getenv() thông thường?
- Type-safe: tự cast "10" → int, "true" → bool
- Validation: báo lỗi ngay nếu thiếu biến bắt buộc
- Autocomplete: IDE hiểu kiểu dữ liệu
- Single source of truth: tất cả config ở 1 chỗ
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Cấu hình toàn cục của ứng dụng.
    
    Pydantic tự động tìm giá trị theo thứ tự ưu tiên:
    1. Biến môi trường hệ thống (cao nhất)
    2. File .env
    3. Giá trị mặc định trong class (thấp nhất)
    """

    # --- Application ---
    APP_NAME: str = "AIQuiz"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False  # True trong dev, False trong production

    # --- MongoDB ---
    # Connection string tới MongoDB instance
    # Trong Docker: mongodb://mongo:27017
    # Local: mongodb://localhost:27017
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "aiquiz"

    # --- Google Gemini ---
    # API Key lấy từ: https://aistudio.google.com/apikey
    DEEPSEEK_API_KEY: str

    # --- File Upload ---
    # Giới hạn kích thước file upload (đơn vị: MB)
    MAX_FILE_SIZE_MB: int = 10

    # --- Authentication ---
    # Google OAuth2 Client ID
    GOOGLE_CLIENT_ID: str = "YOUR_GOOGLE_CLIENT_ID"
    # Khóa bí mật dùng để sign JWT (Nên đổi trong production)
    JWT_SECRET_KEY: str = "super-secret-key-change-this-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # --- CORS ---
    # URL của frontend để cấu hình Cross-Origin Resource Sharing
    # React dev server mặc định chạy port 5173 (Vite)
    FRONTEND_URL: str = "http://localhost:5173"

    @property
    def MAX_FILE_SIZE_BYTES(self) -> int:
        """Chuyển đổi MB sang bytes để dùng trong validation."""
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    # Cấu hình cho Pydantic Settings
    model_config = SettingsConfigDict(
        # Tên file chứa biến môi trường
        env_file=".env",
        # Không phân biệt hoa thường cho tên biến
        # VD: gemini_api_key hoặc GEMINI_API_KEY đều được
        case_sensitive=False,
        # Bỏ qua khoảng trắng thừa trong giá trị
        env_file_encoding="utf-8",
    )


def get_settings() -> Settings:
    """
    Factory function để tạo Settings instance.
    
    Tại sao dùng function thay vì tạo trực tiếp?
    → Để dễ override trong testing (dependency injection)
    → FastAPI sẽ dùng Depends(get_settings) trong routes
    """
    return Settings()
