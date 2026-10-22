from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import UploadFile

from app.models.quiz import Difficulty
from app.routers import documents


@pytest.mark.asyncio
async def test_guest_upload_creates_an_unowned_quiz(monkeypatch):
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
        current_user=None,
        db=MagicMock(),
    )

    assert result["quiz"]["id"] == "quiz-id"
    assert service.upload_and_generate_quiz.await_args.kwargs["user_id"] is None
