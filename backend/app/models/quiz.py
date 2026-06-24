"""
Quiz & Question Models - Schema cho bộ câu hỏi trắc nghiệm
=============================================================

Thiết kế quan trọng:
- Quiz là "container" chứa metadata (tiêu đề, mô tả, difficulty)
- Questions được lưu riêng collection, liên kết qua quiz_id
  → Tại sao tách? Vì 1 quiz có thể 10-30 câu, nếu embed sẽ
    khó paginate, khó update từng câu, và document quá lớn.

- QuizAttempt lưu kết quả làm bài của user
  → Tách riêng để 1 quiz có thể làm nhiều lần
"""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


# ============================================
# QUESTION MODELS
# ============================================

class Option(BaseModel):
    """Một lựa chọn trong câu hỏi trắc nghiệm."""
    key: str = Field(
        ...,
        pattern=r"^[A-D]$",  # Chỉ chấp nhận A, B, C, D
        description="Ký hiệu đáp án (A/B/C/D)",
    )
    text: str = Field(
        ...,
        min_length=1,
        description="Nội dung đáp án",
    )


class QuestionBase(BaseModel):
    """Schema cơ bản của 1 câu hỏi."""
    question_text: str = Field(
        ...,
        min_length=10,  # Câu hỏi phải đủ dài
        description="Nội dung câu hỏi",
    )
    options: list[Option] = Field(
        ...,
        min_length=4,
        max_length=4,  # Luôn có đúng 4 đáp án
        description="Danh sách 4 đáp án A, B, C, D",
    )
    correct_answer: str = Field(
        ...,
        pattern=r"^[A-D]$",
        description="Đáp án đúng (A/B/C/D)",
    )
    explanation: str = Field(
        default="",
        description="Giải thích tại sao đáp án đúng",
    )


class QuestionInDB(QuestionBase):
    """Question schema trong MongoDB."""
    id: str = Field(..., alias="_id")
    quiz_id: str = Field(..., description="ID của quiz chứa câu hỏi này")
    order: int = Field(..., ge=1, description="Thứ tự câu hỏi trong quiz")

    model_config = {"populate_by_name": True}


class QuestionResponse(BaseModel):
    """
    Question trả về cho Frontend khi LÀM BÀI.
    
    QUAN TRỌNG: KHÔNG chứa correct_answer và explanation!
    → Tránh user xem đáp án trong DevTools / Network tab
    → Chỉ trả correct_answer sau khi submit bài
    """
    id: str
    question_text: str
    options: list[Option]
    order: int


class QuestionWithAnswer(QuestionResponse):
    """
    Question trả về SAU KHI submit bài (có đáp án + giải thích).
    Kế thừa QuestionResponse, thêm fields bí mật.
    """
    correct_answer: str
    explanation: str


# ============================================
# QUIZ MODELS
# ============================================

class Difficulty(str, Enum):
    """Mức độ khó của quiz."""
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    MIXED = "mixed"  # Pha trộn các mức độ


class QuizInDB(BaseModel):
    """Quiz schema trong MongoDB."""
    id: str = Field(..., alias="_id")
    document_id: str = Field(..., description="ID tài liệu gốc")
    user_id: str | None = Field(default=None)
    title: str = Field(..., description="Tiêu đề quiz (AI tạo)")
    description: str = Field(default="", description="Mô tả (AI tạo)")
    total_questions: int = Field(..., ge=1)
    difficulty: Difficulty = Field(default=Difficulty.MIXED)
    language: str = Field(default="vi")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    model_config = {"populate_by_name": True}


class QuizResponse(BaseModel):
    """Quiz response cho Frontend (kèm danh sách câu hỏi)."""
    id: str
    title: str
    description: str
    total_questions: int
    difficulty: Difficulty
    created_at: datetime
    questions: list[QuestionResponse] = Field(default_factory=list)


class QuizSummaryResponse(BaseModel):
    """Quiz tóm tắt cho danh sách (không kèm câu hỏi)."""
    id: str
    title: str
    description: str
    total_questions: int
    difficulty: Difficulty
    created_at: datetime


# ============================================
# QUIZ ATTEMPT MODELS (Kết quả làm bài)
# ============================================

class AnswerSubmission(BaseModel):
    """1 câu trả lời user submit."""
    question_id: str
    selected: str = Field(..., pattern=r"^[A-D]$")


class QuizSubmitRequest(BaseModel):
    """Request body khi user nộp bài."""
    answers: list[AnswerSubmission] = Field(
        ...,
        min_length=1,
        description="Danh sách câu trả lời",
    )


class AnswerResult(BaseModel):
    """Kết quả 1 câu sau khi chấm."""
    question_id: str
    selected: str         # User chọn gì
    correct_answer: str   # Đáp án đúng
    is_correct: bool      # Đúng hay sai
    explanation: str      # Giải thích


class QuizSubmitResponse(BaseModel):
    """Response sau khi chấm bài."""
    score: int            # Số câu đúng
    total: int            # Tổng số câu
    percentage: float     # Phần trăm
    results: list[AnswerResult]  # Chi tiết từng câu
