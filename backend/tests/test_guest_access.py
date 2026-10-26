from io import BytesIO
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import BackgroundTasks, UploadFile, HTTPException, Response

from app.models.quiz import Difficulty
from app.controllers import documents, quizzes


@pytest.fixture(autouse=True)
def isolated_upload_capacity(monkeypatch):
    monkeypatch.setattr(documents, "_upload_reservations", set())


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
async def test_home_data_combines_quizzes_and_filters_with_public_cache():
    db = MagicMock()
    db.quizzes.distinct = AsyncMock(return_value=["Vi sinh", "Dược lý", None])
    cursor = db.quizzes.find.return_value.sort.return_value.limit.return_value
    cursor.to_list = AsyncMock(return_value=[{
        "_id": documents.ObjectId("64b64b64b64b64b64b64b64b"),
        "title": "Quiz vi sinh",
        "description": "Ôn tập",
        "total_questions": 20,
        "difficulty": "mixed",
        "subject": "Vi sinh",
        "created_at": datetime(2026, 10, 27, tzinfo=timezone.utc),
    }])
    response = Response()

    result = await quizzes.get_home_page_data(response=response, limit=20, db=db)

    assert result["quizzes"][0]["title"] == "Quiz vi sinh"
    assert result["filters"]["subjects"] == ["Dược lý", "Vi sinh"]
    assert "stale-while-revalidate" in response.headers["cache-control"]
    db.quizzes.find.assert_called_once_with(
        {"is_public": True, "is_approved": True},
        quizzes.QUIZ_SUMMARY_FIELDS,
    )


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
    assert updates[-1]["status"] == "completed"
    assert updates[-1]["quiz_id"] == "quiz-id"


async def submit_upload(file, db):
    return await documents.upload_document(
        background_tasks=BackgroundTasks(), file=file, num_questions=5,
        difficulty=Difficulty.MIXED, language="vi", mode="extract", is_public=True,
        subject="Y khoa", major="Y khoa", exam_type="Cuối kỳ", current_user=None, db=db,
    )


@pytest.mark.asyncio
async def test_busy_upload_is_rejected_before_reading_into_memory(monkeypatch):
    monkeypatch.setattr(documents, "get_settings", lambda: SimpleNamespace(MAX_FILE_SIZE_BYTES=1024))
    documents._upload_reservations.update([documents.ObjectId(), documents.ObjectId()])
    file = UploadFile(filename="test.txt", file=BytesIO(b"text"))
    file.read = AsyncMock()
    with pytest.raises(HTTPException) as error:
        await submit_upload(file, MagicMock())
    assert error.value.status_code == 429
    assert error.value.headers["Retry-After"] == "60"
    file.read.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_upload_releases_capacity(monkeypatch):
    monkeypatch.setattr(documents, "get_settings", lambda: SimpleNamespace(MAX_FILE_SIZE_BYTES=1024))
    with pytest.raises(HTTPException):
        await submit_upload(UploadFile(filename="empty.txt", file=BytesIO(b"")), MagicMock())
    assert not documents._upload_reservations


@pytest.mark.asyncio
async def test_background_failure_releases_capacity(monkeypatch):
    token = documents.ObjectId()
    documents._upload_reservations.add(token)
    monkeypatch.setattr(documents, "_run_upload_job", AsyncMock(side_effect=RuntimeError("DB unavailable")))
    with pytest.raises(RuntimeError):
        await documents._process_upload_job(reservation=token)
    assert not documents._upload_reservations
