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


def partition_complete_questions(questions: list[dict]) -> tuple[list[dict], list[dict]]:
    """Keep usable questions while isolating ones that still need manual review."""
    complete = []
    incomplete = []
    for question in questions:
        target = complete if (
            complete_options(question.get("options"))
            and not UNCLEAR.search(question.get("question_text", ""))
        ) else incomplete
        target.append(question)
    return complete, incomplete


def merge_reviewed_transcription(original: str, reviewed: str) -> str:
    """Replace only question blocks that became complete on the visual retry.

    The retry occasionally fixes one question while dropping another. Starting
    from the original text and applying only proven improvements preserves both.
    """
    def blocks(text: str):
        headings = list(HEADINGS.finditer(text))
        return {
            heading.group(1): text[heading.start():(
                headings[index + 1].start() if index + 1 < len(headings) else len(text)
            )]
            for index, heading in enumerate(headings)
        }

    reviewed_blocks = blocks(reviewed)
    headings = list(HEADINGS.finditer(original))
    if not headings:
        return reviewed if not transcription_issues(reviewed) else original

    pieces = [original[:headings[0].start()]]
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(original)
        source_block = original[heading.start():end]
        candidate = reviewed_blocks.get(heading.group(1), "")
        if candidate and not transcription_issues(candidate):
            pieces.append(candidate.rstrip() + "\n\n")
        else:
            pieces.append(source_block.rstrip() + "\n\n")
    return "".join(pieces).strip()
