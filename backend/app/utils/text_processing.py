"""
Text Processing Utilities - Tiền xử lý và chunking văn bản
=============================================================

Tại sao cần preprocessing?
1. Text extract từ PDF thường có noise (header/footer lặp, page numbers)
2. Gemini có context window giới hạn → phải truncate/chunk nếu text quá dài
3. Text quá ngắn → không đủ chất liệu tạo câu hỏi → cần validate

Strategy cho text dài:
- Nếu text ≤ context limit → gửi nguyên block
- Nếu text > context limit → smart truncate theo paragraph boundaries
  (Giữ nguyên ý nghĩa, không cắt giữa câu)

Tại sao KHÔNG dùng tiktoken?
- tiktoken là tokenizer của OpenAI, không chính xác cho Gemini
- Gemini tokenizer khác → dùng ước lượng: ~4 chars ≈ 1 token
- Đủ chính xác cho mục đích truncation
"""

import re


# ============================================
# CONSTANTS
# ============================================

# Gemini 2.0 Flash context window: ~1M tokens
# Nhưng ta giới hạn input text ở mức an toàn hơn
# để chừa cho system prompt + response
MAX_INPUT_CHARS = 120_000  # ~30k tokens (ước lượng 4 chars/token)
MIN_INPUT_CHARS = 100       # Tối thiểu để tạo câu hỏi có ý nghĩa


def preprocess_text(text: str) -> str:
    """
    Tiền xử lý text trước khi gửi cho AI.

    Pipeline:
    1. Remove page numbers & headers/footers lặp lại
    2. Normalize whitespace
    3. Truncate nếu vượt limit

    Args:
        text: Raw text đã extract từ file

    Returns:
        Cleaned, truncated text sẵn sàng cho AI
    """
    if not text or not text.strip():
        return ""

    # Step 1: Remove common noise patterns
    text = _remove_page_numbers(text)
    text = _remove_repeated_headers(text)

    # Step 2: Normalize whitespace
    text = _normalize_whitespace(text)

    # Step 3: Smart truncate nếu vượt limit
    if len(text) > MAX_INPUT_CHARS:
        text = smart_truncate(text, MAX_INPUT_CHARS)

    return text.strip()


def smart_truncate(text: str, max_chars: int = MAX_INPUT_CHARS) -> str:
    """
    Cắt text thông minh theo paragraph boundaries.

    Thay vì cắt cứng tại vị trí max_chars (có thể gãy giữa câu),
    tìm paragraph boundary gần nhất và cắt tại đó.

    Args:
        text: Text cần truncate
        max_chars: Giới hạn ký tự

    Returns:
        Truncated text, kết thúc tại paragraph boundary
    """
    if len(text) <= max_chars:
        return text

    # Cắt thô tại max_chars
    truncated = text[:max_chars]

    # Tìm paragraph boundary cuối cùng (double newline)
    last_para = truncated.rfind("\n\n")
    if last_para > max_chars * 0.7:  # Nếu boundary ở 70%+ text → accept
        truncated = truncated[:last_para]
    else:
        # Fallback: tìm sentence boundary (dấu chấm + space/newline)
        last_sentence = truncated.rfind(". ")
        if last_sentence > max_chars * 0.8:
            truncated = truncated[:last_sentence + 1]
        # Nếu không tìm được boundary tốt → giữ nguyên cắt thô

    return truncated.strip()


def chunk_text(text: str, chunk_size: int = MAX_INPUT_CHARS, overlap: int = 500) -> list[str]:
    """
    Chia text thành nhiều chunks với overlap.

    Dùng khi text quá dài, cần gọi AI nhiều lần
    rồi merge kết quả.

    Args:
        text: Text cần chia
        chunk_size: Kích thước mỗi chunk (ký tự)
        overlap: Số ký tự overlap giữa các chunks (tránh mất context)

    Returns:
        List of text chunks
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end < len(text):
            # Tìm paragraph boundary để cắt
            chunk = text[start:end]
            last_para = chunk.rfind("\n\n")
            if last_para > chunk_size * 0.5:
                end = start + last_para
        
        chunks.append(text[start:end].strip())
        start = end - overlap  # Overlap để giữ context

    # Bỏ chunk cuối nếu quá ngắn
    if len(chunks) > 1 and len(chunks[-1]) < MIN_INPUT_CHARS:
        chunks.pop()

    return chunks


def estimate_tokens(text: str) -> int:
    """
    Ước lượng số tokens của text.

    Rule of thumb: 1 token ≈ 4 characters (cho tiếng Anh).
    Tiếng Việt có dấu nên tỉ lệ khác, nhưng đủ chính xác
    cho mục đích giới hạn input.
    """
    return len(text) // 4


# ============================================
# Private helpers
# ============================================

def _remove_page_numbers(text: str) -> str:
    """
    Loại bỏ page numbers phổ biến trong PDF.

    Patterns xử lý:
    - "Page 1 of 10", "Trang 5/20"
    - Số đứng một mình trên dòng: "  3  "
    - "- 5 -" (kiểu page number dashed)
    """
    # Pattern: "Page X of Y" hoặc "Trang X/Y"
    text = re.sub(r"(?i)(page|trang)\s+\d+\s*(of|/|trên)\s*\d+", "", text)

    # Pattern: Số đứng một mình trên dòng (likely page number)
    # Chỉ match nếu dòng chỉ có số, max 4 chữ số (tránh remove data thật)
    text = re.sub(r"^\s*\d{1,4}\s*$", "", text, flags=re.MULTILINE)

    # Pattern: "- 5 -" style page numbers
    text = re.sub(r"^\s*[-–—]\s*\d+\s*[-–—]\s*$", "", text, flags=re.MULTILINE)

    return text


def _remove_repeated_headers(text: str) -> str:
    """
    Detect và remove header/footer lặp lại giữa các page.

    Strategy: Tìm dòng ngắn (<80 chars) xuất hiện >= 3 lần
    → likely là header/footer → remove.
    """
    lines = text.split("\n")
    line_counts: dict[str, int] = {}

    for line in lines:
        stripped = line.strip()
        if stripped and len(stripped) < 80:
            line_counts[stripped] = line_counts.get(stripped, 0) + 1

    # Các dòng xuất hiện >= 3 lần → header/footer
    repeated = {
        line for line, count in line_counts.items()
        if count >= 3
    }

    if not repeated:
        return text

    filtered_lines = [
        line for line in lines
        if line.strip() not in repeated
    ]

    return "\n".join(filtered_lines)


def _normalize_whitespace(text: str) -> str:
    """Normalize whitespace: bỏ multiple spaces, multiple blank lines."""
    # Multiple spaces → single space (trong cùng dòng)
    text = re.sub(r"[^\S\n]+", " ", text)

    # Multiple blank lines → max 2
    text = re.sub(r"\n{4,}", "\n\n\n", text)

    return text
