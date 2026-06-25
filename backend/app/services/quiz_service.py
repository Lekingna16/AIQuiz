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
        user_id: str | None = None,
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
            # Step 4: Generate quiz with AI
            # =====================
            logger.info(
                f"Generating {num_questions} questions "
                f"(difficulty={difficulty}, lang={language})"
            )
            quiz_data = await self.gemini.generate_quiz(
                text=processed_text,
                num_questions=num_questions,
                difficulty=difficulty,
                language=language,
            )

            # =====================
            # Step 5: Save quiz + questions to DB
            # =====================
            quiz_id, question_ids = await self._save_quiz_and_questions(
                document_id=document_id,
                quiz_data=quiz_data,
                difficulty=difficulty,
                language=language,
                user_id=user_id,
            )
            logger.info(
                f"Quiz saved: {quiz_id} with {len(question_ids)} questions"
            )

            # =====================
            # Step 6: Update document status → completed
            # =====================
            await self._update_document_status(document_id, "completed")

            # =====================
            # Step 7: Build response
            # =====================
            response = await self._build_response(quiz_id, document_id)
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

    async def _save_quiz_and_questions(
        self,
        document_id: str,
        quiz_data: dict,
        difficulty: str,
        language: str,
        user_id: str | None,
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
        questions = await questions_cursor.to_list(length=100)

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
