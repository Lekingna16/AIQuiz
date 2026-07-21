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

import logging
import json
import re
from datetime import datetime, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.text_extractor import TextExtractor
from app.services.ai_service import (
    DeepSeekService,
    DeepSeekServiceError,
    QuizGenerationError,
    APIConnectionError,
)
from app.utils.text_processing import preprocess_text

logger = logging.getLogger(__name__)


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
        self.extractor = TextExtractor()

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
        chapter: str | None = None,
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
            extracted_text = self.extractor.extract(file_bytes, file_type)

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
                    logger.warning("Không tìm thấy câu hỏi bằng Regex. Chuyển sang dùng AI (DeepSeek) để nhận diện format động (Fallback)...")
                    quiz_data = await self.gemini.generate_quiz(
                        text=processed_text,
                        num_questions=num_questions,
                        difficulty=difficulty,
                        language=language,
                        mode="extract",
                    )
                    quiz_data_list = [quiz_data]
                else:
                    # Thống kê đáp án đã có từ parser (inline + tô sẵn + bảng)
                    has_answer = [q for q in unique_questions if q.get("correct_answer")]
                    unsolved_questions = [q for q in unique_questions if not q.get("correct_answer")]
                    
                    logger.info(
                        f"Answer sources: {len(has_answer)} từ file "
                        f"(inline/tô sẵn/bảng đáp án), "
                        f"{len(unsolved_questions)} cần AI giải"
                    )

                    # Chỉ gọi AI cho những câu thực sự thiếu đáp án
                    ai_solved = 0
                    if unsolved_questions:
                        logger.info(f"Calling DeepSeek AI to solve {len(unsolved_questions)} questions...")
                        solved_results = await self._solve_missing_answers_with_ai(unsolved_questions)
                        
                        # Merge solved answers back bằng INDEX (không dùng text matching)
                        for i, q in enumerate(unsolved_questions):
                            solved_q = solved_results[i] if i < len(solved_results) else None
                            if solved_q and solved_q is not None:
                                answer = solved_q.get("correct_answer", "")
                                explanation = solved_q.get("explanation", "")
                                if answer and answer.upper() in {"A", "B", "C", "D"}:
                                    q["correct_answer"] = answer.upper()
                                    q["explanation"] = explanation
                                    ai_solved += 1
                        
                        logger.info(f"AI solved {ai_solved}/{len(unsolved_questions)} questions")

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
                                "xác định đáp án đúng từ file gốc hoặc AI. "
                                "Vui lòng kiểm tra lại."
                            )

                    metadata = await self.gemini.extract_metadata(extracted_text[:3000])

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
                                f"{ai_solved} đáp án từ AI, "
                                f"{len(still_missing)} đáp án mặc định (cần kiểm tra)"
                            )
                        else:
                            desc_parts.append(
                                f"• {len(has_answer)} đáp án từ file, "
                                f"{ai_solved} đáp án từ AI"
                            )
                        
                    base_title = metadata.get("title") or f"Trích xuất từ {filename}"
                    
                    # Split questions by chapter
                    from collections import defaultdict
                    chapter_groups = defaultdict(list)
                    for q in unique_questions:
                        ch = q.get("chapter", "")
                        chapter_groups[ch].append(q)
                    
                    quiz_data_list = []
                    for ch, qs in chapter_groups.items():
                        if not qs:
                            continue
                        ch_title = f"{base_title} - {ch}" if ch else base_title
                        quiz_data_list.append({
                            "title": ch_title,
                            "description": " ".join(desc_parts),
                            "subject": metadata.get("subject"),
                            "chapter": ch if ch else metadata.get("chapter"),
                            "exam_type": metadata.get("exam_type"),
                            "school": metadata.get("school"),
                            "questions": qs,
                        })
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
                    subject=q_data.get("subject"),
                    chapter=q_data.get("chapter"),
                    exam_type=q_data.get("exam_type"),
                    school=q_data.get("school"),
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

    async def _solve_missing_answers_with_ai(self, questions: list[dict]) -> list[dict]:
        """
        Gửi các câu hỏi thiếu đáp án lên AI để giải.
        Xử lý theo batch (30 câu/batch) để tránh timeout với file lớn.
        
        Returns: list of dicts with 'correct_answer' and 'explanation' 
                 IN THE SAME ORDER as input questions.
        """
        import asyncio
        
        BATCH_SIZE = 30
        # Khởi tạo mảng kết quả với cùng kích thước, mặc định rỗng
        all_solved = [None] * len(questions)
        
        # Chia thành các batch, giữ track index gốc
        batches = []
        for i in range(0, len(questions), BATCH_SIZE):
            batch_items = []
            for j in range(i, min(i + BATCH_SIZE, len(questions))):
                batch_items.append((j, questions[j]))
            batches.append(batch_items)
        
        logger.info(f"Splitting {len(questions)} questions into {len(batches)} batches")
        
        for batch_idx, batch in enumerate(batches):
            logger.info(f"Processing batch {batch_idx + 1}/{len(batches)} ({len(batch)} questions)")
            
            # Tạo payload rút gọn, đánh số thứ tự rõ ràng
            payload = []
            for idx_in_batch, (original_idx, q) in enumerate(batch):
                payload.append({
                    "index": idx_in_batch + 1,  # 1-based cho AI dễ hiểu
                    "question_text": q["question_text"],
                    "options": q["options"]
                })
            json_payload = json.dumps(payload, ensure_ascii=False)
            
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

## OUTPUT FORMAT
Return ONLY a valid JSON object matching this structure:
{{
  "questions": [
    {{
      "index": 1,
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
                    ai_index = solved_q.get("index")
                    if ai_index is not None and 1 <= ai_index <= len(batch):
                        original_idx = batch[ai_index - 1][0]  # index gốc trong questions[]
                        all_solved[original_idx] = solved_q
                    else:
                        # Fallback: nếu AI không trả index, dùng thứ tự
                        pass
                
                # Fallback: nếu không có index, map theo thứ tự xuất hiện
                items_without_index = [s for s in batch_solved if s.get("index") is None]
                if items_without_index and len(items_without_index) == len(batch):
                    # AI không trả index → map theo thứ tự
                    for i, (original_idx, _) in enumerate(batch):
                        if i < len(batch_solved):
                            all_solved[original_idx] = batch_solved[i]
                
                logger.info(f"Batch {batch_idx + 1}: solved {len(batch_solved)} questions")
            except Exception as e:
                logger.error(f"Batch {batch_idx + 1} failed: {e}")
                # Tiếp tục các batch còn lại
                continue
        
        return all_solved

    async def _save_quiz_and_questions(
        self,
        document_id: str,
        quiz_data: dict,
        difficulty: str,
        language: str,
        user_id: str | None,
        subject: str | None,
        chapter: str | None,
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
            "chapter": chapter,
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
