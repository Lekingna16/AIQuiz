from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.quiz_service import QuizService
from app.services.text_extractor import ExtractionResult, TextSegment


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

    service.extractor.extract_document = MagicMock(
        return_value=ExtractionResult.from_text(source_text)
    )
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

    service.extractor.extract_document = MagicMock(
        return_value=ExtractionResult.from_text(source_text)
    )
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


@pytest.mark.asyncio
async def test_quiz_service_never_sends_pending_ocr_segments_to_ai():
    gemini_mock = MagicMock()
    gemini_mock.transcribe_images = AsyncMock()
    service = QuizService(db=MagicMock(), gemini_service=gemini_mock)

    extraction = ExtractionResult(
        file_type="pdf",
        segments=[
            TextSegment(text="Câu 1: Nội dung chữ gốc trên trang PDF?"),
            TextSegment(source="pending", image=b"\xff\xd8fake-jpeg", label="page 1 image 1"),
        ],
    )
    service.extractor.extract_document = MagicMock(return_value=extraction)

    final_text = await service._extract_text(b"%PDF-fake", "pdf", "mixed_scan.pdf")
    gemini_mock.transcribe_images.assert_not_awaited()
    assert "Câu 1: Nội dung chữ gốc" in final_text
    assert "Câu 2:" not in final_text


@pytest.mark.asyncio
async def test_quiz_service_uses_gemini_vision_for_scan_only_pdf():
    gemini_mock = MagicMock()
    service = QuizService(db=MagicMock(), gemini_service=gemini_mock)
    service.extractor.is_scan_only_pdf = MagicMock(return_value=True)
    service._read_scan_pdf = AsyncMock(
        return_value="Câu 1: Nội dung scan?\nA. Một\nB. Hai\nC. Ba\nD. Bốn"
    )
    service._run_extractor_isolated = AsyncMock()

    final_text = await service._extract_text(b"%PDF-fake", "pdf", "scan.pdf")

    service._read_scan_pdf.assert_awaited_once_with(b"%PDF-fake")
    service._run_extractor_isolated.assert_not_awaited()
    assert "Câu 1: Nội dung scan?" in final_text
    assert "D. Bốn" in final_text


@pytest.mark.asyncio
async def test_quiz_service_runs_real_pdf_ocr_via_subprocess_worker():
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=400)
    page.insert_text((72, 100), "Cau 1: Test subprocess extraction?\nA. One\nB. Two\nC. Three\nD. Four")
    pix = page.get_pixmap(dpi=180, alpha=False)
    doc.close()

    scan_doc = fitz.open()
    sp = scan_doc.new_page(width=595, height=400)
    sp.insert_image(sp.rect, stream=pix.tobytes("png"))
    pdf_bytes = scan_doc.tobytes()
    scan_doc.close()

    service = QuizService(db=MagicMock(), gemini_service=MagicMock())
    service.ai_vision_ocr = False
    text = await service._extract_text(pdf_bytes, "pdf", "scan_worker.pdf")
    assert "subprocess" in text.lower()
    assert "A." in text and "D." in text


@pytest.mark.asyncio
async def test_pdf_quota_failure_does_not_restart_local_ocr():
    from app.services.pdf_reader import PDFReadError

    service = QuizService(db=MagicMock(), gemini_service=MagicMock())
    service.ai_vision_ocr = True
    service.extractor.is_scan_only_pdf = MagicMock(return_value=True)
    service._read_scan_pdf = AsyncMock(side_effect=PDFReadError("quota"))
    service._run_extractor_isolated = AsyncMock()
    with pytest.raises(PDFReadError, match="quota"):
        await service._extract_text(b"pdf", "pdf", "scan.pdf")
    service._run_extractor_isolated.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider, pages_per_batch", [("deepseek", 1), ("gemini", 4)])
async def test_scan_reader_uses_explicit_ocr_provider(provider, pages_per_batch):
    import asyncio
    from types import SimpleNamespace

    service = QuizService(db=MagicMock(), gemini_service=MagicMock())
    service.settings = SimpleNamespace(
        AI_PROVIDER="gemini", OCR_PROVIDER=provider,
        DEEPSEEK_API_KEY="deepseek-test", DEEPSEEK_VISION_MODEL="deepseek-flash",
        GEMINI_API_KEY="gemini-test", GEMINI_MODEL="gemini-test-model",
    )
    batches = [(1, 1, b"page")]
    reader = MagicMock()
    reader.read = AsyncMock(return_value="Câu 1: Nội dung")
    loop = asyncio.get_running_loop()
    with (
        patch("app.services.quiz_service.DeepSeekPDFReader", return_value=reader) as deepseek,
        patch("app.services.quiz_service.GeminiPDFReader", return_value=reader) as gemini,
        patch("app.services.quiz_service._get_ocr_process_pool", return_value="pool"),
        patch.object(loop, "run_in_executor", new=AsyncMock(return_value=batches)) as prepare,
    ):
        assert await service._read_scan_pdf(b"pdf") == "Câu 1: Nội dung"
    assert prepare.await_args.args[-1] == pages_per_batch
    assert deepseek.call_count == (provider == "deepseek")
    assert gemini.call_count == (provider == "gemini")
    reader.read.assert_awaited_once_with(batches, service._progress)
