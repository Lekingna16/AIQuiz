"""
Quiz Service - Business logic orchestrator cho quiz generation pipeline
========================================================================

Đây là "brain" của backend, kết nối tất cả services lại:
1. TextExtractor: extract text từ file
2. TextProcessing: preprocess & truncate text
3. GeminiService: gọi AI sinh câu hỏi
4. MongoDB: lưu document, quiz, questions

Tại sao tách ra Service layer thay vì viết hết trong Router?
1. Separation of Concerns:
   - Router: nhận request, validate input, trả response
   - Service: business logic (extract → preprocess → AI → save)
   - Nếu đổi Router (FastAPI → Flask), logic không đổi

2. Testability:
   - Mock GeminiService → test pipeline không cần API key
   - Mock Database → test logic không cần MongoDB

3. Reusability:
   - Nếu thêm CLI tool, cũng dùng lại QuizService
   - Background job (Celery) cũng gọi QuizService

Flow chi tiết:
  upload_and_generate_quiz()
  ├── extract text (TextExtractor)
  ├── validate text (min length)
  ├── preprocess text (remove noise, truncate)
  ├── save document to MongoDB (status: processing)
  ├── call Gemini AI (with retry)
  ├── save quiz + questions to MongoDB
  ├── update document status (completed/failed)
  └── return quiz response
"""

import asyncio
import atexit
import logging
import json
import re
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from datetime import datetime, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import get_settings
from app.services.ocr_service import LocalOCREngine
from app.services.text_extractor import (
    ExtractionResult,
    TextExtractor,
    extract_document_worker,
)
from app.services.ai_service import (
    DeepSeekService,
    DeepSeekServiceError,
    QuizGenerationError,
    APIConnectionError,
)
from app.utils.text_processing import preprocess_text

logger = logging.getLogger(__name__)

# Tách trích xuất PDF/DOCX + C++ Tesseract sang tiến trình riêng để KHÔNG giữ
# Python GIL của tiến trình Uvicorn, giúp các API polling (/jobs/{id}) luôn phản hồi tức thì.
_ocr_process_pool: ProcessPoolExecutor | None = None


def _get_ocr_process_pool() -> ProcessPoolExecutor:
    global _ocr_process_pool
    if _ocr_process_pool is None:
        _ocr_process_pool = ProcessPoolExecutor(max_workers=1)
    return _ocr_process_pool


def _shutdown_ocr_process_pool() -> None:
    global _ocr_process_pool
    if _ocr_process_pool is not None:
        try:
            _ocr_process_pool.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        _ocr_process_pool = None


atexit.register(_shutdown_ocr_process_pool)


class QuizService:
    """
    Orchestrator cho quiz generation pipeline.

    Usage:
        service = QuizService(db, gemini_service)
        result = await service.upload_and_generate_quiz(
            file_bytes=..., filename="test.pdf", file_type="pdf",
            num_questions=10, difficulty="mixed", language="vi"
        )
    """

    def __init__(self, db: AsyncIOMotorDatabase, gemini_service: DeepSeekService):
        self.db = db
        self.gemini = gemini_service
        settings = get_settings()
        self.ocr_gemini_fallback = getattr(settings, "OCR_GEMINI_FALLBACK", True)
        self.extractor = TextExtractor(
            ocr=LocalOCREngine.from_settings(settings),
            ocr_max_pages=getattr(settings, "OCR_MAX_PAGES", None),
        )

    async def _run_extractor_isolated(self, file_bytes: bytes, file_type: str) -> ExtractionResult:
        """
        Chạy trích xuất tài liệu trong ``ProcessPoolExecutor`` đối với PDF/DOCX có OCR
        để C++ Tesseract không giữ GIL làm nghẽn FastAPI event loop.
        Tự động dùng ``asyncio.to_thread`` cho file TXT hoặc khi unit test mock extractor.
        """
        can_use_subprocess = (
            file_type.lower().strip() in {"pdf", "docx"}
            and type(self.extractor) is TextExtractor
            and "extract_document" not in self.extractor.__dict__
            and type(self.extractor.ocr) is LocalOCREngine
            and self.extractor.ocr.is_available
        )
        if can_use_subprocess:
            loop = asyncio.get_running_loop()
            ocr_cfg = self.extractor.ocr
            try:
                return await loop.run_in_executor(
                    _get_ocr_process_pool(),
                    extract_document_worker,
                    file_bytes,
                    file_type,
                    ocr_cfg.requested_languages,
                    ocr_cfg.dpi,
                    ocr_cfg._tessdata_hint,
                    ocr_cfg.enabled,
                    self.extractor.OCR_MAX_PAGES,
                )
            except (BrokenProcessPool, PermissionError, OSError) as exc:
                logger.warning("OCR subprocess unavailable (%s); falling back to thread", exc)
                _shutdown_ocr_process_pool()

        return await asyncio.to_thread(self.extractor.extract_document, file_bytes, file_type)

    async def _extract_text(self, file_bytes: bytes, file_type: str, filename: str) -> str:
        """
        Trích xuất text (kèm OCR) cho mọi loại file.

        1. Đọc file + OCR cục bộ (chạy trong process riêng để tránh giữ GIL
           gây timeout cho các request polling trạng thái job)
        2. Ảnh chưa đọc được (server thiếu dữ liệu OCR cục bộ) → Gemini Vision
        3. Ghép + clean text
        """
        result = await self._run_extractor_isolated(file_bytes, file_type)

        pending = result.pending_segments
        if pending:
            limit = self.extractor.SCANNED_PDF_MAX_PAGES
            transcribe = getattr(self.gemini, "transcribe_images", None)
            if not self.ocr_gemini_fallback or transcribe is None:
                logger.warning(
                    "%s: %d image(s) need OCR but no OCR engine is available",
                    filename, len(pending),
                )
            else:
                if len(pending) > limit:
                    logger.warning(
                        "%s: %d images need OCR, only the first %d are sent to Gemini",
                        filename, len(pending), limit,
                    )
                try:
                    texts = await transcribe([segment.image for segment in pending[:limit]])
                    result.resolve_pending(texts)
                except Exception as exc:
                    logger.warning("%s: Gemini OCR fallback failed: %s", filename, exc)

        if result.used_ocr:
            logger.info(
                "%s: OCR used (pages=%s, images=%d)",
                filename, result.ocr_pages, result.ocr_images,
            )
        return self.extractor.finalize_text(result)

    async def upload_and_generate_quiz(
        self,
        file_bytes: bytes,
        filename: str,
        file_type: str,
        num_questions: int = 10,
        difficulty: str = "mixed",
        language: str = "vi",
        mode: str = "generate",
        user_id: str | None = None,
        subject: str | None = None,
        major: str | None = None,
        exam_type: str | None = None,
        school: str | None = None,
        is_public: bool = False,
    ) -> dict:
        """
        Pipeline hoàn chỉnh: File → Text → AI → Quiz.

        Args:
            file_bytes: Binary content của file upload
            filename: Tên file gốc
            file_type: Loại file (pdf/docx/txt)
            num_questions: Số câu hỏi cần tạo
            difficulty: Mức độ khó
            language: Ngôn ngữ output
            user_id: ID user (None nếu chưa có auth)

        Returns:
            Dict chứa document_id và quiz data

        Raises:
            ValueError: File rỗng, text quá ngắn
            GeminiServiceError: Lỗi AI
        """
        document_id = None

        try:
            # =====================
            # Step 1: Extract text
            # =====================
            logger.info(f"Extracting text from: {filename} ({file_type})")
            extracted_text = await self._extract_text(file_bytes, file_type, filename)

            if not extracted_text.strip() and file_type.lower() in {"pdf", "docx"}:
                raise ValueError(
                    "Không đọc được chữ từ tài liệu (có thể là bản scan/ảnh chụp). "
                    "Máy chủ chưa có dữ liệu OCR tiếng Việt và Gemini Vision không khả dụng. "
                    "Vui lòng thử lại sau hoặc tải lên file có thể bôi đen/copy chữ."
                )

            # Validate text content
            is_valid, error_msg = self.extractor.validate_extracted_text(extracted_text)
            if not is_valid:
                raise ValueError(error_msg)

            logger.info(
                f"Extracted {len(extracted_text)} chars from {filename}"
            )

            # =====================
            # Step 2: Save document to DB (status: processing)
            # =====================
            document_id = await self._save_document(
                filename=filename,
                file_type=file_type,
                file_size=len(file_bytes),
                extracted_text=extracted_text,
                user_id=user_id,
            )
            logger.info(f"Document saved: {document_id}")

            # =====================
            # Step 3: Preprocess text
            # =====================
            processed_text = preprocess_text(extracted_text)
            logger.info(
                f"Text preprocessed: {len(extracted_text)} → {len(processed_text)} chars"
            )

            # =====================
            # Step 4: Generate/Extract quiz with AI
            # =====================
            logger.info(
                f"Processing {num_questions} questions "
                f"(difficulty={difficulty}, lang={language}, mode={mode})"
            )
            
            if mode == "extract":
                # =============================================
                # Trích xuất bằng REGEX
                # → Nhanh (~50ms), chính xác, lấy hết 100% câu
                # Ưu tiên đáp án: inline > tô sẵn > bảng > AI
                # =============================================
                from app.utils.question_parser import (
                    parse_questions_from_text,
                    deduplicate_questions,
                )

                logger.info("Using programmatic parser for extraction")
                raw_questions = parse_questions_from_text(extracted_text)
                logger.info(f"Parsed {len(raw_questions)} raw questions")

                unique_questions = deduplicate_questions(raw_questions)
                logger.info(f"After dedup: {len(unique_questions)} unique questions")

                if not unique_questions:
                    raise ValueError(
                        "Không tìm thấy câu hỏi trắc nghiệm theo định dạng hỗ trợ trong tài liệu."
                    )
                else:
                    # Thống kê đáp án đã có từ parser (inline + tô sẵn + bảng)
                    has_answer = [q for q in unique_questions if q.get("correct_answer")]
                    unsolved_questions = [q for q in unique_questions if not q.get("correct_answer")]
                    
                    logger.info(
                        f"Answer sources: {len(has_answer)} từ file "
                        f"(inline/tô sẵn/bảng đáp án), "
                        f"{len(unsolved_questions)} cần AI giải"
                    )

                    # Chỉ gọi AI cho những câu thực sự thiếu đáp án (hoặc cần sửa lỗi OCR nặng)
                    needs_ocr_repair = self.extractor.has_damaged_ocr_text(extracted_text)
                    questions_to_process = unique_questions if needs_ocr_repair else unsolved_questions
                    ai_solved = 0
                    if questions_to_process:
                        logger.info(
                            f"Calling AI answer solver for {len(questions_to_process)} questions "
                            f"(repair_ocr={needs_ocr_repair})..."
                        )
                        solved_results = await self._solve_missing_answers_with_ai(
                            questions_to_process,
                            repair_ocr=needs_ocr_repair,
                        )
                        
                        # Merge solved answers back bằng INDEX (không dùng text matching)
                        for i, q in enumerate(questions_to_process):
                            solved_q = solved_results[i] if i < len(solved_results) else None
                            if solved_q and solved_q is not None:
                                if needs_ocr_repair:
                                    repaired_text = (solved_q.get("question_text") or "").strip()
                                    repaired_opts = solved_q.get("options")
                                    if repaired_text and self._has_complete_options(repaired_opts):
                                        q["question_text"] = repaired_text
                                        q["options"] = repaired_opts
                                if not q.get("correct_answer"):
                                    answer = solved_q.get("correct_answer", "")
                                    explanation = solved_q.get("explanation", "")
                                    if answer and answer.upper() in {"A", "B", "C", "D"}:
                                        q["correct_answer"] = answer.upper()
                                        q["explanation"] = explanation
                                        ai_solved += 1
                        
                        logger.info(f"AI solved {ai_solved}/{len(questions_to_process)} questions")

                    # Safety fallback: đảm bảo KHÔNG CÓ câu nào thiếu đáp án
                    still_missing = [q for q in unique_questions if not q.get("correct_answer")]
                    if still_missing:
                        logger.warning(
                            f"{len(still_missing)} questions still missing answers after AI. "
                            f"Assigning 'A' as default."
                        )
                        for q in still_missing:
                            q["correct_answer"] = "A"
                            q["explanation"] = (
                                "⚠️ Đáp án được gán mặc định (A) vì hệ thống không thể "
                                "xác định đáp án đúng từ file gốc. "
                                "Vui lòng kiểm tra lại."
                            )

                    # Tạo title/description tự động
                    desc_parts = [
                        f"Trích xuất {len(unique_questions)} câu hỏi duy nhất",
                        f"(lọc từ {len(raw_questions)} câu gốc)",
                    ]
                    if has_answer and not unsolved_questions:
                        desc_parts.append("• Tất cả đáp án từ file gốc")
                    elif unsolved_questions:
                        if still_missing:
                            desc_parts.append(
                                f"• {len(has_answer)} đáp án từ file, "
                                f"{len(still_missing)} đáp án mặc định (cần kiểm tra)"
                            )
                        else:
                            desc_parts.append(
                                f"• {len(has_answer)} đáp án từ file"
                            )
                        
                    base_title = f"Trích xuất từ {filename}"
                    
                    # Keep every extracted and de-duplicated question in one
                    # quiz. Subject metadata is retained, while section
                    # grouping is intentionally not stored or exposed.
                    quiz_data_list = [{
                        "title": base_title,
                        "description": " ".join(desc_parts),
                        "subject": subject,
                        "exam_type": exam_type,
                        "school": school,
                        "questions": unique_questions,
                    }]
            else:
                # Luôn dùng AI cho generate
                quiz_data = await self.gemini.generate_quiz(
                    text=processed_text,
                    num_questions=num_questions,
                    difficulty=difficulty,
                    language=language,
                    mode=mode,
                )
                quiz_data_list = [quiz_data]

            # =====================
            # Step 5: Save quiz + questions to DB
            # =====================
            saved_quiz_ids = []
            for q_data in quiz_data_list:
                qid, q_ids = await self._save_quiz_and_questions(
                    document_id=document_id,
                    quiz_data=q_data,
                    difficulty=difficulty,
                    language=language,
                    user_id=user_id,
                    subject=subject,
                    major=major,
                    exam_type=exam_type,
                    school=school,
                    is_public=True, # Tự động public và approved
                )
                saved_quiz_ids.append(qid)
                logger.info(f"Quiz saved: {qid} with {len(q_ids)} questions")

            quiz_id = saved_quiz_ids[0] if saved_quiz_ids else None

            # =====================
            # Step 6: Update document status → completed
            # =====================
            await self._update_document_status(document_id, "completed")

            # =====================
            # Step 7: Build response
            # =====================
            if not quiz_id:
                raise ValueError("Không tìm thấy câu hỏi hợp lệ để tạo quiz")
            response = await self._build_response(quiz_id, document_id)
            if len(saved_quiz_ids) > 1:
                response["all_quiz_ids"] = saved_quiz_ids
            return response

        except Exception as e:
            # Update document status → failed
            if document_id:
                await self._update_document_status(document_id, "failed")
            logger.error(f"Quiz generation failed for {filename}: {str(e)}")
            raise

    # ============================================
    # Database operations
    # ============================================

    async def _save_document(
        self,
        filename: str,
        file_type: str,
        file_size: int,
        extracted_text: str,
        user_id: str | None,
    ) -> str:
        """Lưu document metadata vào MongoDB. Returns document_id."""
        doc = {
            "original_filename": filename,
            "file_type": file_type,
            "file_size_bytes": file_size,
            "extracted_text": extracted_text,
            "text_length": len(extracted_text),
            "upload_status": "processing",
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc),
        }
        result = await self.db.documents.insert_one(doc)
        return str(result.inserted_id)

    @staticmethod
    def _has_complete_options(options: list[dict]) -> bool:
        """Validate a repaired option set before replacing parsed source text."""
        if not isinstance(options, list) or len(options) != 4:
            return False
        keys = {option.get("key") for option in options if isinstance(option, dict)}
        return keys == {"A", "B", "C", "D"} and all(
            option.get("text", "").strip() for option in options
        )

    async def _solve_missing_answers_with_ai(
        self,
        questions: list[dict],
        repair_ocr: bool = False,
    ) -> list[dict]:
        """
        Gửi các câu hỏi thiếu đáp án lên AI để giải.
        Chỉ dùng AI ở bước trả lời các câu đã được parser code tách ra.
        
        Returns: list of dicts with 'correct_answer' and 'explanation' 
                 IN THE SAME ORDER as input questions.
        """
        import asyncio
        
        # Returning corrected text and choices has a larger JSON payload than
        # answer-only solving, so use smaller batches to avoid truncation.
        BATCH_SIZE = 60 if not repair_ocr else 20
        # Khởi tạo mảng kết quả với cùng kích thước, mặc định rỗng
        all_solved = [None] * len(questions)
        
        # Chia thành các batch, giữ track index gốc
        batches = []
        for i in range(0, len(questions), BATCH_SIZE):
            batch_items = []
            for j in range(i, min(i + BATCH_SIZE, len(questions))):
                batch_items.append((j, questions[j]))
            batches.append(batch_items)
        
        logger.info(f"Splitting {len(questions)} questions into {len(batches)} batches for concurrent solving")
        
        async def solve_batch(batch_idx, batch):
            # Tạo payload rút gọn, đánh số thứ tự rõ ràng
            payload = []
            for idx_in_batch, (original_idx, q) in enumerate(batch):
                payload.append({
                    "index": idx_in_batch + 1,  # 1-based cho AI dễ hiểu
                    "question_text": q["question_text"],
                    "options": q["options"]
                })
            json_payload = json.dumps(payload, ensure_ascii=False)
            
            repair_rules = ""
            repair_output_fields = ""
            if repair_ocr:
                repair_rules = """
6. The source was read from a damaged Vietnamese OCR layer. Correct obvious OCR
   character errors in question and option text, without changing its meaning.
7. Return `question_text` and exactly four non-empty `options` keyed A, B, C,
   D for every item. Never change the question order or merge questions.
"""
                repair_output_fields = '''
      "question_text": "Corrected question text",
      "options": [
        {"key": "A", "text": "..."},
        {"key": "B", "text": "..."},
        {"key": "C", "text": "..."},
        {"key": "D", "text": "..."}
      ],'''

            system_prompt = f"""You are an expert educational AI.
Your task is to SOLVE a given list of {len(batch)} multiple-choice questions.

## TASK
I will provide you with a JSON array of {len(batch)} questions (each with an "index" field) and their options.
For EACH question, you MUST determine the correct answer based on your knowledge.

## CRITICAL RULES
1. You MUST return EXACTLY {len(batch)} answers, one for each input question.
2. You MUST preserve the "index" field from the input to match answers back.
3. Determine the correct answer (must be one of: A, B, C, D).
4. Provide a brief explanation for why it is correct.
5. Return answers IN THE SAME ORDER as the input.
{repair_rules}

## OUTPUT FORMAT
Return ONLY a valid JSON object matching this structure:
{{
  "questions": [
    {{
      "index": 1,
{repair_output_fields}
      "correct_answer": "A",
      "explanation": "..."
    }}
  ]
}}
"""
            try:
                response_text = await self.gemini._call_api_with_retry(
                    system_prompt, json_payload, skip_validation=True
                )
                
                # Parse JSON trực tiếp (KHÔNG dùng _parse_response vì nó 
                # validate full quiz structure mà solve response không có)
                cleaned = re.sub(r"```json\s*", "", response_text)
                cleaned = re.sub(r"\s*```", "", cleaned).strip()
                solved_data = json.loads(cleaned)
                batch_solved = solved_data.get("questions", [])
                
                # Map kết quả về vị trí gốc bằng index
                for solved_q in batch_solved:
                    # Lấy index từ AI response (1-based) → convert về 0-based
                    raw_index = solved_q.get("index")
                    try:
                        ai_index = int(raw_index) if raw_index is not None else None
                    except (TypeError, ValueError):
                        ai_index = None
                    if ai_index is not None and 1 <= ai_index <= len(batch):
                        original_idx = batch[ai_index - 1][0]  # index gốc trong questions[]
                        all_solved[original_idx] = solved_q
                
                # Fallback: nếu không có index, map theo thứ tự xuất hiện
                items_without_index = [s for s in batch_solved if s.get("index") is None]
                if items_without_index and len(items_without_index) == len(batch):
                    for i, (original_idx, _) in enumerate(batch):
                        if i < len(batch_solved):
                            all_solved[original_idx] = batch_solved[i]
                
                logger.info(f"Batch {batch_idx + 1}: solved {len(batch_solved)} questions")
            except Exception as e:
                logger.error(f"Batch {batch_idx + 1} failed: {e}")

        # One request at a time prevents a large document from consuming an
        # entire provider rate limit in a few seconds.
        sem = asyncio.Semaphore(2)
        async def solve_batch_with_sem(batch_idx, batch):
            async with sem:
                await solve_batch(batch_idx, batch)

        tasks = [solve_batch_with_sem(idx, b) for idx, b in enumerate(batches)]
        await asyncio.gather(*tasks)
        
        return all_solved

    async def _save_quiz_and_questions(
        self,
        document_id: str,
        quiz_data: dict,
        difficulty: str,
        language: str,
        user_id: str | None,
        subject: str | None,
        major: str | None,
        exam_type: str | None,
        school: str | None,
        is_public: bool,
    ) -> tuple[str, list[str]]:
        """
        Lưu quiz và questions vào MongoDB.

        Returns: (quiz_id, list of question_ids)
        """
        # Save quiz
        quiz_doc = {
            "document_id": document_id,
            "user_id": user_id,
            "title": quiz_data.get("title", "Untitled Quiz"),
            "description": quiz_data.get("description", ""),
            "total_questions": len(quiz_data["questions"]),
            "difficulty": difficulty,
            "language": language,
            "subject": subject,
            "major": major,
            "exam_type": exam_type,
            "school": school,
            "is_public": is_public,
            "is_approved": True, # Mặc định approved
            "created_at": datetime.now(timezone.utc),
        }
        quiz_result = await self.db.quizzes.insert_one(quiz_doc)
        quiz_id = str(quiz_result.inserted_id)

        # Save questions (bulk insert cho performance)
        question_docs = []
        for i, q in enumerate(quiz_data["questions"]):
            question_docs.append({
                "quiz_id": quiz_id,
                "question_text": q["question_text"],
                "options": q["options"],
                "correct_answer": q["correct_answer"],
                "explanation": q.get("explanation", ""),
                "order": i + 1,
            })

        if question_docs:
            result = await self.db.questions.insert_many(question_docs)
            question_ids = [str(qid) for qid in result.inserted_ids]
        else:
            question_ids = []

        return quiz_id, question_ids

    async def _update_document_status(
        self, document_id: str, status: str
    ) -> None:
        """Update upload_status của document."""
        try:
            await self.db.documents.update_one(
                {"_id": ObjectId(document_id)},
                {"$set": {"upload_status": status}},
            )
        except Exception as e:
            logger.error(
                f"Failed to update document {document_id} status: {e}"
            )

    async def _build_response(
        self, quiz_id: str, document_id: str
    ) -> dict:
        """
        Build response dict từ saved quiz data.

        Trả về quiz với questions (KHÔNG kèm correct_answer)
        để frontend render quiz ngay sau upload.
        """
        # Fetch quiz
        quiz = await self.db.quizzes.find_one({"_id": ObjectId(quiz_id)})

        # Fetch questions (sorted by order)
        questions_cursor = self.db.questions.find(
            {"quiz_id": quiz_id}
        ).sort("order", 1)
        questions = await questions_cursor.to_list(length=None)

        # Build response (ẩn correct_answer)
        quiz_response = {
            "document_id": document_id,
            "quiz": {
                "id": str(quiz["_id"]),
                "title": quiz["title"],
                "description": quiz.get("description", ""),
                "total_questions": quiz["total_questions"],
                "difficulty": quiz["difficulty"],
                "major": quiz.get("major"),
                "created_at": quiz["created_at"].isoformat(),
                "questions": [
                    {
                        "id": str(q["_id"]),
                        "question_text": q["question_text"],
                        "options": q["options"],
                        "order": q["order"],
                    }
                    for q in questions
                ],
            },
        }

        return quiz_response
