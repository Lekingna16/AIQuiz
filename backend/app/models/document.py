"""
Document Model - Schema cho tài liệu user upload
===================================================

Pydantic Models phục vụ 2 mục đích:
1. Validation: tự validate dữ liệu đầu vào (request body)
2. Serialization: chuyển dữ liệu từ MongoDB → JSON response

Tại sao tách riêng Request model và Response model?
- Request: chỉ chứa fields user gửi lên
- Response: chứa thêm _id, created_at (server tự tạo)
- Nguyên tắc: KHÔNG bao giờ expose toàn bộ DB schema ra ngoài
"""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class FileType(str, Enum):
    """
    Enum giới hạn các loại file được phép upload.
    Kế thừa str để serialize thành JSON dễ dàng.
    """
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"


class UploadStatus(str, Enum):
    """Trạng thái xử lý file upload."""
    PROCESSING = "processing"  # Đang trích xuất text / gọi AI
    COMPLETED = "completed"    # Hoàn thành, quiz đã được tạo
    FAILED = "failed"          # Lỗi trong quá trình xử lý


class DocumentBase(BaseModel):
    """Fields cơ bản của Document (dùng chung)."""
    original_filename: str = Field(
        ...,  # ... = required, không có giá trị mặc định
        description="Tên file gốc user upload",
        examples=["bai_giang_python.pdf"],
    )
    file_type: FileType = Field(
        ...,
        description="Loại file (pdf, docx, txt)",
    )
    file_size_bytes: int = Field(
        ...,
        gt=0,  # gt = greater than → phải > 0
        description="Kích thước file tính bằng bytes",
    )


class DocumentInDB(DocumentBase):
    """
    Schema lưu trong MongoDB.
    
    Mở rộng từ DocumentBase, thêm các fields server tạo.
    MongoDB tự tạo _id (ObjectId), ta lưu dưới dạng string.
    """
    id: str = Field(
        ...,
        alias="_id",  # Map field "id" ↔ "_id" trong MongoDB
        description="MongoDB ObjectId dưới dạng string",
    )
    user_id: str | None = Field(
        default=None,
        description="ID của user upload (None nếu chưa có auth)",
    )
    extracted_text: str = Field(
        default="",
        description="Nội dung text đã trích xuất từ file",
    )
    text_length: int = Field(
        default=0,
        description="Độ dài text (để quick stats, không cần query text)",
    )
    upload_status: UploadStatus = Field(
        default=UploadStatus.PROCESSING,
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    model_config = {
        # Cho phép dùng cả field name (id) và alias (_id)
        "populate_by_name": True,
    }


class DocumentResponse(BaseModel):
    """
    Response trả về cho Frontend.
    
    KHÔNG chứa extracted_text (có thể rất lớn, không cần thiết).
    Chỉ trả metadata cần thiết.
    """
    id: str
    original_filename: str
    file_type: FileType
    file_size_bytes: int
    text_length: int
    upload_status: UploadStatus
    created_at: datetime
