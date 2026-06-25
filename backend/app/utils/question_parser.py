"""
Question Parser - Trích xuất câu hỏi trắc nghiệm từ văn bản có sẵn
=====================================================================

Thay vì dùng AI (chậm, tốn tiền, thiếu chính xác), module này parse
trực tiếp bằng regex để trích xuất câu hỏi MCQ từ file.

Hỗ trợ các format phổ biến:
  - "Câu 1: ..." / "Câu 1. ..." / "1. ..." / "1) ..."
  - Options trên dòng riêng: "A. ...", "A) ...", "a. ..."
  - Options trên cùng 1 dòng: "A. x B. y C. z D. w"
  - Options hỗn hợp: A. B. trên 1 dòng + C. D. trên dòng tiếp
  - Đáp án: "Đáp án: A" / "ĐA: B" / "Answer: C"
  - Bảng đáp án cuối file: "1 | B | 2 | D | ..."
  - Không có đáp án: vẫn trích xuất câu hỏi + options

Performance: parse file 0.3MB (~100 câu) < 50ms.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ============================================
# Regex Patterns
# ============================================

# Pattern nhận diện đáp án đúng (inline trong câu hỏi)
ANSWER_PATTERNS = [
    re.compile(
        r"(?:Đáp\s*án(?:\s*đúng)?|ĐA|đáp\s*án)\s*[.:)\-]\s*([A-Da-d])",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:Correct\s*)?(?:Answer|Ans)\s*[.:)\-]\s*([A-Da-d])",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:=>|→|>>)\s*([A-Da-d])\b",
        re.IGNORECASE,
    ),
]

# Pattern: option ở đầu dòng riêng
SINGLE_OPTION_PATTERN = re.compile(
    r"^\s*([A-Da-d])\s*[.):\-]\s*(.+?)$"
)

# Pattern: đầu câu hỏi - "Câu X:" etc.
# Dấu chấm/hai chấm/ngoặc là tuỳ chọn. Text đằng sau có thể rỗng (text nằm ở dòng dưới).
QUESTION_PREFIX_PATTERN = re.compile(
    r"^\s*(?:Câu|CÂU|Question|QUESTION|Q|Bài)\s*(\d{1,4})\s*[.:)]?\s*(.*)$",
    re.IGNORECASE,
)

# Pattern: đầu câu hỏi - "X. text" (number + dot/paren + optional text)
# Rất linh hoạt vì false positives sẽ bị loại nếu không có >= 2 options đi kèm.
QUESTION_NUM_PATTERN = re.compile(
    r"^\s*(\d{1,4})\s*[.:)]\s*(.*)$",
)

# Pattern bảng đáp án cuối file: "1 | B | 26 | D | 51 | A | 76 | B"
ANSWER_TABLE_PATTERN = re.compile(
    r"(\d{1,4})\s*\|\s*([A-Da-d])",
    re.IGNORECASE,
)


def parse_questions_from_text(text: str) -> list[dict]:
    """
    Parse câu hỏi trắc nghiệm từ văn bản thô.
    """
    if not text or not text.strip():
        return []

    # Step 1: Parse bảng đáp án ở cuối file (nếu có)
    answer_map = _parse_answer_table(text)
    if answer_map:
        logger.info(f"Found answer table with {len(answer_map)} answers")

    # Step 2: Parse câu hỏi
    questions = _parse_line_by_line(text, answer_map)

    logger.info(f"Parsed {len(questions)} raw questions from text")
    return questions


def deduplicate_questions(questions: list[dict]) -> list[dict]:
    """
    Loại bỏ câu hỏi trùng lặp.
    Chỉ loại bỏ khi normalized text HOÀN TOÀN GIỐNG NHAU.
    """
    if not questions:
        return []

    unique = []
    seen = set()

    for q in questions:
        normalized = q["question_text"].lower().strip()
        normalized = re.sub(r"\s+", " ", normalized)

        if normalized not in seen:
            seen.add(normalized)
            unique.append(q)
        else:
            logger.debug(f"Duplicate removed: {q['question_text'][:60]}...")

    removed = len(questions) - len(unique)
    if removed > 0:
        logger.info(
            f"Deduplication: {len(questions)} -> {len(unique)} "
            f"(removed {removed} duplicates)"
        )
    return unique


def _parse_answer_table(text: str) -> dict[int, str]:
    """
    Tìm và parse bảng đáp án ở cuối file.

    Format phổ biến:
    Câu | Đáp án | Câu | Đáp án
    1   | B      | 26  | D
    2   | D      | 27  | A
    ...

    Returns: dict mapping question_number -> answer_key
    """
    answer_map = {}

    # Tìm phần bảng đáp án (thường bắt đầu bằng header chứa "Đáp án")
    table_start = -1
    for pattern_str in [r"Câu\s*\|\s*Đáp\s*án", r"Câu\s*\|\s*ĐA", r"STT\s*\|\s*Đáp"]:
        match = re.search(pattern_str, text, re.IGNORECASE)
        if match:
            table_start = match.start()
            break

    if table_start == -1:
        return answer_map

    table_text = text[table_start:]

    # Parse từng cặp (số câu, đáp án)
    for match in ANSWER_TABLE_PATTERN.finditer(table_text):
        q_num = int(match.group(1))
        answer = match.group(2).upper()
        if 1 <= q_num <= 9999:
            answer_map[q_num] = answer

    return answer_map


def _extract_options_from_line(line: str) -> list[dict]:
    """
    Trích xuất options từ 1 dòng.

    Hỗ trợ:
    - "A. text1 B. text2 C. text3 D. text4"  (tất cả trên 1 dòng)
    - "A. text1 B. text2"  (chỉ 2 options trên 1 dòng)
    """
    options = []

    # Tìm tất cả vị trí bắt đầu option trong dòng
    # Pattern: chữ cái A-D (hoặc a-d) theo sau bởi dấu .):-
    option_starts = []
    for m in re.finditer(r"(?:^|\s)([A-Da-d])\s*[.):\-]\s*", line):
        key = m.group(1).upper()
        if key in {"A", "B", "C", "D"}:
            option_starts.append({
                "key": key,
                "pos": m.end(),
                "match_start": m.start(),
            })

    if len(option_starts) < 2:
        return []

    # Trích xuất text cho mỗi option
    for i, opt_info in enumerate(option_starts):
        start = opt_info["pos"]
        end = option_starts[i + 1]["match_start"] if i + 1 < len(option_starts) else len(line)
        text = line[start:end].strip()
        if text:
            options.append({"key": opt_info["key"], "text": text})

    return options


def _parse_line_by_line(text: str, answer_map: dict[int, str]) -> list[dict]:
    """
    Quét từng dòng để tìm và xây dựng câu hỏi.

    Xử lý mọi format:
    1. Mỗi option trên dòng riêng
    2. Tất cả options trên 1 dòng
    3. Hỗn hợp (2 options/dòng)
    4. Bảng đáp án cuối file
    """
    lines = text.split("\n")
    questions = []
    current_q_num = 0
    current_q_text = ""
    current_options = []
    current_answer = ""

    # Xác định phần bảng đáp án để bỏ qua
    table_start_line = len(lines)
    for i, line in enumerate(lines):
        if re.search(r"Câu\s*\|\s*Đáp\s*án|Câu\s*\|\s*ĐA|STT\s*\|\s*Đáp", line, re.IGNORECASE):
            table_start_line = i
            break

    def _save_current():
        """Lưu câu hỏi hiện tại nếu hợp lệ."""
        nonlocal current_q_text, current_options, current_answer, current_q_num
        if current_q_text and len(current_options) >= 2:
            cleaned = _clean_question_text(current_q_text)
            if cleaned and len(cleaned) >= 3:
                # Deduplicate option keys
                seen_keys = set()
                final_opts = []
                for opt in current_options:
                    if opt["key"] not in seen_keys and opt["key"] in {"A", "B", "C", "D"}:
                        seen_keys.add(opt["key"])
                        final_opts.append(opt)

                if len(final_opts) >= 2:
                    # Tra cứu đáp án từ bảng nếu chưa có
                    answer = current_answer
                    if not answer and current_q_num in answer_map:
                        answer = answer_map[current_q_num]

                    questions.append({
                        "question_text": cleaned,
                        "options": final_opts[:4],
                        "correct_answer": answer,
                        "explanation": "",
                    })

        current_q_text = ""
        current_options = []
        current_answer = ""
        current_q_num = 0

    for line_idx, line in enumerate(lines):
        # Bỏ qua bảng đáp án cuối file
        if line_idx >= table_start_line:
            # Lưu câu hỏi cuối cùng trước khi vào bảng
            if current_q_text:
                _save_current()
            break

        stripped = line.strip()
        # Loại bỏ markdown formatting (**, *, __, _)
        stripped = re.sub(r"^\*{1,2}|\*{1,2}$", "", stripped).strip()
        stripped = re.sub(r"^_{1,2}|_{1,2}$", "", stripped).strip()
        if not stripped:
            continue

        # ---- 1. Check: dòng này là ĐÁP ÁN inline? ----
        answer_found = False
        for pattern in ANSWER_PATTERNS:
            ans_match = pattern.search(stripped)
            if ans_match:
                current_answer = ans_match.group(1).upper()
                answer_found = True
                _save_current()
                break
        if answer_found:
            continue

        # ---- 2. Check: dòng này là ĐẦU CÂU HỎI MỚI? ----
        is_new_question = False
        q_num = 0
        q_text = ""

        # Thử "Câu X:" trước
        q_match = QUESTION_PREFIX_PATTERN.match(stripped)
        if q_match:
            q_num = int(q_match.group(1))
            q_text = q_match.group(2).strip()
            is_new_question = True
        else:
            # Thử "X. text" (number only)
            q_match = QUESTION_NUM_PATTERN.match(stripped)
            if q_match:
                num = int(q_match.group(1))
                remaining = q_match.group(2).strip()
                # Verify: không phải option line (A.xxx B.yyy ...)
                # và số phải hợp lý (1-999)
                if 1 <= num <= 999:
                    q_num = num
                    q_text = remaining
                    is_new_question = True

        if is_new_question:
            # Lưu câu hỏi trước đó
            _save_current()

            current_q_num = q_num

            # Check: phần text có chứa inline options không?
            inline_opts = _extract_options_from_line(q_text)
            if inline_opts:
                # Tìm vị trí option đầu tiên trong q_text để tách question
                first_opt_match = re.search(r"(?:^|\s)[A-Da-d]\s*[.):\-]\s*", q_text)
                if first_opt_match:
                    current_q_text = q_text[:first_opt_match.start()].strip()
                else:
                    current_q_text = q_text
                current_options = inline_opts
            else:
                current_q_text = q_text
                current_options = []

            current_answer = ""
            continue

        # ---- 3. Check: dòng chứa INLINE OPTIONS (A. x B. y ...)? ----
        if current_q_text:
            inline_opts = _extract_options_from_line(stripped)
            if inline_opts:
                current_options.extend(inline_opts)
                continue

        # ---- 4. Check: dòng là 1 OPTION riêng lẻ? ----
        opt_match = SINGLE_OPTION_PATTERN.match(stripped)
        if opt_match and current_q_num > 0:
            key = opt_match.group(1).upper()
            opt_text = opt_match.group(2).strip()
            current_options.append({"key": key, "text": opt_text})
            continue

        # ---- 5. Dòng không match → phần tiếp theo của câu hỏi hoặc option ----
        if current_q_num > 0 and not current_options:
            if current_q_text:
                current_q_text += " " + stripped
            else:
                current_q_text = stripped

    # Lưu câu hỏi cuối cùng
    _save_current()

    return questions


# ============================================
# Helpers
# ============================================

def _clean_question_text(text: str) -> str:
    """Làm sạch text câu hỏi: bỏ prefix số, normalize whitespace."""
    text = re.sub(
        r"^\s*(?:Câu|CÂU|Question|QUESTION|Q)?\s*\d{1,4}\s*[.:)]\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+", " ", text).strip()
    return text
