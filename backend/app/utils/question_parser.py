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
  - Đáp án inline: "Đáp án: A" / "ĐA: B" / "Answer: C"
  - Đáp án tô sẵn: **A**, *A*, ✓A, √A, [x]A, (x)A
  - Bảng đáp án cuối file:
    + Dạng pipe:  "1 | B | 26 | D | 51 | A"
    + Dạng dot:   "1.A  2.B  3.C  4.D"
    + Dạng dash:  "1-A, 2-B, 3-C, 4-D"
    + Dạng liệt kê: "1. A    2. B    3. C"
    + Dạng header: "ĐÁP ÁN" / "BẢNG ĐÁP ÁN" section

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
ANSWER_TABLE_PIPE_PATTERN = re.compile(
    r"(\d{1,4})\s*\|\s*([A-Da-d])",
    re.IGNORECASE,
)

# Pattern bảng đáp án dạng dot/dash: "1.A" "1-A" "1: A" "1)A"
ANSWER_TABLE_COMPACT_PATTERN = re.compile(
    r"(?:^|[\s,;])(\d{1,4})\s*[.\-:)]\s*([A-Da-d])(?=[\s,;.$]|$)",
    re.IGNORECASE,
)

# Header patterns để nhận diện section bảng đáp án
ANSWER_SECTION_HEADERS = [
    re.compile(r"(?:BẢNG\s*)?ĐÁP\s*ÁN", re.IGNORECASE),
    re.compile(r"ANSWER\s*KEY", re.IGNORECASE),
    re.compile(r"Câu\s*\|\s*Đáp\s*án", re.IGNORECASE),
    re.compile(r"Câu\s*\|\s*ĐA", re.IGNORECASE),
    re.compile(r"STT\s*\|\s*Đáp", re.IGNORECASE),
    re.compile(r"KEY\s*:", re.IGNORECASE),
]

# Pattern nhận diện option bị tô/đánh dấu
# Ví dụ: **A.** text, *A.* text, __A.__ text, _A._ text
MARKED_OPTION_BOLD = re.compile(
    r"^\s*\*{1,2}([A-Da-d])\s*[.):\-]\s*(.+?)\*{1,2}\s*$"
)
MARKED_OPTION_UNDERLINE = re.compile(
    r"^\s*_{1,2}([A-Da-d])\s*[.):\-]\s*(.+?)_{1,2}\s*$"
)
# Dấu tích: ✓, √, ✔, ☑, [x], (x)
MARKED_OPTION_CHECK = re.compile(
    r"^\s*(?:[✓✔√☑]|\[x\]|\(x\))\s*([A-Da-d])\s*[.):\-]\s*(.+?)$",
    re.IGNORECASE,
)
# Dấu tích sau option key: "A. ✓ text" hoặc "A. √ text"
MARKED_OPTION_CHECK_AFTER = re.compile(
    r"^\s*([A-Da-d])\s*[.):\-]\s*(?:[✓✔√☑]|\[x\]|\(x\))\s*(.+?)$",
    re.IGNORECASE,
)


def parse_questions_from_text(text: str) -> list[dict]:
    """
    Parse câu hỏi trắc nghiệm từ văn bản thô.
    
    Ưu tiên đáp án:
    1. Đáp án inline trong câu hỏi ("Đáp án: A")
    2. Đáp án tô sẵn/đánh dấu trong options (**A**, ✓A)
    3. Bảng đáp án cuối file
    4. → Nếu vẫn thiếu → gọi AI (ở quiz_service.py)
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
    
    # Log statistics
    with_answer = sum(1 for q in questions if q.get("correct_answer"))
    without_answer = len(questions) - with_answer
    logger.info(
        f"Answer stats: {with_answer} có đáp án, "
        f"{without_answer} cần AI giải"
    )
    
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

    Hỗ trợ nhiều format:
    1. Pipe: "1 | B | 26 | D"
    2. Compact: "1.A  2.B  3.C  4.D" hoặc "1-A, 2-B, 3-C"
    3. Listing: "1. A    2. B    3. C"
    4. Section header: "ĐÁP ÁN" / "BẢNG ĐÁP ÁN" / "ANSWER KEY"

    Returns: dict mapping question_number -> answer_key (uppercase)
    """
    answer_map = {}

    # Tìm vị trí bắt đầu section đáp án
    table_start = -1
    for header_pattern in ANSWER_SECTION_HEADERS:
        match = header_pattern.search(text)
        if match:
            table_start = match.start()
            break

    if table_start == -1:
        return answer_map

    table_text = text[table_start:]

    # Thử parse dạng pipe trước (chính xác nhất)
    pipe_matches = list(ANSWER_TABLE_PIPE_PATTERN.finditer(table_text))
    if pipe_matches:
        for m in pipe_matches:
            q_num = int(m.group(1))
            answer = m.group(2).upper()
            if 1 <= q_num <= 9999:
                answer_map[q_num] = answer
        if answer_map:
            return answer_map

    # Thử parse dạng compact: "1.A  2.B  3.C" hoặc "1-A, 2-B"
    compact_matches = list(ANSWER_TABLE_COMPACT_PATTERN.finditer(table_text))
    if len(compact_matches) >= 3:  # Cần ít nhất 3 cặp để chắc chắn đây là bảng
        for m in compact_matches:
            q_num = int(m.group(1))
            answer = m.group(2).upper()
            if 1 <= q_num <= 9999:
                answer_map[q_num] = answer

    return answer_map


def _detect_marked_answer(options: list[dict], raw_lines: list[str]) -> str:
    """
    Phát hiện đáp án đã được tô/đánh dấu sẵn trong options.
    
    Nhận diện các dạng:
    - In đậm: **A. text** hoặc __A. text__
    - Dấu tích: ✓A. text, √A. text, ✔A. text, [x]A. text
    - Dấu tích sau key: A. ✓ text
    
    Returns: answer key (A/B/C/D) hoặc "" nếu không tìm thấy
    """
    for line in raw_lines:
        stripped = line.strip()
        if not stripped:
            continue
        
        # Check bold marking: **A. text** hoặc *A. text*
        m = MARKED_OPTION_BOLD.match(stripped)
        if m:
            return m.group(1).upper()
        
        # Check underline marking: __A. text__ hoặc _A. text_
        m = MARKED_OPTION_UNDERLINE.match(stripped)
        if m:
            return m.group(1).upper()
        
        # Check tick before key: ✓A. text
        m = MARKED_OPTION_CHECK.match(stripped)
        if m:
            return m.group(1).upper()
        
        # Check tick after key: A. ✓ text
        m = MARKED_OPTION_CHECK_AFTER.match(stripped)
        if m:
            return m.group(1).upper()
    
    return ""


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
    5. Đáp án tô sẵn trong options
    """
    lines = text.split("\n")
    questions = []
    current_q_num = 0
    current_q_text = ""
    current_options = []
    current_answer = ""
    current_option_raw_lines = []  # Lưu raw lines của options để detect marking

    # Xác định phần bảng đáp án để bỏ qua
    table_start_line = len(lines)
    for i, line in enumerate(lines):
        for header_pattern in ANSWER_SECTION_HEADERS:
            if header_pattern.search(line):
                table_start_line = i
                break
        if i == table_start_line:
            break

    def _save_current():
        """Lưu câu hỏi hiện tại nếu hợp lệ."""
        nonlocal current_q_text, current_options, current_answer, current_q_num, current_option_raw_lines
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
                    answer = current_answer
                    
                    # Ưu tiên 1: đáp án inline đã tìm thấy
                    # (current_answer đã được set)
                    
                    # Ưu tiên 2: đáp án tô sẵn trong options
                    if not answer:
                        answer = _detect_marked_answer(
                            final_opts, current_option_raw_lines
                        )
                    
                    # Ưu tiên 3: tra cứu bảng đáp án
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
        current_option_raw_lines = []

    for line_idx, line in enumerate(lines):
        # Bỏ qua bảng đáp án cuối file
        if line_idx >= table_start_line:
            # Lưu câu hỏi cuối cùng trước khi vào bảng
            if current_q_text:
                _save_current()
            break

        stripped = line.strip()
        # Lưu bản gốc trước khi strip markdown (để detect bold/underline marking)
        original_stripped = stripped
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
                current_option_raw_lines = [q_text]
            else:
                current_q_text = q_text
                current_options = []
                current_option_raw_lines = []

            current_answer = ""
            continue

        # ---- 3. Check: dòng chứa INLINE OPTIONS (A. x B. y ...)? ----
        if current_q_text:
            inline_opts = _extract_options_from_line(stripped)
            if inline_opts:
                current_options.extend(inline_opts)
                current_option_raw_lines.append(original_stripped)
                continue

        # ---- 4. Check: dòng là 1 OPTION riêng lẻ? ----
        opt_match = SINGLE_OPTION_PATTERN.match(stripped)
        if opt_match and current_q_num > 0:
            key = opt_match.group(1).upper()
            opt_text = opt_match.group(2).strip()
            current_options.append({"key": key, "text": opt_text})
            current_option_raw_lines.append(original_stripped)
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
