from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import BackgroundTasks, UploadFile

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
    settings = SimpleNamespace(
        DEEPSEEK_API_KEY="test-key",
        MAX_FILE_SIZE_BYTES=1024 * 1024,
    )

    monkeypatch.setattr(documents, "get_settings", lambda: settings)
    db = MagicMock()
    db.upload_jobs.insert_one = AsyncMock(
        return_value=SimpleNamespace(inserted_id="64b64b64b64b64b64b64b64b")
    )

    upload = UploadFile(filename="guest.txt", file=BytesIO(b"guest document"))
    result = await documents.upload_document(
        background_tasks=BackgroundTasks(),
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
        db=db,
    )

    assert result == {"job_id": "64b64b64b64b64b64b64b64b", "status": "queued"}
    db.upload_jobs.insert_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_background_upload_job_marks_quiz_as_completed(monkeypatch):
    db = MagicMock()
    db.upload_jobs.update_one = AsyncMock()
    service = MagicMock()

    monkeypatch.setattr(documents, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(documents, "_create_ai_service", lambda _: MagicMock())
    monkeypatch.setattr(documents, "QuizService", lambda **_: service)
    monkeypatch.setattr(
        documents,
        "_generate_in_available_slot",
        AsyncMock(return_value={"document_id": "document-id", "quiz": {"id": "quiz-id"}}),
    )

    await documents._process_upload_job(
        db=db,
        job_id=documents.ObjectId("64b64b64b64b64b64b64b64b"),
        file_bytes=b"test document",
        filename="test.txt",
        file_type="txt",
        options={},
    )

    updates = [call.args[1]["$set"] for call in db.upload_jobs.update_one.await_args_list]
    assert updates[0]["status"] == "processing"
    assert updates[-1]["status"] == "completed"
    assert updates[-1]["quiz_id"] == "quiz-id"
