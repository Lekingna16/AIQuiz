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

from pydantic import field_validator
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

    @field_validator("DEBUG", mode="before")
    @classmethod
    def normalize_debug_value(cls, value):
        """Accept common deployment labels without preventing the API from starting.

        Some hosts inject ``DEBUG=release`` or ``DEBUG=production``.  Pydantic
        only accepts boolean strings by default, so that otherwise harmless
        environment variable made the whole application fail during import.
        """
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "production", "prod"}:
                return False
            if normalized in {"development", "dev"}:
                return True
        return value

    # --- MongoDB ---
    # Connection string tới MongoDB instance
    # Trong Docker: mongodb://mongo:27017
    # Local: mongodb://localhost:27017
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "aiquiz"

    # --- Google Gemini ---
    # API Key lấy từ: https://aistudio.google.com/apikey
    # Gemini uses the OpenAI-compatible endpoint. Keep DeepSeek as an
    # optional fallback so existing deployments continue to start.
    AI_PROVIDER: str = "deepseek"
    DEEPSEEK_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-3.8-flash"

    @field_validator("AI_PROVIDER")
    @classmethod
    def validate_ai_provider(cls, value: str) -> str:
        provider = value.strip().lower()
        if provider not in {"deepseek", "gemini"}:
            raise ValueError("AI_PROVIDER must be either 'deepseek' or 'gemini'.")
        return provider

    # --- File Upload ---
    # Giới hạn kích thước file upload (đơn vị: MB)
    MAX_FILE_SIZE_MB: int = 50

    # --- OCR (ảnh scan trong PDF, ảnh chèn trong Word) ---
    # OCR cục bộ dùng Tesseract nhúng sẵn trong PyMuPDF, chỉ cần file
    # *.traineddata (chạy: python scripts/download_tessdata.py).
    OCR_ENABLED: bool = True
    # Ngôn ngữ Tesseract, nối bằng "+" (vie = tiếng Việt, eng = tiếng Anh)
    OCR_LANGUAGES: str = "vie+eng"
    # 250 DPI giữ được dấu tiếng Việt / nhãn A-D trên đề scan, vẫn nhẹ hơn
    # mức 300 DPI trước đây. Trang phát hiện thiếu phương án sẽ tự đọc lại 300 DPI.
    OCR_DPI: int = 250
    # Số trang PDF tối đa được OCR cục bộ cho 1 file. Giới hạn này giữ một file
    # scan lớn không chiếm toàn bộ CPU của instance Render.
    OCR_MAX_PAGES: int = 24
    # Thư mục chứa *.traineddata; để trống → tự tìm (backend/tessdata, env, máy)
    TESSDATA_PREFIX: str | None = None
    # Với PDF scan hoàn toàn, ưu tiên Gemini Vision để giữ chữ tiếng Việt và
    # đủ các phương án; nếu Vision lỗi/quota thì quay về OCR cục bộ.
    OCR_AI_VISION: bool = True

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
