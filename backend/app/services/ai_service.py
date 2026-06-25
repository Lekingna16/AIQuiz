"""
DeepSeek AI Service - Tích hợp DeepSeek API để sinh câu hỏi trắc nghiệm
=========================================================================

Kiến trúc:
- DeepSeekService: class chính quản lý kết nối và tạo quiz
- SYSTEM_PROMPT: prompt template đã được tuning cho MCQ generation
- Retry logic: xử lý API failures, JSON parse errors với exponential backoff

Tại sao dùng OpenAI SDK?
- DeepSeek API tương thích 100% với OpenAI API format
- Chỉ cần thay base_url → https://api.deepseek.com
- SDK handle auth, rate limiting, retry tự động
- Type-safe response objects
- response_format={"type": "json_object"} → force JSON output

Model choice: deepseek-chat
- Chi phí rất thấp (rẻ hơn GPT-4o nhiều lần)
- Context window lớn (64K tokens)
- Đủ thông minh cho MCQ generation
- Phù hợp cho project portfolio
"""

import asyncio
import json
import logging
import re

from openai import OpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

logger = logging.getLogger(__name__)


# ============================================
SYSTEM_PROMPT_GENERATE = """You are an expert educational assessment designer. 

## TASK
Your task is to GENERATE exactly {num_questions} high-quality multiple-choice questions (MCQs) based STRICTLY on the source material at {difficulty} difficulty level.

## RULES (MUST FOLLOW):
1. **Factual accuracy**: Every question and answer MUST be directly supported by the source text. NEVER fabricate or infer information not present in the source.
2. **Distractors**: Wrong answers must be plausible and logically related to the topic, but clearly incorrect based on the source material. Avoid absurd or obviously wrong options.
3. **Coverage**: Distribute them across different sections/topics of the source material evenly.
4. **Clarity**: Questions must be unambiguous with exactly ONE correct answer. Avoid "all of the above" or "none of the above" options.
5. **Language**: Generate ALL content (questions, options, explanations) in {language}.
6. **Explanations**: Each explanation should briefly reference the relevant part of the source material or explain why the answer is correct.

## OUTPUT FORMAT (STRICT JSON):
Return ONLY a valid JSON object. No markdown, no code fences, no extra text before or after.

{{
  "title": "A descriptive quiz title based on the document content",
  "description": "A brief 1-2 sentence description of what the quiz covers",
  "questions": [
    {{
      "question_text": "Clear, specific question?",
      "options": [
        {{"key": "A", "text": "First option"}},
        {{"key": "B", "text": "Second option"}},
        {{"key": "C", "text": "Third option"}},
        {{"key": "D", "text": "Fourth option"}}
      ],
      "correct_answer": "A",
      "explanation": "Brief explanation referencing the source material."
    }}
  ]
}}
"""

SYSTEM_PROMPT_EXTRACT = """You are an expert data extractor.

## TASK
The source material ALREADY contains a list of multiple-choice questions. Your task is to EXTRACT them. 
IMPORTANT: You MUST filter out and REMOVE any DUPLICATE questions (questions that ask the same thing or have identical text).

## RULES (MUST FOLLOW):
1. **Extraction only**: Do not create new questions. Only extract what is present in the source material.
2. **Deduplication**: If a question appears multiple times, keep only ONE version of it.
3. **Language**: Output ALL content in {language}. Provide translations if necessary.
4. **Format options correctly**: Ensure each question has exactly 4 options (A, B, C, D) and one correct answer.
5. **Solve missing answers**: If the source material does NOT provide the correct answer or explanation for an extracted question, YOU MUST SOLVE IT yourself based on your knowledge and provide the correct_answer and a brief explanation.

## OUTPUT FORMAT (STRICT JSON):
Return ONLY a valid JSON object. No markdown, no code fences, no extra text before or after.

{{
  "title": "A descriptive quiz title based on the document content",
  "description": "A brief 1-2 sentence description of what the quiz covers",
  "questions": [
    {{
      "question_text": "Clear, specific question?",
      "options": [
        {{"key": "A", "text": "First option"}},
        {{"key": "B", "text": "Second option"}},
        {{"key": "C", "text": "Third option"}},
        {{"key": "D", "text": "Fourth option"}}
      ],
      "correct_answer": "A",
      "explanation": "Brief explanation referencing the source material."
    }}
  ]
}}
"""


class DeepSeekServiceError(Exception):
    """Base exception cho DeepSeek service errors."""
    pass


class QuizGenerationError(DeepSeekServiceError):
    """Lỗi khi sinh quiz (AI response không hợp lệ)."""
    pass


class APIConnectionError(DeepSeekServiceError):
    """Lỗi kết nối tới DeepSeek API."""
    pass


class DeepSeekService:
    """
    Service tích hợp DeepSeek API cho quiz generation.

    Usage:
        service = DeepSeekService(api_key="...")
        quiz_data = await service.generate_quiz(
            text="nội dung tài liệu...",
            num_questions=10,
            difficulty="mixed",
            language="vi",
        )

    quiz_data sẽ có format:
    {
        "title": "...",
        "description": "...",
        "questions": [...]
    }
    """

    def __init__(self, api_key: str):
        """
        Khởi tạo DeepSeek service.

        Args:
            api_key: DeepSeek API key từ https://platform.deepseek.com/api_keys
        """
        if not api_key or api_key == "your_deepseek_api_key_here":
            raise ValueError(
                "Invalid DeepSeek API key. "
                "Get your key at: https://platform.deepseek.com/api_keys"
            )

        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
        )
        self.model = "deepseek-chat"
        logger.info(f"DeepSeekService initialized with model: {self.model}")

    async def generate_quiz(
        self,
        text: str,
        num_questions: int = 10,
        difficulty: str = "mixed",
        language: str = "vi",
        mode: str = "generate",
    ) -> dict:
        """
        Sinh bộ câu hỏi trắc nghiệm từ nội dung văn bản.

        Args:
            text: Nội dung văn bản đã extract & preprocess
            num_questions: Số câu hỏi cần tạo (5-30)
            difficulty: Mức độ khó (easy/medium/hard/mixed)
            language: Ngôn ngữ output (vi/en)
            mode: "generate" hoặc "extract"

        Returns:
            Dict chứa title, description, questions

        Raises:
            QuizGenerationError: Nếu AI response không parse được
            APIConnectionError: Nếu không kết nối được DeepSeek API
        """
        # Build prompt từ template
        if mode == "extract":
            system_prompt = SYSTEM_PROMPT_EXTRACT.format(language=language)
        else:
            system_prompt = SYSTEM_PROMPT_GENERATE.format(
                language=language,
                num_questions=num_questions,
                difficulty=difficulty,
            )

        # Gọi API với retry logic
        response_text = await self._call_api_with_retry(system_prompt, text)

        # Parse và validate response
        quiz_data = self._parse_response(response_text)

        # Validate số câu hỏi (chỉ cảnh báo nếu ở chế độ generate)
        actual_count = len(quiz_data.get("questions", []))
        if actual_count == 0:
            # Ghi log text ra file để debug
            with open("failed_extracted_text.log", "w", encoding="utf-8") as f:
                f.write(text)
            raise QuizGenerationError("AI generated 0 questions (Extracted text saved to failed_extracted_text.log)")

        if mode == "generate" and actual_count != num_questions:
            logger.warning(
                f"Requested {num_questions} questions, got {actual_count}"
            )

        return quiz_data

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        retry=retry_if_exception_type((
            json.JSONDecodeError,
            QuizGenerationError,
        )),
        reraise=True,
    )
    async def _call_api_with_retry(self, system_prompt: str, text: str) -> str:
        """
        Gọi DeepSeek API với retry logic.

        Retry khi:
        - JSON parse error (AI trả format sai)
        - QuizGenerationError (thiếu fields)

        KHÔNG retry khi:
        - API key invalid (401)
        - Rate limit (429) → tenacity exponential backoff
        - Timeout → raise ngay
        """
        try:
            # Chạy synchronous OpenAI call trong thread pool
            # để không block event loop
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.chat.completions.create,
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"SOURCE MATERIAL:\n{text}"},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.3,  # Low temp → consistent, factual output
                    max_tokens=8192,
                ),
                timeout=300,  # Tăng lên 300s cho các file lớn
            )

            content = response.choices[0].message.content
            if not content:
                raise QuizGenerationError("Empty response from DeepSeek API")

            # Parse thử để trigger retry nếu JSON invalid
            self._parse_response(content)

            return content

        except asyncio.TimeoutError:
            raise APIConnectionError(
                "DeepSeek API timeout after 300 seconds. "
                "The document might be too long or the API is overloaded."
            )
        except Exception as e:
            # Re-raise known errors, wrap unknown ones
            if isinstance(e, (QuizGenerationError, APIConnectionError, json.JSONDecodeError)):
                raise
            raise APIConnectionError(f"DeepSeek API error: {str(e)}")

    def _parse_response(self, text: str) -> dict:
        """
        Parse và validate AI response JSON.

        Steps:
        1. Strip markdown code fences (nếu AI trả ```json...```)
        2. Parse JSON
        3. Validate structure (title, questions, options, correct_answer)

        Args:
            text: Raw response text từ DeepSeek

        Returns:
            Validated quiz dict

        Raises:
            json.JSONDecodeError: Nếu không phải valid JSON
            QuizGenerationError: Nếu thiếu required fields
        """
        # Step 1: Clean markdown fences
        cleaned = re.sub(r"```json\s*", "", text)
        cleaned = re.sub(r"\s*```", "", cleaned)
        cleaned = cleaned.strip()

        # Step 2: Parse JSON
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {text[:200]}...")
            raise

        # Step 3: Validate structure
        self._validate_quiz_structure(data)

        # Step 4: Deduplicate questions as a fallback
        import string
        unique_questions = []
        seen_texts = set()
        
        for q in data.get("questions", []):
            # Chuẩn hóa text: chuyển chữ thường, xóa khoảng trắng thừa và dấu câu
            normalized = q["question_text"].lower().strip()
            normalized = normalized.translate(str.maketrans('', '', string.punctuation))
            
            if normalized not in seen_texts:
                seen_texts.add(normalized)
                unique_questions.append(q)
            else:
                logger.info(f"Filtered out duplicate question: {q['question_text']}")
                
        data["questions"] = unique_questions

        return data

    @staticmethod
    def _validate_quiz_structure(data: dict) -> None:
        """
        Validate quiz data structure trả về từ AI.

        Kiểm tra:
        - Có field "questions" (required)
        - Mỗi question có: question_text, options (4), correct_answer
        - correct_answer phải là A/B/C/D
        - Options phải có key A/B/C/D

        Raises:
            QuizGenerationError: Nếu structure không hợp lệ
        """
        if "questions" not in data:
            raise QuizGenerationError(
                "AI response missing 'questions' field"
            )

        if not isinstance(data["questions"], list):
            raise QuizGenerationError(
                "'questions' must be a list"
            )

        required_fields = {"question_text", "options", "correct_answer"}
        valid_keys = {"A", "B", "C", "D"}

        for i, question in enumerate(data["questions"]):
            # Check required fields
            missing = required_fields - set(question.keys())
            if missing:
                raise QuizGenerationError(
                    f"Question {i + 1} missing fields: {missing}"
                )

            # Check options count
            options = question.get("options", [])
            if len(options) != 4:
                raise QuizGenerationError(
                    f"Question {i + 1} has {len(options)} options, expected 4"
                )

            # Check option keys
            option_keys = {opt.get("key") for opt in options}
            if option_keys != valid_keys:
                raise QuizGenerationError(
                    f"Question {i + 1} has invalid option keys: {option_keys}. "
                    f"Expected: {valid_keys}"
                )

            # Check correct_answer validity
            correct = question.get("correct_answer")
            if correct not in valid_keys:
                raise QuizGenerationError(
                    f"Question {i + 1} has invalid correct_answer: '{correct}'. "
                    f"Must be one of: {valid_keys}"
                )

            # Check option text not empty
            for opt in options:
                if not opt.get("text", "").strip():
                    raise QuizGenerationError(
                        f"Question {i + 1}, Option {opt.get('key')}: "
                        f"text is empty"
                    )
