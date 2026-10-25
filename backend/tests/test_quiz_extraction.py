from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.quiz_service import QuizService


def _question(number: int) -> dict:
    return {
        "question_text": f"Question {number}?",
        "options": [
            {"key": "A", "text": "Option A"},
            {"key": "B", "text": "Option B"},
            {"key": "C", "text": "Option C"},
            {"key": "D", "text": "Option D"},
        ],
        "correct_answer": "A",
        "explanation": "Explanation",
    }


@pytest.mark.asyncio
async def test_extract_keeps_all_questions_in_one_subject_quiz():
    service = QuizService(db=MagicMock(), gemini_service=MagicMock())
    source_text = "Source material " * 20
    questions = [_question(1), _question(2)]

    service.extractor.extract = MagicMock(return_value=source_text)
    service.extractor.validate_extracted_text = MagicMock(return_value=(True, ""))
    service._save_document = AsyncMock(return_value="document-id")
    service._save_quiz_and_questions = AsyncMock(
        return_value=("quiz-id", ["question-1", "question-2"])
    )
    service._build_response = AsyncMock(return_value={"quiz": {"id": "quiz-id"}})
    service._update_document_status = AsyncMock()
    service.gemini.extract_metadata = AsyncMock(return_value={"title": "All questions"})

    with (
        patch("app.utils.question_parser.parse_questions_from_text", return_value=questions),
        patch("app.utils.question_parser.deduplicate_questions", return_value=questions),
    ):
        await service.upload_and_generate_quiz(
            file_bytes=b"file",
            filename="questions.txt",
            file_type="txt",
            mode="extract",
        )

    assert service._save_quiz_and_questions.await_count == 1
    saved_quiz = service._save_quiz_and_questions.await_args.kwargs["quiz_data"]
    assert saved_quiz["questions"] == questions
    assert "chapter" not in saved_quiz


@pytest.mark.asyncio
async def test_upload_metadata_overrides_ai_metadata():
    service = QuizService(db=MagicMock(), gemini_service=MagicMock())
    source_text = "Source material " * 20
    questions = [_question(1)]

    service.extractor.extract = MagicMock(return_value=source_text)
    service.extractor.validate_extracted_text = MagicMock(return_value=(True, ""))
    service._save_document = AsyncMock(return_value="document-id")
    service._save_quiz_and_questions = AsyncMock(return_value=("quiz-id", ["question-1"]))
    service._build_response = AsyncMock(return_value={"quiz": {"id": "quiz-id"}})
    service._update_document_status = AsyncMock()
    service.gemini.extract_metadata = AsyncMock(return_value={
        "title": "AI title",
        "subject": "AI subject",
        "exam_type": "AI exam",
        "school": "AI school",
    })

    with (
        patch("app.utils.question_parser.parse_questions_from_text", return_value=questions),
        patch("app.utils.question_parser.deduplicate_questions", return_value=questions),
    ):
        await service.upload_and_generate_quiz(
            file_bytes=b"file",
            filename="questions.txt",
            file_type="txt",
            mode="extract",
            subject="Toán học",
            exam_type="Cuối kỳ",
            school="Trường ĐH Y Hà Nội",
        )

    saved_args = service._save_quiz_and_questions.await_args.kwargs
    assert saved_args["subject"] == "Toán học"
    assert saved_args["exam_type"] == "Cuối kỳ"
    assert saved_args["school"] == "Trường ĐH Y Hà Nội"
