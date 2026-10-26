"""Check transcribed choices without guessing missing source content."""

import re

from app.utils.question_parser import parse_questions_from_text

UNCLEAR = re.compile(r"\[(?:không rõ|illegible|unreadable)\]", re.IGNORECASE)
HEADINGS = re.compile(r"(?im)^\s*(?:Câu|Cau|Question)\s+(\d+)\s*[:.)]\s*")


def complete_options(options) -> bool:
    return (isinstance(options, list) and len(options) == 4
            and all(isinstance(o, dict) and isinstance(o.get("text"), str)
                    and o["text"].strip() and not UNCLEAR.search(o["text"])
                    for o in options)
            and {o.get("key") for o in options} == set("ABCD"))


def transcription_issues(text: str) -> list[tuple[int, int, str]]:
    """Return source spans for incomplete questions, including dropped questions.

    Readers are instructed to normalize numbered headings. Joining all batches
    before this check lets a question continue on the next page normally.
    """
    headings = list(HEADINGS.finditer(text))
    issues = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        block = text[heading.start():end]
        questions = parse_questions_from_text(block)
        if len(questions) != 1 or not complete_options(questions[0]["options"]) or UNCLEAR.search(block):
            issues.append((heading.start(), end, heading.group(1)))
    return issues


def validate_extracted_questions(questions: list[dict]) -> None:
    invalid = [str(index) for index, q in enumerate(questions, 1)
               if not complete_options(q.get("options")) or UNCLEAR.search(q.get("question_text", ""))]
    if invalid:
        raise ValueError(
            "Chưa đọc đủ hoặc chưa rõ các phương án A–D ở câu thứ "
            + ", ".join(invalid[:12])
            + ". Chưa tạo quiz để tránh làm mất phương án. Vui lòng dùng ảnh rõ hơn "
              "hoặc bản đề không bị chữ viết tay che khuất."
        )
