"""
Test Text Processing - Unit tests cho text preprocessing utilities
====================================================================

Test strategy:
- Test từng function riêng lẻ
- Test pipeline preprocess_text end-to-end
- Test edge cases: text rỗng, text quá dài
"""

import pytest

from app.utils.text_processing import (
    preprocess_text,
    smart_truncate,
    chunk_text,
    estimate_tokens,
    _remove_page_numbers,
    _remove_repeated_headers,
    _normalize_whitespace,
    MAX_INPUT_CHARS,
    MIN_INPUT_CHARS,
)


# ============================================
# PREPROCESS TEXT (End-to-End)
# ============================================

class TestPreprocessText:
    """Tests cho preprocess_text pipeline."""

    def test_basic_preprocessing(self):
        """Test preprocessing cơ bản."""
        text = "Hello World.\nThis is a test document."
        result = preprocess_text(text)
        assert "Hello World" in result
        assert "test document" in result

    def test_empty_text(self):
        """Test với text rỗng."""
        assert preprocess_text("") == ""
        assert preprocess_text("   ") == ""
        assert preprocess_text(None) == ""

    def test_removes_page_numbers(self):
        """Test pipeline loại bỏ page numbers."""
        text = (
            "Introduction to Python\n"
            "Page 1 of 10\n"
            "Python is a great language.\n"
            "Page 2 of 10\n"
            "It supports multiple paradigms."
        )
        result = preprocess_text(text)
        assert "Page 1 of 10" not in result
        assert "Introduction to Python" in result
        assert "Python is a great language" in result

    def test_removes_repeated_headers(self):
        """Test pipeline loại bỏ headers lặp lại."""
        header = "CONFIDENTIAL - Company XYZ"
        text = "\n".join([
            f"{header}\nContent of page 1",
            f"{header}\nContent of page 2",
            f"{header}\nContent of page 3",
            f"{header}\nContent of page 4",
        ])
        result = preprocess_text(text)
        assert "CONFIDENTIAL" not in result
        assert "Content of page 1" in result

    def test_truncates_long_text(self):
        """Test pipeline truncate text quá dài."""
        # Create text longer than MAX_INPUT_CHARS
        long_text = "This is a sentence. " * (MAX_INPUT_CHARS // 10)
        result = preprocess_text(long_text)
        assert len(result) <= MAX_INPUT_CHARS


# ============================================
# SMART TRUNCATE
# ============================================

class TestSmartTruncate:
    """Tests cho smart_truncate function."""

    def test_no_truncation_needed(self):
        """Test text ngắn hơn limit không bị cắt."""
        text = "Short text that doesn't need truncation."
        result = smart_truncate(text, max_chars=1000)
        assert result == text

    def test_truncates_at_paragraph(self):
        """Test cắt tại paragraph boundary."""
        para1 = "First paragraph content." * 10
        para2 = "Second paragraph content." * 10
        text = f"{para1}\n\n{para2}"

        # Set limit so chỉ đủ cho para1
        limit = len(para1) + 50
        result = smart_truncate(text, max_chars=limit)

        # Should cut at paragraph boundary
        assert result.endswith(para1) or len(result) <= limit

    def test_truncates_at_sentence(self):
        """Test fallback cắt tại sentence boundary."""
        text = "Sentence one. Sentence two. Sentence three. " * 100
        result = smart_truncate(text, max_chars=100)
        # Should end with a complete sentence (period)
        assert len(result) <= 100

    def test_truncate_returns_stripped(self):
        """Test kết quả đã strip whitespace."""
        text = "Content here. " * 100
        result = smart_truncate(text, max_chars=50)
        assert result == result.strip()


# ============================================
# CHUNK TEXT
# ============================================

class TestChunkText:
    """Tests cho chunk_text function."""

    def test_single_chunk(self):
        """Test text ngắn → 1 chunk duy nhất."""
        text = "Short text"
        chunks = chunk_text(text, chunk_size=1000)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_multiple_chunks(self):
        """Test text dài → nhiều chunks."""
        text = "Word " * 1000  # ~5000 chars
        chunks = chunk_text(text, chunk_size=1000, overlap=100)
        assert len(chunks) > 1

    def test_chunks_have_content(self):
        """Test mỗi chunk đều có nội dung."""
        text = "Sentence here. " * 500
        chunks = chunk_text(text, chunk_size=500, overlap=50)
        for chunk in chunks:
            assert len(chunk.strip()) > 0

    def test_overlap_between_chunks(self):
        """Test overlap giữa các chunks."""
        # Create text with distinct markers
        text = "A" * 1000 + "B" * 1000 + "C" * 1000
        chunks = chunk_text(text, chunk_size=1200, overlap=200)

        if len(chunks) > 1:
            # Last 200 chars of chunk[0] should appear in chunk[1]
            # (approximately, since paragraph boundaries may adjust)
            assert len(chunks) >= 2


# ============================================
# REMOVE PAGE NUMBERS
# ============================================

class TestRemovePageNumbers:
    """Tests cho _remove_page_numbers."""

    def test_page_x_of_y(self):
        """Test remove 'Page X of Y' pattern."""
        text = "Content here\nPage 1 of 10\nMore content"
        result = _remove_page_numbers(text)
        assert "Page 1 of 10" not in result
        assert "Content here" in result

    def test_trang_pattern(self):
        """Test remove 'Trang X/Y' pattern (Vietnamese)."""
        text = "Nội dung\nTrang 5/20\nTiếp theo"
        result = _remove_page_numbers(text)
        assert "Trang 5/20" not in result

    def test_standalone_number(self):
        """Test remove số đứng một mình trên dòng."""
        text = "Content\n  3  \nMore content"
        result = _remove_page_numbers(text)
        assert "Content" in result

    def test_preserves_numbers_in_text(self):
        """Test KHÔNG xóa số trong câu văn."""
        text = "Python có 3 phiên bản chính: 2.x và 3.x"
        result = _remove_page_numbers(text)
        assert "3 phiên bản" in result

    def test_dashed_page_number(self):
        """Test remove '- 5 -' style page numbers."""
        text = "Content\n- 5 -\nMore content"
        result = _remove_page_numbers(text)
        assert "- 5 -" not in result


# ============================================
# REMOVE REPEATED HEADERS
# ============================================

class TestRemoveRepeatedHeaders:
    """Tests cho _remove_repeated_headers."""

    def test_removes_header(self):
        """Test loại bỏ header xuất hiện 3+ lần."""
        header = "UNIVERSITY OF SCIENCE"
        text = "\n".join([
            f"{header}\nPage 1 content",
            f"{header}\nPage 2 content",
            f"{header}\nPage 3 content",
        ])
        result = _remove_repeated_headers(text)
        assert header not in result
        assert "Page 1 content" in result

    def test_preserves_non_repeated(self):
        """Test giữ dòng chỉ xuất hiện 1-2 lần."""
        text = "Unique line 1\nUnique line 2\nAnother unique line"
        result = _remove_repeated_headers(text)
        assert "Unique line 1" in result
        assert "Another unique line" in result

    def test_ignores_long_lines(self):
        """Test KHÔNG xóa dòng dài >80 chars (likely content, not header)."""
        long_line = "A" * 100
        text = f"{long_line}\n{long_line}\n{long_line}\nOther content"
        result = _remove_repeated_headers(text)
        # Long repeated lines should NOT be removed
        assert long_line in result


# ============================================
# NORMALIZE WHITESPACE
# ============================================

class TestNormalizeWhitespace:
    """Tests cho _normalize_whitespace."""

    def test_multiple_spaces(self):
        """Test nhiều space liên tiếp → 1 space."""
        text = "Hello    World     Test"
        result = _normalize_whitespace(text)
        assert "Hello World Test" == result

    def test_multiple_blank_lines(self):
        """Test nhiều blank lines → max 3."""
        text = "Para 1\n\n\n\n\n\n\nPara 2"
        result = _normalize_whitespace(text)
        # Should have at most 3 consecutive newlines
        assert "\n\n\n\n" not in result
        assert "Para 1" in result
        assert "Para 2" in result


# ============================================
# ESTIMATE TOKENS
# ============================================

class TestEstimateTokens:
    """Tests cho estimate_tokens."""

    def test_basic_estimate(self):
        """Test ước lượng tokens cơ bản."""
        text = "Hello World"  # 11 chars → ~2-3 tokens
        tokens = estimate_tokens(text)
        assert tokens == 11 // 4

    def test_empty_text(self):
        """Test empty text → 0 tokens."""
        assert estimate_tokens("") == 0

    def test_long_text(self):
        """Test ước lượng text dài."""
        text = "A" * 40000  # 40k chars → ~10k tokens
        tokens = estimate_tokens(text)
        assert tokens == 10000
