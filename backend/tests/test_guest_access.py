from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import UploadFile

from app.models.quiz import Difficulty
from app.controllers import documents, quizzes


@pytest.mark.asyncio
async def test_upload_catalog_returns_major_specific_course_suggestions():
    filters = await quizzes.get_quiz_filters(include_catalog=True)

    assert filters["exam_types"] == ["Ôn tập", "Giữa kỳ", "Cuối kỳ"]
    assert "Y khoa" in filters["majors"]
    assert "Giải phẫu học" in filters["courses_by_major"]["Y khoa"]
    assert "An toàn thông tin" in filters["majors"]
    assert "Kiểm thử xâm nhập" in filters["courses_by_major"]["An toàn thông tin"]
    assert "Thiết kế đồ họa" in filters["majors"]
    assert len(filters["majors"]) >= 70


@pytest.mark.asyncio
async def test_guest_upload_accepts_a_custom_major(monkeypatch):
    service = MagicMock()
    service.upload_and_generate_quiz = AsyncMock(
        return_value={"document_id": "document-id", "quiz": {"id": "quiz-id"}}
    )
    settings = SimpleNamespace(
        DEEPSEEK_API_KEY="test-key",
        MAX_FILE_SIZE_BYTES=1024 * 1024,
    )

    monkeypatch.setattr(documents, "get_settings", lambda: settings)
    monkeypatch.setattr(documents, "DeepSeekService", lambda **_: MagicMock())
    monkeypatch.setattr(documents, "QuizService", lambda **_: service)

    upload = UploadFile(filename="guest.txt", file=BytesIO(b"guest document"))
    result = await documents.upload_document(
        file=upload,
        num_questions=5,
        difficulty=Difficulty.MIXED,
        language="vi",
        mode="generate",
        is_public=True,
        subject="Y học hàng không",
        major="Ngành liên ngành mới",
        exam_type="Cuối kỳ",
        current_user=None,
        db=MagicMock(),
    )

    assert result["quiz"]["id"] == "quiz-id"
    assert service.upload_and_generate_quiz.await_args.kwargs["user_id"] is None
    assert service.upload_and_generate_quiz.await_args.kwargs["subject"] == "Y học hàng không"
    assert service.upload_and_generate_quiz.await_args.kwargs["major"] == "Ngành liên ngành mới"
    assert service.upload_and_generate_quiz.await_args.kwargs["exam_type"] == "Cuối kỳ"
    assert service.upload_and_generate_quiz.await_args.kwargs["school"] is None
