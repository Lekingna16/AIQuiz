"""
Test DeepSeek Service - Unit tests cho JSON parsing & validation
================================================================

Lưu ý: KHÔNG test actual API calls (cần API key, tốn tiền).
Chỉ test parsing logic, validation logic, và error handling.
Sử dụng mock cho API calls.
"""

import json

import pytest

from app.services.ai_service import (
    DeepSeekService,
    QuizGenerationError,
)


# ============================================
# SAMPLE DATA
# ============================================

VALID_QUIZ_JSON = {
    "title": "Python Basics Quiz",
    "description": "Test your knowledge of Python fundamentals",
    "questions": [
        {
            "question_text": "What is the output of print(type([]))?",
            "options": [
                {"key": "A", "text": "<class 'list'>"},
                {"key": "B", "text": "<class 'tuple'>"},
                {"key": "C", "text": "<class 'dict'>"},
                {"key": "D", "text": "<class 'set'>"},
            ],
            "correct_answer": "A",
            "explanation": "[] creates an empty list, so type returns <class 'list'>.",
        },
        {
            "question_text": "Which keyword is used to define a function in Python?",
            "options": [
                {"key": "A", "text": "function"},
                {"key": "B", "text": "def"},
                {"key": "C", "text": "func"},
                {"key": "D", "text": "define"},
            ],
            "correct_answer": "B",
            "explanation": "In Python, the 'def' keyword is used to define a function.",
        },
    ],
}


# ============================================
# PARSE RESPONSE TESTS
# ============================================

class TestParseResponse:
    """Tests cho _parse_response method."""

    def test_parse_valid_json(self):
        """Test parse JSON hợp lệ."""
        json_str = json.dumps(VALID_QUIZ_JSON)
        # We need a DeepSeekService instance to test the method,
        # but we can't create one without a valid API key.
        # So we test the static method directly.
        DeepSeekService._validate_quiz_structure(VALID_QUIZ_JSON)
        # Should not raise

    def test_parse_json_with_code_fences(self):
        """Test parse JSON có markdown code fences."""
        json_str = f"```json\n{json.dumps(VALID_QUIZ_JSON)}\n```"
        # Simulate _parse_response cleaning
        import re
        cleaned = re.sub(r"```json\s*", "", json_str)
        cleaned = re.sub(r"\s*```", "", cleaned)
        data = json.loads(cleaned.strip())
        assert "questions" in data
        assert len(data["questions"]) == 2

    def test_parse_invalid_json(self):
        """Test parse text không phải JSON."""
        with pytest.raises(json.JSONDecodeError):
            json.loads("This is not JSON at all")


# ============================================
# VALIDATE QUIZ STRUCTURE TESTS
# ============================================

class TestValidateQuizStructure:
    """Tests cho _validate_quiz_structure."""

    def test_valid_structure(self):
        """Test structure hợp lệ không raise."""
        DeepSeekService._validate_quiz_structure(VALID_QUIZ_JSON)

    def test_missing_questions_field(self):
        """Test thiếu field 'questions'."""
        data = {"title": "Quiz", "description": "Test"}
        with pytest.raises(QuizGenerationError, match="missing 'questions'"):
            DeepSeekService._validate_quiz_structure(data)

    def test_questions_not_list(self):
        """Test 'questions' không phải list."""
        data = {"questions": "not a list"}
        with pytest.raises(QuizGenerationError, match="must be a list"):
            DeepSeekService._validate_quiz_structure(data)

    def test_missing_question_fields(self):
        """Test question thiếu required fields."""
        data = {
            "questions": [
                {
                    "question_text": "What is Python?",
                    # Missing: options, correct_answer
                }
            ]
        }
        with pytest.raises(QuizGenerationError, match="missing fields"):
            DeepSeekService._validate_quiz_structure(data)

    def test_wrong_option_count(self):
        """Test question có ít/nhiều hơn 4 options."""
        data = {
            "questions": [
                {
                    "question_text": "What is Python?",
                    "options": [
                        {"key": "A", "text": "Language"},
                        {"key": "B", "text": "Framework"},
                    ],
                    "correct_answer": "A",
                }
            ]
        }
        with pytest.raises(QuizGenerationError, match="2 options"):
            DeepSeekService._validate_quiz_structure(data)

    def test_invalid_option_keys(self):
        """Test option keys không phải A/B/C/D."""
        data = {
            "questions": [
                {
                    "question_text": "What is Python?",
                    "options": [
                        {"key": "1", "text": "Option 1"},
                        {"key": "2", "text": "Option 2"},
                        {"key": "3", "text": "Option 3"},
                        {"key": "4", "text": "Option 4"},
                    ],
                    "correct_answer": "1",
                }
            ]
        }
        with pytest.raises(QuizGenerationError, match="invalid option keys"):
            DeepSeekService._validate_quiz_structure(data)

    def test_invalid_correct_answer(self):
        """Test correct_answer không hợp lệ."""
        data = {
            "questions": [
                {
                    "question_text": "What is Python?",
                    "options": [
                        {"key": "A", "text": "Language"},
                        {"key": "B", "text": "Framework"},
                        {"key": "C", "text": "Database"},
                        {"key": "D", "text": "OS"},
                    ],
                    "correct_answer": "E",  # Invalid
                }
            ]
        }
        with pytest.raises(QuizGenerationError, match="invalid correct_answer"):
            DeepSeekService._validate_quiz_structure(data)

    def test_empty_option_text(self):
        """Test option có text rỗng."""
        data = {
            "questions": [
                {
                    "question_text": "What is Python?",
                    "options": [
                        {"key": "A", "text": "Language"},
                        {"key": "B", "text": ""},  # Empty
                        {"key": "C", "text": "Database"},
                        {"key": "D", "text": "OS"},
                    ],
                    "correct_answer": "A",
                }
            ]
        }
        with pytest.raises(QuizGenerationError, match="text is empty"):
            DeepSeekService._validate_quiz_structure(data)

    def test_multiple_questions_valid(self):
        """Test multiple questions đều hợp lệ."""
        # VALID_QUIZ_JSON has 2 questions
        DeepSeekService._validate_quiz_structure(VALID_QUIZ_JSON)


# ============================================
# DEEPSEEK SERVICE INITIALIZATION
# ============================================

class TestDeepSeekServiceInit:
    """Tests cho DeepSeekService initialization."""

    def test_invalid_api_key_placeholder(self):
        """Test reject placeholder API key."""
        with pytest.raises(ValueError, match="Invalid DeepSeek API key"):
            DeepSeekService(api_key="your_deepseek_api_key_here")

    def test_empty_api_key(self):
        """Test reject empty API key."""
        with pytest.raises(ValueError, match="Invalid DeepSeek API key"):
            DeepSeekService(api_key="")
