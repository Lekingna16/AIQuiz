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
    + Dạng cột chấm máy: "mamon | made | cauhoi | dapan" (theo đúng Mã đề thi)

Performance: parse file 0.3MB (~100 câu) < 50ms.
"""

import re
import logging

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

# Pattern: option ở đầu dòng riêng. Some OCR / PDF text layers lose the dot
# between the option key and its text (``A Mycobacterium ...``), so whitespace
# is accepted as a last-resort separator too.
SINGLE_OPTION_PATTERN = re.compile(
    r"^\s*(?:đáp\s*án\s*)?([A-Da-d])(?:\s*[.):\-]\s*|\s+)(.*)$",
    re.IGNORECASE,
)

# Pattern: đầu câu hỏi - "Câu X:" etc.
# Dấu chấm/hai chấm/ngoặc là tuỳ chọn. Text đằng sau có thể rỗng (text nằm ở dòng dưới).
NUMERIC_OPTION_PATTERN = re.compile(r"^\s*([1-4])\s*[.)]\s*(.*)$")

QUESTION_PREFIX_PATTERN = re.compile(
    r"^\s*[\"'“”‘’(\[{<>^_+\-–—•·«»~`]*\s*"
    r"(?:(?i:c?(?:câu|cau)|question|q)|C(?:lu|ầu|ân|ău|áu|àu|ẫu|â0|a0))"
    r"[\s:`'´]*(\d{1,4})\s*[.:),;\-]?\s*(.*)$",
)

# Pattern: đầu câu hỏi - "X. text" (không khớp số thập phân kiểu "99.3")
QUESTION_NUM_PATTERN = re.compile(
    r"^\s*(\d{1,4}|[lI])\s*[.:)]+(?!\d)\s*(.*)$",
)

# OCR sometimes moves a question number to its own line and misreads ``1``
# as a lowercase L. Standalone numbers are considered questions only after
# the preceding question already has options.
QUESTION_STANDALONE_NUM_PATTERN = re.compile(r"^\s*(\d{1,4})\s*$")

SHARED_PASSAGE_PATTERN = re.compile(
    r"^\s*(?:(?:Phần|Dữ\s*kiện|Tình\s*huống)\s+)?"
    r"(?:câu\s*hỏi|các\s*câu(?:\s*hỏi)?|câu)\s+"
    r"(\d{1,4})\s*[-–—]\s*(\d{1,4})\s*[:.]\s*(.*)$",
    re.IGNORECASE,
)

# Header/footer trang đề thi & trạm thi (kết thúc câu cuối trang, tránh nối nhầm vào đáp án D)
PAGE_OR_EXAM_HEADER_PATTERN = re.compile(
    r"^(?:"
    r"\s*[\"'“(]*\s*(?:Trang|Trahe|Page|pane|rata)\s*\d*\s*(?:[/⁄]\s*\d+|-\s*(?:Mã|Ma|Mi)\b|\b\d+\s*$).*$"
    r"|\s*[\"'“($\d]*\s*[/⁄]\s*\d+\s*[-=–—]+\s*(?:Mã|Ma|Mi)\b.*$"
    r"|\s*(?:TRẠM|TRAM)\s*(?:\d+\b.*)?$"
    r"|\s*\[?\s*(?:MÃ\s*ĐỀ|MA\s*ĐỀ|MA\s*DE|MÃĐỀ|MADE|MABe|MASE|MAwe|8th\s*ĐỀ)\s*[:.]?\s*\d+.*$"
    r"|\s*[/\\~`\"']*?\s*(?:TRƯỜNG|TRƯƠNG|TRUONG|BỘ\s*MÔN|BO\s*MÔN|BO\s*MON|DỘ\s*MÔN|ĐỘ\s*MÔN"
    r"|ĐỀ\s*THI|ĐỀ\s*THỊ|DE\s*THI|DE\s*THỊ|DETHI|MÔN\s*THI|MÔN\s*THỊ|MON\s*THI|MON\s*THỊ"
    r"|ĐỐI\s*TƯỢNG|ĐÓI\s*TƯỢNG|ĐÔI\s*TƯỢNG|DOI\s*TƯỢNG|DÓI\s*TƯỢNG"
    r"|Mã\s*đề\s*thi|Ma\s*đề\s*thi|Ma\s*de\s*thi|Mi\s*dé\s*thi"
    r"|Thời\s*gian\s*làm|Thờigian\s*làm|Thai\s*gian\s*làm)\b.*$"
    r"|\s*M(?:ODULE)?\s*\d+\s*,?\s*(?:Đề|De)\s*[A-Z0-9]+\s*,?\s*"
    r"(?:NH|Năm\s*học)\s*\d{2,4}\s*[-/]\s*\d{2,4}\s*,?\s*"
    r"[A-ZĐ]{1,8}\d{1,4}\s*,?\s*(?:trang|page)\s*\d+(?:\s*/\s*\d+)?\s*$"
    r")",
    re.IGNORECASE,
)

# Footer printed at the bottom of photographed exam sheets. OCR frequently
# appends it to option D because both occupy the last visible line.
EXAM_FOOTER_SUFFIX_PATTERN = re.compile(
    r"\s+M(?:ODULE)?\s*\d+\s*,?\s*(?:Đề|De)\s*[A-Z0-9]+\s*,?\s*"
    r"(?:NH|Năm\s*học)\s*\d{2,4}\s*[-/]\s*\d{2,4}\s*,?\s*"
    r"[A-ZĐ]{1,8}\d{1,4}\s*,?\s*(?:trang|page)\s*\d+(?:\s*/\s*\d+)?\s*$",
    re.IGNORECASE,
)

# Bảng đáp án dạng cột chấm máy: "YY091602  2  46  D" (cùng dòng hoặc tách dòng)
EXAM_CODE_IN_HEADER_PATTERN = re.compile(
    r"(?:Mã\s*đề(?:\s*thi)?|Ma\s*đề(?:\s*thi)?|Ma\s*de(?:\s*thi)?)\s*[:=]\s*(\d{1,4})\b",
    re.IGNORECASE,
)
STRUCTURED_ANSWER_ROW_PATTERN = re.compile(
    r"\b[A-Z]{2,4}\d{3,8}\s+(\d{1,4})\s+(\d{1,4})\s*([A-Da-d])\b"
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
    re.compile(r"^\s*(?:BẢNG\s*)?ĐÁP\s*ÁN\s*$", re.IGNORECASE),
    re.compile(r"^\s*ANSWER\s*KEY\s*$", re.IGNORECASE),
    re.compile(r"^\s*Câu\s*\|\s*Đáp\s*án\s*$", re.IGNORECASE),
    re.compile(r"^\s*Câu\s*\|\s*ĐA\s*$", re.IGNORECASE),
    re.compile(r"^\s*STT\s*\|\s*Đáp\s*$", re.IGNORECASE),
    re.compile(r"^\s*KEY\s*:\s*$", re.IGNORECASE),
]

# Pattern nhận diện option bị tô/đánh dấu
MARKED_OPTION_BOLD = re.compile(
    r"^\s*\*{1,2}([A-Da-d])\s*[.):\-]\s*(.+?)\*{1,2}\s*$"
)
MARKED_OPTION_UNDERLINE = re.compile(
    r"^\s*_{1,2}([A-Da-d])\s*[.):\-]\s*(.+?)_{1,2}\s*$"
)
MARKED_OPTION_CHECK = re.compile(
    r"^\s*(?:[✓✔√☑]|\[x\]|\(x\))\s*([A-Da-d])\s*[.):\-]\s*(.+?)$",
    re.IGNORECASE,
)
MARKED_OPTION_CHECK_AFTER = re.compile(
    r"^\s*([A-Da-d])\s*[.):\-]\s*(?:[✓✔√☑]|\[x\]|\(x\))\s*(.+?)$",
    re.IGNORECASE,
)
MARKED_OPTION_DAPAN_PREFIX = re.compile(
    r"^\s*đáp\s*án\s*([A-Da-d])\s*[.):\-]\s*(.+?)$",
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
    5. Bảng cột chấm máy: "mamon | made | cauhoi | dapan" (theo đúng Mã đề)

    Returns: dict mapping question_number -> answer_key (uppercase)
    """
    answer_map: dict[int, str] = {}

    # Tìm vị trí bắt đầu section đáp án
    table_start = -1
    for header_pattern in ANSWER_SECTION_HEADERS:
        match = header_pattern.search(text)
        if match:
            table_start = match.start()
            break

    if table_start != -1:
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
        if len(compact_matches) >= 3:
            for m in compact_matches:
                q_num = int(m.group(1))
                answer = m.group(2).upper()
                if 1 <= q_num <= 9999:
                    answer_map[q_num] = answer
            if answer_map:
                return answer_map

    # Hỗ trợ bảng đáp án cuối PDF dạng cột (mamon | made | cauhoi | dapan)
    structured_map = _parse_structured_exam_answer_table(text)
    if structured_map:
        return structured_map

    return answer_map


def _parse_structured_exam_answer_table(text: str) -> dict[int, str]:
    """
    Đọc bảng đáp án chấm máy dạng cột (``mamon | made | cauhoi | dapan``) kể cả khi
    vài dòng bị watermark chéo làm mờ mã học phần / mã đề (``r2``, ``V2``, ``13 €``).
    """
    lines = text.splitlines()
    start_idx = -1
    for idx, ln in enumerate(lines):
        if re.match(r"^\s*mamon\b", ln, re.IGNORECASE):
            start_idx = idx
            break

    if start_idx == -1:
        code_hits = [
            idx for idx, ln in enumerate(lines)
            if STRUCTURED_ANSWER_ROW_PATTERN.search(ln)
            or re.search(r"\b[A-Za-z]{2}\w{0,2}\d{4,8}\b", ln)
        ]
        if len(code_hits) >= 5:
            start_idx = code_hits[0]

    if start_idx == -1:
        return {}

    by_exam_code: dict[str, dict[int, str]] = {}

    # 1. Các dòng đủ 4 cột trên cùng 1 hàng: "YY091602  2  46  D"
    same_line_matches = [
        m for ln in lines[start_idx:]
        for m in STRUCTURED_ANSWER_ROW_PATTERN.finditer(ln)
    ]
    if len(same_line_matches) >= 5:
        for m in same_line_matches:
            made = m.group(1)
            q_num = int(m.group(2))
            ans = m.group(3).upper()
            if 1 <= q_num <= 9999:
                by_exam_code.setdefault(made, {})[q_num] = ans

    # 2. Quét tuần tự theo dòng (xử lý bảng tách cột xuống dòng & nhiễu OCR từng ô)
    seq_by_code: dict[str, dict[int, str]] = {}
    current_made: str | None = None
    pending_made: str | None = None
    prev_q_num = 0
    saw_course_code = False
    ans_norm = {"€": "C", "G": "C", "g": "C"}

    for raw_ln in lines[start_idx:]:
        ln = raw_ln.strip()
        if not ln or re.match(r"^(?:Page|Trang)\s+\d+", ln, re.IGNORECASE):
            continue

        # Đủ 4 cột trên 1 dòng
        full_m = re.search(
            r"[A-Za-z]{1,4}\S{0,3}\d{3,8}\D*(\d)\s+(\d{1,3})\s*([A-Da-d€Gg])\b", ln
        )
        if full_m:
            current_made = full_m.group(1)
            q_num = int(full_m.group(2))
            raw_a = full_m.group(3)
            ans = ans_norm.get(raw_a, raw_a.upper())
            seq_by_code.setdefault(current_made, {})[q_num] = ans
            prev_q_num = q_num
            pending_made = None
            saw_course_code = False
            continue

        # Dòng mã môn (kể cả dính mã đề ở cuối dòng như "YY091602Ảo 2" hoặc "YY091602 v2")
        code_m = re.search(
            r"(?:[A-Za-z¥]{1,4}\S{0,3}\d{4,8}|\b\d{6}\b)(?:\s+\S*?(\d))?\s*[\"'”`]*$",
            ln,
        )
        if code_m and not re.match(r"^\d{1,3}\s*[A-Da-d€Gg]", ln):
            saw_course_code = True
            if code_m.group(1):
                pending_made = code_m.group(1)
            continue

        # Dòng mã đề đứng riêng ("1", "2", "r2", "V2", "v2", "„€1")
        made_m = re.match(r"^[^0-9A-Da-d]{0,3}[rRvV]?([1-9])\s*$", ln)
        if made_m and (saw_course_code or prev_q_num >= 40 or current_made is None):
            pending_made = made_m.group(1)
            continue

        # Dòng "cauhoi + dapan": "1A", "16 C", "13 €", "7G", "19 BS", "60 Cce"
        qa_m = re.match(r"^(\d{1,3})\s*([A-Da-d€Gg])(?:[A-Za-z]{0,2})?\s*[\"'”`w]*$", ln)
        if qa_m:
            q_num = int(qa_m.group(1))
            if not (1 <= q_num <= 300):
                continue
            raw_a = qa_m.group(2)
            ans = ans_norm.get(raw_a, raw_a.upper())
            if ans not in {"A", "B", "C", "D"}:
                continue

            if prev_q_num > 0 and q_num < prev_q_num - 2:
                if pending_made:
                    current_made = pending_made
                elif current_made and current_made.isdigit():
                    current_made = str(int(current_made) + 1)
                else:
                    current_made = "2"
            elif current_made is None:
                current_made = pending_made or "1"

            seq_by_code.setdefault(current_made, {})[q_num] = ans
            prev_q_num = q_num
            pending_made = None
            saw_course_code = False

    if sum(len(v) for v in seq_by_code.values()) > sum(len(v) for v in by_exam_code.values()):
        by_exam_code = seq_by_code

    if not by_exam_code:
        return {}

    if len(by_exam_code) == 1:
        return next(iter(by_exam_code.values()))

    header_slice = "\n".join(lines[:start_idx]) if start_idx > 0 else text
    code_match = (
        EXAM_CODE_IN_HEADER_PATTERN.search(header_slice)
        or EXAM_CODE_IN_HEADER_PATTERN.search(text)
    )
    if code_match and code_match.group(1) in by_exam_code:
        return by_exam_code[code_match.group(1)]

    return max(by_exam_code.values(), key=len)


def _detect_marked_answer(options: list[dict], raw_lines: list[str]) -> str:
    """
    Phát hiện đáp án đã được tô/đánh dấu sẵn trong options.

    Nhận diện các dạng:
    - In đậm: **A. text** hoặc __A. text__
    - Dấu tích: ✓A. text, √A. text, ✔A. text, [x]A. text
    - Dấu tích sau key: A. ✓ text
    """
    for line in raw_lines:
        stripped = line.strip()
        if not stripped:
            continue

        m = MARKED_OPTION_BOLD.match(stripped)
        if m:
            return m.group(1).upper()

        m = MARKED_OPTION_UNDERLINE.match(stripped)
        if m:
            return m.group(1).upper()

        m = MARKED_OPTION_CHECK.match(stripped)
        if m:
            return m.group(1).upper()

        m = MARKED_OPTION_CHECK_AFTER.match(stripped)
        if m:
            return m.group(1).upper()

        m = MARKED_OPTION_DAPAN_PREFIX.match(stripped)
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
    option_starts = []
    for m in re.finditer(
        r"(?:^|\s)(?:đáp\s*án\s*)?([A-Da-d€])\s*[.):\-]\s*", line, re.IGNORECASE
    ):
        raw_k = m.group(1)
        key = "C" if raw_k == "€" else raw_k.upper()
        if key in {"A", "B", "C", "D"}:
            # A repeated letter or a sentence-final group name is content,
            # e.g. 'A. ... liên cầu A.' must retain the final 'A.'.
            if any(start["key"] == key for start in option_starts):
                continue
            if not line[m.end():].strip():
                continue
            if re.search(r"(?i)\b(?:vitamin|nhóm|liên cầu|type|typ|típ|loại)\s*$", line[:m.start()]):
                continue
            option_starts.append({
                "key": key,
                "pos": m.end(),
                "match_start": m.start(),
            })

    if len(option_starts) < 2:
        return []

    for i, opt_info in enumerate(option_starts):
        start = opt_info["pos"]
        end = option_starts[i + 1]["match_start"] if i + 1 < len(option_starts) else len(line)
        text = line[start:end].strip()
        if text:
            options.append({"key": opt_info["key"], "text": text})

    return options


def _split_compacted_option(
    key: str,
    text: str,
    seen_keys: set[str],
) -> list[dict]:
    """Split option labels that OCR merged into the preceding option.

    Examples from scanned medical exams::

        B. Cấy dịch khớp xác định liên cầu C xét nghiệm máu ASLO
        A Mycobacterium tuberculosis B Corynebacterium diphtheriae

    Only a missing next key (A → B → C → D) is eligible. Call after collecting
    the entire question so e.g. 'vitamin C' cannot steal a later explicit C.
    """
    options: list[dict] = []
    current_key = key.upper()
    remaining = text.strip()
    known_keys = {item.upper() for item in seen_keys}

    while current_key in {"A", "B", "C", "D"}:
        next_key = chr(ord(current_key) + 1)
        if next_key > "D" or next_key in known_keys:
            break

        # The separator after the compressed label may be punctuation or just
        # one space. Require text after it so a trailing "C" is not split.
        marker = re.search(
            rf"\s+{next_key}(?:\s*[.):\-]\s*|\s+)(?=\S)",
            remaining,
        )
        if not marker:
            break

        before = remaining[:marker.start()].strip()
        after = remaining[marker.end():].strip()
        if len(before) < 2 or len(after) < 2:
            break
        # These letters are common parts of medical names, not option labels.
        if re.search(r"(?i)\b(?:vitamin|nhóm|type|typ|típ|loại|hạng|độ)\s*$", before):
            break

        options.append({"key": current_key, "text": before})
        known_keys.add(current_key)
        current_key = next_key
        remaining = after

    # Keep a label-only option (``A.`` on one line, text on the next): the
    # line-by-line parser will append the following text to it.
    if remaining or not options:
        options.append({"key": current_key, "text": remaining})
    return options


def _parse_line_by_line(text: str, answer_map: dict[int, str]) -> list[dict]:
    """
    Quét từng dòng để tìm và xây dựng câu hỏi.
    """
    lines = text.split("\n")
    has_explicit_prefix = (
        sum(1 for ln in lines if QUESTION_PREFIX_PATTERN.match(ln.strip())) >= 3
    )
    questions = []
    current_q_num = 0
    current_q_text = ""
    current_options = []
    current_answer = ""
    current_option_raw_lines = []
    current_uses_numeric_options = False
    shared_range = None
    shared_lines = []
    collecting_shared = False

    def _save_current():
        """Lưu câu hỏi hiện tại nếu hợp lệ."""
        nonlocal current_q_text, current_options, current_answer, current_q_num, current_option_raw_lines, current_uses_numeric_options
        if current_q_text and current_options:
            known_keys = {o["key"] for o in current_options}
            expanded = []
            for option in current_options:
                parts = _split_compacted_option(option["key"], option["text"], known_keys)
                expanded.extend(parts)
                known_keys.update(p["key"] for p in parts)
            current_options = expanded
        if current_q_text and len(current_options) >= 2:
            # Nếu câu hỏi xuống dòng ngay trước "B. Đánh giá...:" rồi mới tới A, C, B, D thật
            while (
                len(current_options) >= 4
                and current_options[0]["key"] != "A"
                and any(o["key"] == "A" for o in current_options[1:])
                and sum(1 for o in current_options if o["key"] == current_options[0]["key"]) >= 2
            ):
                stem_tail = current_options.pop(0)
                current_q_text = f"{current_q_text} {stem_tail['key']}. {stem_tail['text']}".strip()

            # Nếu có đúng 4 dòng phương án nhưng 1 chữ cái bị OCR nhầm trùng (vd: [A, C, D, D] thiếu B)
            if len(current_options) == 4:
                raw_keys = [o["key"] for o in current_options]
                unique_valid = {k for k in raw_keys if k in {"A", "B", "C", "D"}}
                missing_keys = sorted({"A", "B", "C", "D"} - unique_valid)
                if len(unique_valid) == 3 and len(missing_keys) == 1:
                    missing_k = missing_keys[0]
                    dup_k = next(k for k in raw_keys if raw_keys.count(k) == 2)
                    dup_indices = [idx for idx, k in enumerate(raw_keys) if k == dup_k]
                    replace_idx = dup_indices[0] if missing_k < dup_k else dup_indices[1]
                    current_options[replace_idx]["key"] = missing_k

            cleaned = _strip_trailing_ocr_crumbs(_clean_question_text(current_q_text))
            if cleaned and len(cleaned) >= 3:
                seen_keys = set()
                final_opts = []
                for opt in current_options:
                    opt_text = _strip_trailing_ocr_crumbs(opt["text"])
                    if opt["key"] not in seen_keys and opt["key"] in {"A", "B", "C", "D"} and opt_text:
                        seen_keys.add(opt["key"])
                        final_opts.append({"key": opt["key"], "text": opt_text})

                if len(final_opts) >= 2:
                    # Fallback: Nếu thiếu option A (bị dính vào cuối câu hỏi)
                    if final_opts[0]["key"] == "B" and "A" not in seen_keys:
                        m = re.search(
                            r"(?:^|\s)(?:đáp\s*án\s*)?[Aa]\s*[.):\-]?\s+([A-ZĐ0-9].*)$",
                            cleaned,
                            re.IGNORECASE,
                        )
                        if m:
                            opt_a_text = m.group(1).strip()
                            cleaned = cleaned[:m.start()].strip()
                            final_opts.insert(0, {"key": "A", "text": opt_a_text})

                    # Chuẩn hoá thứ tự A, B, C, D (đề thi 2 cột khi OCR thường đọc A, C, B, D)
                    final_opts.sort(key=lambda opt: opt["key"])

                    answer = current_answer
                    if not answer:
                        answer = _detect_marked_answer(final_opts, current_option_raw_lines)
                    if not answer and current_q_num in answer_map:
                        answer = answer_map[current_q_num]

                    questions.append({
                        "question_text": (
                            " ".join(shared_lines) + "\n\n" + cleaned
                            if shared_range and shared_range[0] <= current_q_num <= shared_range[1]
                            and shared_lines else cleaned
                        ),
                        "options": final_opts[:4],
                        "correct_answer": answer,
                        "explanation": "",
                    })

        current_q_text = ""
        current_options = []
        current_answer = ""
        current_q_num = 0
        current_option_raw_lines = []
        current_uses_numeric_options = False

    for line_idx, line in enumerate(lines):
        stripped = line.strip()
        original_stripped = stripped
        stripped = re.sub(r"^\*{1,2}|\*{1,2}$", "", stripped).strip()
        stripped = re.sub(r"^_{1,2}|_{1,2}$", "", stripped).strip()
        if not stripped:
            continue

        shared_match = SHARED_PASSAGE_PATTERN.match(stripped)
        if shared_match and int(shared_match.group(1)) <= int(shared_match.group(2)):
            _save_current()
            shared_range = (int(shared_match.group(1)), int(shared_match.group(2)))
            shared_lines = [shared_match.group(3).strip()] if shared_match.group(3).strip() else []
            collecting_shared = True
            continue

        if collecting_shared:
            if not (QUESTION_PREFIX_PATTERN.match(stripped) or QUESTION_NUM_PATTERN.match(stripped)):
                if not PAGE_OR_EXAM_HEADER_PATTERN.match(stripped):
                    shared_lines.append(stripped)
                continue
            collecting_shared = False

        # A numbered option can look like a question prefix when options use 1-4.
        numeric_option_match = NUMERIC_OPTION_PATTERN.match(stripped)
        is_first_numeric_option = (
            numeric_option_match
            and numeric_option_match.group(1) == "1"
            and current_q_num > 0
            and bool(current_q_text)
            and not current_options
        )
        is_following_numeric_option = (
            numeric_option_match
            and current_uses_numeric_options
            and len(current_options) < 4
        )
        if is_first_numeric_option or is_following_numeric_option:
            current_uses_numeric_options = True
            option_number = int(numeric_option_match.group(1))
            current_options.append({
                "key": chr(ord("A") + option_number - 1),
                "text": numeric_option_match.group(2).strip(),
            })
            current_option_raw_lines.append(original_stripped)
            continue

        # ---- 1. Check: dòng này là ĐẦU CÂU HỎI MỚI? ----
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
            q_match = QUESTION_NUM_PATTERN.match(stripped)
            if q_match:
                raw_num = q_match.group(1)
                remaining = q_match.group(2).strip()
                seen_opt_keys = {o["key"] for o in current_options}
                if raw_num in ("l", "I"):
                    if current_q_num > 0 and {"A", "B", "C"}.issubset(seen_opt_keys) and "D" not in seen_opt_keys:
                        current_options.append({"key": "D", "text": remaining})
                        current_option_raw_lines.append(original_stripped)
                        continue
                    num = 1 if (current_q_num == 0 and not has_explicit_prefix) else 0
                elif has_explicit_prefix and current_q_num > 0:
                    # Tài liệu dùng "Câu X." rõ ràng → số trần (vd "5. Tiểu lắt nhắt" do OCR nhầm "B.")
                    # không phải đầu câu hỏi mới.
                    num = 0
                elif len(current_options) == 1 and int(raw_num) != current_q_num + 1:
                    num = 0
                else:
                    num = int(raw_num)
                if 1 <= num <= 999:
                    q_num = num
                    q_text = remaining
                    is_new_question = True

            if not is_new_question and not has_explicit_prefix:
                standalone_match = QUESTION_STANDALONE_NUM_PATTERN.match(stripped)
                if standalone_match and current_q_num > 0 and len(current_options) >= 2:
                    cand_num = int(standalone_match.group(1))
                    if current_q_num < cand_num <= current_q_num + 5:
                        q_num = cand_num
                        q_text = ""
                        is_new_question = True

        # ---- 2. Skip section headings & page headers/footers ----
        if not is_new_question:
            if PAGE_OR_EXAM_HEADER_PATTERN.match(stripped) or STRUCTURED_ANSWER_ROW_PATTERN.search(stripped):
                if len(current_options) >= 2:
                    _save_current()
                continue
            if re.match(r"^\s*mamon\b", stripped, re.IGNORECASE):
                _save_current()
                continue
            if re.match(r"^\s*[A-Za-z¥]{2,4}\S{0,2}\d{4,8}\b", stripped):
                _save_current()
                continue

            section_heading_match = re.match(
                r"^\s*(?:Chương|Bài|Phần)\s+(?:[0-9]+|[IVXLCDM]+|[A-Z])(?:\s*[:.\-]\s*|\s+|$).*$",
                stripped,
                re.IGNORECASE,
            )
            if section_heading_match and len(stripped) < 150 and not SINGLE_OPTION_PATTERN.match(stripped):
                _save_current()
                continue

        # ---- 3. Check: dòng này là ĐÁP ÁN inline? ----
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

        if is_new_question:
            _save_current()
            current_q_num = q_num

            inline_opts = _extract_options_from_line(q_text)
            if inline_opts:
                first_opt_match = re.search(
                    r"(?:^|\s)(?:đáp\s*án\s*)?[A-Da-d€]\s*[.):\-]\s*", q_text, re.IGNORECASE
                )
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

        # ---- 3b. Check: dòng chứa INLINE OPTIONS (A. x B. y ...)? ----
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

        if current_q_num > 0:
            ocr_opt = _match_ocr_option_line(stripped, {o["key"] for o in current_options})
            if ocr_opt is not None:
                key, opt_text = ocr_opt
                current_options.append({"key": key, "text": opt_text})
                current_option_raw_lines.append(original_stripped)
                continue

        # ---- 5. Dòng không match → phần tiếp theo của câu hỏi hoặc option ----
        if current_q_num > 0:
            if not current_options:
                if _is_ocr_speck_line(stripped, has_existing_text=bool(current_q_text)):
                    continue
                if current_q_text:
                    current_q_text += " " + stripped
                else:
                    current_q_text = stripped
            else:
                last_has_text = bool(current_options[-1]["text"])
                seen_opt_keys = {o["key"] for o in current_options}
                if _is_ocr_speck_line(stripped, has_existing_text=last_has_text):
                    if {"A", "B", "C", "D"}.issubset(seen_opt_keys) and last_has_text:
                        _save_current()
                    continue
                current_options[-1]["text"] = (
                    f"{current_options[-1]['text']} {stripped}".strip()
                )
                current_option_raw_lines.append(original_stripped)

    _save_current()
    return questions


# ============================================
# Helpers
# ============================================

def _match_ocr_option_line(stripped: str, seen_keys: set[str]) -> tuple[str, str] | None:
    """
    Nhận diện dòng phương án bị nhiễu khi OCR đề scan (dấu phẩy/gạch dưới thay dấu chấm,
    ký tự ``€.`` thay cho ``C.``, mảnh watermark dính trước chữ cái A-D).
    Chỉ gọi khi đang ở bên trong một câu hỏi (``current_q_num > 0``).
    """
    # 1. Ký hiệu Euro "€." / "-€" / "Res €." là lỗi nhận dạng kinh điển của "C." khi vướng nét gạch
    m = re.match(
        r"^(?:[A-Za-zÀ-ỹ]{1,4}\s+|[\"'“”‘’(\[{<>^&_+.\-–—•·©®°«»~`\s]+)*€\s*[.):,_\-]?\s*(.+)$",
        stripped,
    )
    if m and "C" not in seen_keys:
        return "C", m.group(1).strip()

    # 2. Dấu phẩy hoặc gạch dưới ngay sau chữ hoa A-D: "A, 3,5-3,8", "B_Nóng bụng", "D, Misoprostol"
    m = re.match(r"^([A-D])\s*[,_]\s*(.+)$", stripped)
    if m:
        return m.group(1), m.group(2).strip()

    # 3. Ký tự nhiễu / số đơn watermark đứng trước "A. text" (vd: ".cC. ...", "7 D. ...", "& D. ...", "« A. ...")
    m = re.match(
        r"^(?:"
        r"[.\"'“”‘’(\[{<>^&_+\-–—•·©®°«»~`\s]+"
        r"|[0-9]\s+"
        r"|[.\"'“”‘’(\[{<>^&_+\-–—•·©®°«»~`]*[A-Za-zÀ-ỹ]{1,3}[.\"'“”‘’(\[{<>^&_+\-–—•·©®°«»~`\s]+"
        r"|[.\"'“”‘’(\[{<>^&_+\-–—•·©®°«»~`]*[oO0cC]\s*"
        r")([A-D])\s*[.):,_\-]+[\s.,]*(.+)$",
        stripped,
    )
    if m:
        return m.group(1), m.group(2).strip()

    # 4. "Cc. <0,9", "oo. Tiểu đục", "oe. Giai đoạn 3a", "re. Giai đoạn 3a", "ae Tiểu đục" khi đang thiếu C
    m = re.match(r"^(?:[Cc]{2}|[oOrRaA][oOeEcC])\s*[.):,\-\s]\s*(.+)$", stripped)
    if m and "C" not in seen_keys and ("A" in seen_keys or "B" in seen_keys):
        return "C", m.group(1).strip()

    # 5. Đã có A mà dòng B bị OCR nhầm chữ "B." thành "E." / "5." / "8." / "99." (vd: "E.RDW", "5. Tiểu...", "99.3")
    if "A" in seen_keys and "B" not in seen_keys:
        m = re.match(r"^(?:E|[58]|99)\s*[.):,]\s*(\S.*)$", stripped)
        if m:
            return "B", m.group(1).strip()

    # 6. Chưa có phương án nào mà gặp "Al" / "A1" (OCR nhầm "A. 1")
    if not seen_keys and re.match(r"^A[lI1]$", stripped):
        return "A", "1"

    # 7. Thiếu dấu chấm sau chữ hoa B/C/D khi đã có A (vd: "C4", "C3", "CI", "Ds" -> D: 5)
    if "A" in seen_keys:
        if stripped == "Ds" and "D" not in seen_keys and "C" in seen_keys:
            return "D", "5"
        m = re.match(r"^([B-D])(\d+(?:\s+\S.*)?|[IVX]{1,4}|[A-ZÀ-Ỹ][a-zà-ỹ]+.*)$", stripped)
        if m and m.group(1) not in seen_keys:
            return m.group(1), m.group(2).strip()

    return None


def _is_ocr_speck_line(stripped: str, has_existing_text: bool) -> bool:
    """Phát hiện mảnh rác ngắn do watermark chéo / viền trang khi OCR đề scan."""
    if not any(ch.isalnum() for ch in stripped):
        return True
    if re.search(r"[Ø©®]{2,}|(?:\bØ\s*){2,}", stripped):
        return True
    if not has_existing_text:
        return False
    if len(stripped) <= 3 and not stripped.endswith(":"):
        return True
    if len(stripped) <= 6 and re.search(r"[©®°™¤§¨¬¯±²³´¶¸º»¼½¾¿×÷|<>~`^„”]", stripped):
        return True
    return False


def _strip_trailing_ocr_crumbs(text: str) -> str:
    """Loại bỏ mảnh rác watermark ngắn bám ở cuối câu hỏi hoặc cuối phương án."""
    if not text:
        return ""
    text = EXAM_FOOTER_SUFFIX_PATTERN.sub("", text)
    text = re.sub(r"\s+\d*th\s*ĐỀ\s*:\s*\d+(?:\s+\d+)?\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*(?:—|–|-)\s*(?:OS|vÒ`|[<>¿©®°`\"'~]{1,4})\s*$", "", text)
    text = re.sub(r"\s*[©®°„”`~<>]{2,}\s*$", "", text)
    text = re.sub(r"(?<=:)\s+(?:i\s+Ke|[„\"'~`]+\d*|>)\s*$", "", text)
    return text.strip()


def _clean_question_text(text: str) -> str:
    """Làm sạch text câu hỏi: bỏ prefix số, normalize whitespace."""
    text = re.sub(
        r"^\s*[\"'“”‘’(\[{<>^_+\-–—•·«»~`]*\s*"
        r"(?:(?:(?i:c?(?:câu|cau)|question|q)|C(?:lu|ầu|ân|ău|áu|àu|ẫu|â0|a0)))?"
        r"[\s:`'´]*\d{1,4}\s*[.:),;\-]?\s*",
        "",
        text,
    )
    text = re.sub(r"\s+", " ", text).strip()
    return text
