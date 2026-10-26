"""Exercise real document parsing and persistence without network services."""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fitz
import pytest
from bson import ObjectId
from docx import Document

from app.services.quiz_service import QuizService


class MemoryCollection:
    def __init__(self):
        self.rows = []

    async def insert_one(self, row):
        row["_id"] = ObjectId()
        self.rows.append(row)
        return SimpleNamespace(inserted_id=row["_id"])

    async def insert_many(self, rows):
        ids = [(await self.insert_one(row)).inserted_id for row in rows]
        return SimpleNamespace(inserted_ids=ids)

    async def find_one(self, query):
        return next(row for row in self.rows if all(row.get(k) == v for k, v in query.items()))

    async def update_one(self, query, update):
        (await self.find_one(query)).update(update["$set"])

    def find(self, query):
        rows = [row for row in self.rows if all(row.get(k) == v for k, v in query.items())]
        return SimpleNamespace(sort=lambda key, direction: SimpleNamespace(
            to_list=AsyncMock(return_value=sorted(rows, key=lambda row: row[key]))
        ))


@pytest.mark.asyncio
@pytest.mark.parametrize("file_type", ["txt", "docx", "pdf"])
async def test_document_to_quiz_pipeline(file_type):
    source = "Python is a programming language. FastAPI is a framework for building web APIs. " * 3
    if file_type == "docx":
        document = Document()
        document.add_paragraph(source)
        buffer = BytesIO()
        document.save(buffer)
        data = buffer.getvalue()
    elif file_type == "pdf":
        with fitz.open() as document:
            page = document.new_page()
            page.insert_textbox(fitz.Rect(40, 40, 550, 780), source)
            data = document.tobytes()
    else:
        data = source.encode()

    questions = [{
        "question_text": f"Question {n}: What is Python?",
        "options": [{"key": key, "text": f"Option {key}"} for key in "ABCD"],
        "correct_answer": "B", "explanation": "A programming language.",
    } for n in range(1, 6)]
    ai = SimpleNamespace(generate_quiz=AsyncMock(return_value={
        "title": "Python quiz", "questions": questions,
    }))
    db = SimpleNamespace(**{name: MemoryCollection() for name in ("documents", "quizzes", "questions")})
    service = QuizService(db=db, gemini_service=ai)

    result = await service.upload_and_generate_quiz(
        file_bytes=data, filename=f"sample.{file_type}", file_type=file_type,
        num_questions=5, mode="generate",
    )

    ai.generate_quiz.assert_awaited_once()
    assert "Python" in ai.generate_quiz.await_args.kwargs["text"]
    assert db.documents.rows[0]["upload_status"] == "completed"
    assert db.quizzes.rows[0]["total_questions"] == 5
    assert [row["correct_answer"] for row in db.questions.rows] == ["B"] * 5
    assert [question["order"] for question in result["quiz"]["questions"]] == list(range(1, 6))
    assert all("correct_answer" not in question for question in result["quiz"]["questions"])
