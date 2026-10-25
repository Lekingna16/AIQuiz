"""
Text Extraction Service - Trích xuất văn bản từ file upload
=============================================================

Hỗ trợ 3 định dạng:
- PDF: dùng PyMuPDF (fitz) — nhanh, chính xác, hỗ trợ Unicode/tiếng Việt tốt
       + Nhận diện đáp án tô đậm / tô màu / highlight trong PDF gốc
       + OCR tự động cho trang scan, ảnh chụp đề thi đưa vào PDF, và PDF lai (chữ + ảnh)
- DOCX: dùng python-docx — đọc paragraphs + tables THEO ĐÚNG THỨ TỰ trong file,
        khôi phục đánh số tự động (1., A., B., C., D. từ numbering.xml),
        bảng phương án 2x2/1x4, text box, công thức toán (OMML), nhận diện đáp án
        in đậm/gạch chân/highlight/đổi màu, và OCR ảnh chèn trong Word
- TXT: ưu tiên UTF-8/UTF-16 BOM + chardet để tự detect encoding

Flow:
  file_bytes + file_type → extract_document() → ExtractionResult (các segment)
                         → (tuỳ chọn) OCR fallback bằng Gemini cho ảnh chưa đọc được
                         → finalize_text() → cleaned plain text
  extract() = extract_document() + finalize_text() (đồng bộ, dùng OCR cục bộ)

Phân loại hình học từng trang PDF:
- "text"  : trang có lớp chữ tốt và không có vùng ảnh thiếu chữ → lấy text gốc
- "scan"  : trang chỉ có ảnh / ảnh scan (kể cả có watermark CamScanner/số trang)
            hoặc lớp chữ OCR cũ bị hỏng → OCR toàn trang
- "mixed" : trang vừa có chữ gốc vừa có ảnh nội dung chưa có lớp chữ → giữ text gốc,
            OCR từng cụm ảnh và ghép theo đúng thứ tự toạ độ (y, x) trên trang
- "empty" : trang trắng → bỏ qua
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from io import BytesIO

import chardet
import fitz  # PyMuPDF
from docx import Document
from docx.oxml.ns import qn

from app.services.ocr_service import LocalOCREngine

logger = logging.getLogger(__name__)


# Common footer/watermark left by document-sharing sites and mobile scanner apps.
WATERMARK_LINE_PATTERN = re.compile(
    r"(?:"
    r"^\s*downloaded\s+by\b"
    r"|lomoarcpsd\|"
    r"|\bstudocu\b"
    r"|^\s*scan\s+to\s+open\b"
    r"|^\s*scanned\s+(?:by|with)\s+(?:camscanner|tapscanner|fastscanner|clearscanner|vflat)\b"
    r"|^\s*camscanner\s*$"
    r"|^\s*cs\s+scanned\s+with\s+camscanner\b"
    r")",
    re.IGNORECASE,
)

# Standalone page number lines (ignored when deciding whether a scanned page already has text)
_TRIVIAL_PAGE_NO_LINE = re.compile(
    r"^\s*(?:(?:page|trang)\s*\d+(?:\s*(?:of|/|trên)\s*\d+)?|[-–—]?\s*\d{1,4}\s*[-–—]?)\s*$",
    re.IGNORECASE,
)

# A number embedded inside a Vietnamese word is a strong signal that the PDF
# contains a damaged OCR text layer (for example, ``ntr6c`` instead of
# ``nước``). Ordinary numbering such as ``Câu 10`` does not match.
OCR_DAMAGE_PATTERN = re.compile(
    r"(?iu)\b[^\W\d_]+\d+[^\W\d_]+\b|\b(?:ntr6c|nur&c|h6a|h0i|nh6m|strc|lurong)\b"
)

# ============================================
# Legacy Vietnamese font converters (TCVN3 & VNI-Windows)
# ============================================

TCVN3_CHARS = "µ¸¶·¹¨»¾¼½Æ©ÇÊÈÉË®ÌÐÎÏÑªÒÕÓÔÖ×ÝØÜÞßãáâä«åèæçé¬êíëìîïóñòô\u00adõøö÷ùúýûüþ¡¢§£¤¥¦"
UNICODE_CHARS = "àáảãạăằắẳẵặâầấẩẫậđèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵĂÂĐÊÔƠƯ"
TCVN3_EXTRA = "\u03bc\u2212"
UNICODE_EXTRA = "àư"

tcvn3_to_unicode_map = dict(zip(TCVN3_CHARS + TCVN3_EXTRA, UNICODE_CHARS + UNICODE_EXTRA))
_TCVN3_REGEX = re.compile("|".join(map(re.escape, tcvn3_to_unicode_map.keys())))


def _is_tcvn3(text: str) -> bool:
    indicators = [
        r"[Cc]©u",               # C©u / c©u -> Câu / câu
        r"®\u2212",              # ®− -> đư
        r"l\u03bc",              # lμ -> là
        r"t\u2212\u00ebng",      # t−ëng -> tưởng
        r"tr\u2212\u00eang",     # tr−êng -> trường
        r"th\u2212\u00ebng",     # th−ëng -> thưởng
        r"®êi",                  # ®êi -> đời
        r"®©u",                  # ®©u -> đâu
    ]
    return bool(re.search("|".join(indicators), text))


def _tcvn3_to_unicode(text: str) -> str:
    return _TCVN3_REGEX.sub(lambda m: tcvn3_to_unicode_map[m.group(0)], text)


# VNI-Windows two-char sequences (base vowel + VNI diacritic/tone codepoint) -> Unicode
_VNI_PAIRS: dict[str, str] = {
    # Plain tones: ù (sắc), ø (huyền), û (hỏi), õ (ngã), ï (nặng)
    "aù": "á", "aø": "à", "aû": "ả", "aõ": "ã", "aï": "ạ",
    "AÙ": "Á", "AØ": "À", "AÛ": "Ả", "AÕ": "Ã", "AÏ": "Ạ",
    "eù": "é", "eø": "è", "eû": "ẻ", "eõ": "ẽ", "eï": "ẹ",
    "EÙ": "É", "EØ": "È", "EÛ": "Ẻ", "EÕ": "Ẽ", "EÏ": "Ẹ",
    "où": "ó", "oø": "ò", "oû": "ỏ", "oõ": "õ", "oï": "ọ",
    "OÙ": "Ó", "OØ": "Ò", "OÛ": "Ỏ", "OÕ": "Õ", "OÏ": "Ọ",
    "uù": "ú", "uø": "ù", "uû": "ủ", "uõ": "ũ", "uï": "ụ",
    "UÙ": "Ú", "UØ": "Ù", "UÛ": "Ủ", "UÕ": "Ũ", "UÏ": "Ụ",
    "yù": "ý", "yø": "ỳ", "yû": "ỷ", "yõ": "ỹ",
    "YÙ": "Ý", "YØ": "Ỳ", "YÛ": "Ỷ", "YÕ": "Ỹ",
    # ơ (ô in VNI) + tones
    "ôù": "ớ", "ôø": "ờ", "ôû": "ở", "ôõ": "ỡ", "ôï": "ợ",
    "ÔÙ": "Ớ", "ÔØ": "Ờ", "ÔÛ": "Ở", "ÔÕ": "Ỡ", "ÔÏ": "Ợ",
    # ư (ö in VNI) + tones
    "öù": "ứ", "öø": "ừ", "öû": "ử", "öõ": "ữ", "öï": "ự",
    "ÖÙ": "Ứ", "ÖØ": "Ừ", "ÖÛ": "Ử", "ÖÕ": "Ữ", "ÖÏ": "Ự",
    # Circumflex â / ê / ô: â (plain), á (sắc), à (huyền), å (hỏi), ã (ngã), ä (nặng)
    "aâ": "â", "aá": "ấ", "aà": "ầ", "aå": "ẩ", "aã": "ẫ", "aä": "ậ",
    "AÂ": "Â", "AÁ": "Ấ", "AÀ": "Ầ", "AÅ": "Ẩ", "AÃ": "Ẫ", "AÄ": "Ậ",
    "eâ": "ê", "eá": "ế", "eà": "ề", "eå": "ể", "eã": "ễ", "eä": "ệ",
    "EÂ": "Ê", "EÁ": "Ế", "EÀ": "Ề", "EÅ": "Ể", "EÃ": "Ễ", "EÄ": "Ệ",
    "oâ": "ô", "oá": "ố", "oà": "ồ", "oå": "ổ", "oã": "ỗ", "oä": "ộ",
    "OÂ": "Ô", "OÁ": "Ố", "OÀ": "Ồ", "OÅ": "Ổ", "OÃ": "Ỗ", "OÄ": "Ộ",
    # Breve ă: ê (plain), é (sắc), è (huyền), ú (hỏi), ü (ngã), ë (nặng)
    "aê": "ă", "aé": "ắ", "aè": "ằ", "aú": "ẳ", "aü": "ẵ", "aë": "ặ",
    "AÊ": "Ă", "AÉ": "Ắ", "AÈ": "Ằ", "AÚ": "Ẳ", "AÜ": "Ẵ", "AË": "Ặ",
}
# Mixed-case first capital letter (e.g. "Caâu", "Ñaùp", "Vieät", "Nöôùc")
for _k, _v in list(_VNI_PAIRS.items()):
    if len(_k) == 2 and _k.islower():
        _VNI_PAIRS[_k[0].upper() + _k[1]] = _v.upper() if False else _v
        # Capital base + lowercase VNI mark -> Capital Vietnamese vowel!
        _VNI_PAIRS[_k[0].upper() + _k[1]] = _v.upper()

_VNI_SINGLES: dict[str, str] = {
    "ñ": "đ", "Ñ": "Đ",
    "ô": "ơ", "Ô": "Ơ",
    "ö": "ư", "Ö": "Ư",
    "í": "í", "Í": "Í",
    "ì": "ì", "Ì": "Ì",
    "æ": "ỉ", "Æ": "Ỉ",
    "ó": "ĩ", "Ó": "Ĩ",
    "ò": "ị", "Ò": "Ị",
    "î": "ỵ", "Î": "Ỵ",
}
_VNI_TOKEN_REGEX = re.compile(
    "|".join(
        sorted(map(re.escape, list(_VNI_PAIRS.keys()) + list(_VNI_SINGLES.keys())), key=len, reverse=True)
    )
)
_VNI_INDICATOR_REGEX = re.compile(
    r"(?:Caâu|caâu|Ñaùp|ñaùp|Vieät|nöôùc|tröôøng|ñöôïc|nhöõng|baèng|laø\b|cuûa\b|trong\s+\w*[ùøûõï])"
)


def _is_vni(text: str) -> bool:
    return bool(text) and len(_VNI_INDICATOR_REGEX.findall(text)) >= 2


def _vni_to_unicode(text: str) -> str:
    def _sub(match: re.Match) -> str:
        tok = match.group(0)
        return _VNI_PAIRS.get(tok) or _VNI_SINGLES.get(tok, tok)

    return _VNI_TOKEN_REGEX.sub(_sub, text)


# ============================================
# Extraction result model
# ============================================

@dataclass
class TextSegment:
    """
    Một đoạn nội dung theo đúng thứ tự xuất hiện trong tài liệu.

    source:
    - "text"    : chữ đọc trực tiếp từ file (có thể cần convert TCVN3/VNI)
    - "ocr"     : chữ nhận dạng từ ảnh (luôn là Unicode)
    - "pending" : ảnh cần OCR nhưng chưa có engine cục bộ → ``image`` chứa
                  JPEG để caller gửi Gemini Vision; ``text`` là nội dung dự
                  phòng nếu OCR fallback thất bại
    """

    text: str = ""
    source: str = "text"
    image: bytes | None = None
    label: str = ""


@dataclass
class ExtractionResult:
    """Kết quả trích xuất thô (chưa clean) kèm thống kê OCR."""

    file_type: str
    segments: list[TextSegment] = field(default_factory=list)
    ocr_pages: list[int] = field(default_factory=list)   # trang PDF đã OCR (1-based)
    ocr_images: int = 0                                  # số ảnh rời / vùng ảnh đã OCR
    skipped_ocr_pages: list[int] = field(default_factory=list)

    @classmethod
    def from_text(cls, text: str, file_type: str = "txt") -> "ExtractionResult":
        return cls(file_type=file_type, segments=[TextSegment(text=text)])

    @property
    def pending_segments(self) -> list[TextSegment]:
        return [s for s in self.segments if s.source == "pending" and s.image]

    @property
    def used_ocr(self) -> bool:
        return bool(self.ocr_pages or self.ocr_images)

    def resolve_pending(self, texts: list[str]) -> None:
        """Gắn kết quả OCR fallback (cùng thứ tự với ``pending_segments``)."""
        for segment, text in zip(self.pending_segments, texts):
            if text and text.strip():
                segment.text = text
                segment.source = "ocr"
                segment.image = None
                self.ocr_images += 1


# ============================================
# Shared styled-line & option-emphasis helpers (used by BOTH PDF and DOCX)
# ============================================

_OPTION_LINE_PATTERN = re.compile(r"^\s*([A-Da-d])\s*[.):]\s*\S")
_INLINE_OPTION_SPLIT_PATTERN = re.compile(r"(?:\t+|\s{2,})(?=[A-Da-d]\s*[.):]\s*\S)")
_QUESTION_OR_OPTION_CELL_PATTERN = re.compile(
    r"^\s*(?:[A-Da-d]\s*[.):]\s*\S|(?:Câu|Question)\s*\d{1,4}\b|\d{1,4}\s*[.):]\s*\S)",
    re.IGNORECASE,
)

_NEUTRAL_COLORS = {"AUTO", "000000", "FFFFFF"}
_W_FALSE = {"0", "false", "off", "none"}


@dataclass
class _StyledLine:
    text: str
    # Kiểu nhấn mạnh phủ >= 85% ký tự hiển thị của dòng (vd: {"bold", "color:FF0000"})
    signature: frozenset = frozenset()
    # Kiểu nhấn mạnh tại ký tự đầu tiên (thường là chữ cái đáp án "A", "B", "C", "D")
    key_signature: frozenset = frozenset()


def _build_styled_lines_from_pieces(pieces: list[tuple[str, frozenset]]) -> list[_StyledLine]:
    """
    Chuyển chuỗi mảnh ``(text, kinds)`` của một dòng/paragraph thành danh sách
    ``_StyledLine``. Nếu một dòng chứa nhiều phương án ``A. ...  B. ...  C. ...  D. ...``
    ngăn cách bởi tab hoặc nhiều dấu cách, tự tách thành từng dòng phương án riêng
    với đúng kiểu nhấn mạnh của từng phương án.
    """
    full_text = "".join(t for t, _ in pieces)
    if not full_text.strip():
        return []

    out: list[_StyledLine] = []
    offset = 0
    for raw_sub in full_text.split("\n"):
        sub_start, sub_end = offset, offset + len(raw_sub)
        offset = sub_end + 1
        if not raw_sub.strip():
            continue

        # Tách các phương án nằm chung 1 dòng (vd: "A. Hà Nội\tB. Huế\tC. Đà Nẵng\tD. Cần Thơ")
        spans = _find_inline_option_spans(raw_sub)
        if spans:
            for rel_s, rel_e in spans:
                seg_text = raw_sub[rel_s:rel_e].strip()
                if seg_text:
                    out.append(_slice_styled_line(seg_text, pieces, sub_start + rel_s, sub_start + rel_e))
        else:
            out.append(_slice_styled_line(raw_sub, pieces, sub_start, sub_end))
    return out


def _find_inline_option_spans(line: str) -> list[tuple[int, int]]:
    """
    Nếu dòng chứa >= 2 phương án trắc nghiệm phân tách bằng tab hoặc >= 2 khoảng trắng,
    trả về danh sách ``(start, end)`` cho phần câu hỏi (nếu có ở đầu) và từng phương án.
    """
    splits = [m.start() for m in _INLINE_OPTION_SPLIT_PATTERN.finditer(line)]
    if not splits:
        return []

    # Kiểm tra xem phần trước điểm cắt đầu tiên có bắt đầu bằng "A." không
    first_chunk = line[:splits[0]]
    leading_opt = re.search(r"(?:^|\t+|\s{2,})([A-Da-d]\s*[.):]\s*\S)", first_chunk)
    boundaries = [0]
    if leading_opt and leading_opt.start(1) > 0:
        boundaries.append(leading_opt.start(1))

    for pos in splits:
        # Nhảy qua các khoảng trắng/tab phân cách để trỏ đúng chữ cái B/C/D
        while pos < len(line) and line[pos] in " \t\u00a0":
            pos += 1
        if pos not in boundaries:
            boundaries.append(pos)
    boundaries.append(len(line))

    option_count = sum(
        1 for i in range(len(boundaries) - 1)
        if _OPTION_LINE_PATTERN.match(line[boundaries[i]:boundaries[i + 1]])
    )
    if option_count < 2:
        return []
    return [(boundaries[i], boundaries[i + 1]) for i in range(len(boundaries) - 1)]


def _slice_styled_line(
    text: str,
    pieces: list[tuple[str, frozenset]],
    start: int,
    end: int,
) -> _StyledLine:
    """Tính chữ ký nhấn mạnh cho đoạn ký tự ``[start, end)``."""
    counts: dict[str, int] = {}
    total = 0
    key_kinds: frozenset | None = None
    pos = 0
    for piece, kinds in pieces:
        p_start, p_end = pos, pos + len(piece)
        pos = p_end
        lo, hi = max(p_start, start), min(p_end, end)
        if lo >= hi:
            continue
        segment = piece[lo - p_start:hi - p_start]
        visible = len(re.sub(r"\s", "", segment))
        if not visible:
            continue
        if key_kinds is None:
            key_kinds = kinds
        total += visible
        for kind in kinds:
            counts[kind] = counts.get(kind, 0) + visible

    signature = frozenset(k for k, c in counts.items() if total and c / total >= 0.85)
    return _StyledLine(
        text=text.replace("\t", " ").strip(),
        signature=signature,
        key_signature=key_kinds or frozenset(),
    )


def _mark_emphasized_options(lines: list[_StyledLine]) -> None:
    """
    Trong mỗi nhóm phương án A/B/C/D liên tiếp, nếu ĐÚNG 1 phương án được
    nhấn mạnh khác biệt (in đậm, gạch chân, tô màu, highlight) so với các
    phương án còn lại → bọc ``**...**`` để ``question_parser`` nhận là đáp án.
    """
    index = 0
    while index < len(lines):
        match = _OPTION_LINE_PATTERN.match(lines[index].text)
        if not match or match.group(1).upper() != "A":
            index += 1
            continue

        group = [index]
        expected = "B"
        cursor = index + 1
        while cursor < len(lines) and expected <= "D":
            next_match = _OPTION_LINE_PATTERN.match(lines[cursor].text)
            if not next_match or next_match.group(1).upper() != expected:
                break
            group.append(cursor)
            expected = chr(ord(expected) + 1)
            cursor += 1

        if len(group) >= 2:
            chosen = _distinct_option(lines, group, "signature")
            if chosen is None:
                chosen = _distinct_option(lines, group, "key_signature")
            if chosen is not None:
                line = lines[chosen]
                if not line.text.strip().startswith("*"):
                    line.text = f"**{line.text.strip()}**"
        index = cursor if len(group) >= 2 else index + 1


def _distinct_option(lines: list[_StyledLine], group: list[int], attr: str) -> int | None:
    distinct = []
    for idx in group:
        own = getattr(lines[idx], attr) - {"italic"}
        others = set()
        for other in group:
            if other != idx:
                others |= getattr(lines[other], attr)
        if own - others:
            distinct.append(idx)
    return distinct[0] if len(distinct) == 1 else None


# ============================================
# PDF internal models
# ============================================

@dataclass
class _PdfImageCluster:
    rect: fitz.Rect
    dpi: float = 300.0


@dataclass
class _PdfTextBlock:
    rect: fitz.Rect
    lines: list[_StyledLine]
    meaningful_chars: int


# ============================================
# TextExtractor
# ============================================

class TextExtractor:
    """
    Service trích xuất text từ file bytes (PDF, DOCX, TXT) kèm OCR.

    Usage:
        extractor = TextExtractor()
        text = extractor.extract(file_bytes, "pdf")
    """

    _EXTRACTORS = {
        "pdf": "_extract_pdf",
        "docx": "_extract_docx",
        "txt": "_extract_txt",
    }

    # Minimum text length để coi là có nội dung hợp lệ (100 ký tự ≈ 1-2 câu)
    MIN_TEXT_LENGTH = 100
    SCANNED_PDF_MAX_PAGES = 20
    SCANNED_PDF_DPI_SCALE = 2

    # --- Ngưỡng phân loại hình học cho trang PDF ---
    # Số ký tự có nghĩa tối thiểu nằm bên trong 1 cụm ảnh để coi cụm ảnh đó đã có lớp chữ
    MIN_CHARS_IN_IMAGE_CLUSTER = 35
    # Số ký tự có nghĩa tối thiểu nằm ngoài các cụm ảnh để coi trang là "mixed" thay vì "scan"
    MIN_OUTSIDE_TEXT_CHARS = 20
    # Tỉ lệ diện tích tối thiểu của cụm ảnh trên trang (hoặc đủ rộng/cao như ảnh chụp 1 câu hỏi)
    MIN_CONTENT_IMAGE_RATIO = 0.015
    # Trang không chữ, không ảnh nhưng rất nhiều đường vector → chữ bị convert sang outline
    OUTLINED_TEXT_MIN_DRAWINGS = 150
    # Giới hạn số trang PDF được OCR cục bộ trong 1 file để bảo vệ server
    OCR_MAX_PAGES = 60

    def __init__(self, ocr: LocalOCREngine | None = None, ocr_max_pages: int | None = None):
        self.ocr = ocr if ocr is not None else LocalOCREngine()
        if ocr_max_pages is not None:
            self.OCR_MAX_PAGES = ocr_max_pages

    @staticmethod
    def has_damaged_ocr_text(text: str) -> bool:
        """Detect a non-empty PDF text layer that is visibly OCR-corrupted."""
        return bool(text) and len(OCR_DAMAGE_PATTERN.findall(text)) >= 2

    def extract(self, file_bytes: bytes, file_type: str) -> str:
        """
        Trích xuất text từ file bytes (đồng bộ, dùng OCR cục bộ nếu có).

        Args:
            file_bytes: Nội dung file dưới dạng bytes
            file_type: Loại file ("pdf", "docx", "txt")

        Returns:
            Cleaned plain text string
        """
        return self.finalize_text(self.extract_document(file_bytes, file_type))

    def extract_document(self, file_bytes: bytes, file_type: str) -> ExtractionResult:
        """Trích xuất thô thành các segment (chưa clean, có thể còn ảnh pending)."""
        file_type = file_type.lower().strip()

        extractor_name = self._EXTRACTORS.get(file_type)
        if not extractor_name:
            supported = ", ".join(self._EXTRACTORS.keys())
            raise ValueError(
                f"Unsupported file type: '{file_type}'. "
                f"Supported types: {supported}"
            )

        result = ExtractionResult(file_type=file_type)
        extractor = getattr(self, extractor_name)
        extractor(file_bytes, result)
        return result

    def finalize_text(self, result: ExtractionResult) -> str:
        """Ghép segment → convert TCVN3/VNI (chỉ phần text gốc) → normalize NFC → clean."""
        native_text = "\n".join(s.text for s in result.segments if s.source == "text")
        # Tự động chuyển đổi bảng mã cũ (TCVN3 / VNI-Windows) sang Unicode.
        # Chỉ áp dụng cho segment "text" (không đụng tới kết quả OCR vốn đã là Unicode).
        convert_tcvn3 = _is_tcvn3(native_text)
        convert_vni = (not convert_tcvn3) and _is_vni(native_text)

        parts = []
        for segment in result.segments:
            text = segment.text
            if not text or not text.strip():
                continue
            if segment.source == "text":
                if convert_tcvn3:
                    text = _tcvn3_to_unicode(text)
                elif convert_vni:
                    text = _vni_to_unicode(text)
            parts.append(unicodedata.normalize("NFC", text))

        return self._clean_text("\n\n".join(parts))

    def validate_extracted_text(self, text: str) -> tuple[bool, str]:
        """
        Validate text đã extract có đủ nội dung để tạo quiz hay không.

        Returns:
            (is_valid, error_message)
        """
        if not text or not text.strip():
            return False, "Could not extract any text from the file. The file may be empty or contain only images."

        if len(text.strip()) < self.MIN_TEXT_LENGTH:
            return False, (
                f"Extracted text is too short ({len(text.strip())} characters). "
                f"Minimum {self.MIN_TEXT_LENGTH} characters required to generate meaningful questions."
            )

        return True, ""

    @classmethod
    def render_scanned_pdf_pages(cls, file_bytes: bytes) -> list[bytes]:
        """Render a scan-only PDF to compact JPEG pages for multimodal OCR."""
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            try:
                if doc.page_count > cls.SCANNED_PDF_MAX_PAGES:
                    raise ValueError(
                        "Scanned PDFs can contain at most "
                        f"{cls.SCANNED_PDF_MAX_PAGES} pages."
                    )

                pages = []
                for page in doc:
                    pages.append(_render_rect_jpeg(page, page.rect))
                return pages
            finally:
                doc.close()
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Unable to prepare the scanned PDF for OCR.") from exc

    # ============================================
    # PDF extraction (native + embedded images + scanned pages)
    # ============================================

    def _extract_pdf(self, file_bytes: bytes, result: ExtractionResult) -> None:
        """
        Đọc PDF theo từng trang với phân tích hình học:
        1. Đọc các block chữ gốc + nhận diện đáp án tô đậm/tô màu/highlight.
        2. Gom các ảnh trên trang thành cụm ảnh (xử lý cả ảnh scan bị cắt lát ngang).
        3. Kiểm tra từng cụm ảnh xem đã có lớp chữ gốc đè lên chưa:
           - Nếu toàn trang là ảnh scan (kể cả có dính watermark CamScanner / số trang)
             hoặc lớp chữ OCR cũ bị lỗi → OCR toàn trang.
           - Nếu trang có cả chữ gốc lẫn cụm ảnh chưa có lớp chữ (ảnh chụp câu hỏi/bảng
             đưa vào PDF) → giữ chữ gốc, OCR riêng từng cụm ảnh và ghép theo thứ tự (y, x).
           - Nếu trang có lớp chữ đầy đủ → dùng chữ gốc (nhanh & chính xác tuyệt đối).
        """
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception as e:
            raise ValueError(f"Failed to extract text from PDF: {str(e)}")

        try:
            if doc.needs_pass and not doc.authenticate(""):
                raise ValueError("PDF is password-protected. Please remove the password and upload again.")

            ocr_budget = self.OCR_MAX_PAGES
            for page_index, page in enumerate(doc):
                page_number = page_index + 1
                blocks, raw_page_text = self._read_pdf_native_blocks(page)
                clusters = self._content_image_clusters(page)
                kind, unocrd_clusters = self._analyze_pdf_page(
                    page, blocks, raw_page_text, clusters
                )

                if kind == "empty":
                    continue

                if kind == "text":
                    page_text = self._format_pdf_blocks(blocks)
                    if page_text:
                        result.segments.append(TextSegment(text=page_text))
                    continue

                if ocr_budget <= 0:
                    result.skipped_ocr_pages.append(page_number)
                    page_text = self._format_pdf_blocks(blocks)
                    if page_text:
                        result.segments.append(TextSegment(text=page_text))
                    continue
                ocr_budget -= 1

                if kind == "scan":
                    self._process_scanned_pdf_page(page, page_number, blocks, result)
                else:
                    self._process_mixed_pdf_page(
                        page, page_number, blocks, unocrd_clusters, result
                    )
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Failed to extract text from PDF: {str(e)}")
        finally:
            doc.close()

        if result.ocr_pages:
            logger.info("OCR applied to PDF pages: %s", result.ocr_pages)
        if result.skipped_ocr_pages:
            logger.warning(
                "OCR page limit (%s) reached; pages not OCR'd: %s",
                self.OCR_MAX_PAGES, result.skipped_ocr_pages,
            )

    def _process_scanned_pdf_page(
        self,
        page: fitz.Page,
        page_number: int,
        fallback_blocks: list[_PdfTextBlock],
        result: ExtractionResult,
    ) -> None:
        fallback_text = self._format_pdf_blocks(fallback_blocks)
        if self.ocr.is_available:
            try:
                ocr_text = self.ocr.ocr_page(page, full=True)
            except Exception as exc:
                logger.warning("Local OCR failed on scanned page %s: %s", page_number, exc)
                ocr_text = ""
            if ocr_text and ocr_text.strip():
                result.segments.append(TextSegment(text=ocr_text, source="ocr", label=f"page {page_number}"))
                result.ocr_pages.append(page_number)
                return
            if fallback_text:
                result.segments.append(TextSegment(text=fallback_text))
            return

        result.segments.append(TextSegment(
            text=fallback_text,
            source="pending",
            image=_render_rect_jpeg(page, page.rect),
            label=f"page {page_number}",
        ))

    def _process_mixed_pdf_page(
        self,
        page: fitz.Page,
        page_number: int,
        blocks: list[_PdfTextBlock],
        unocrd_clusters: list[_PdfImageCluster],
        result: ExtractionResult,
    ) -> None:
        """
        Ghép các block chữ gốc và kết quả OCR của các ảnh nhúng theo đúng thứ tự
        từ trên xuống dưới, từ trái sang phải trên trang PDF.
        """
        items: list[tuple[float, float, str, object]] = []
        for blk in blocks:
            # Bỏ qua các mảnh chữ rác nằm lọt thỏm bên trong vùng ảnh chưa OCR (vd: watermark nhỏ)
            if blk.meaningful_chars < 15 and any(
                _overlap_ratio(blk.rect, cl.rect) > 0.7 for cl in unocrd_clusters
            ):
                continue
            items.append((blk.rect.y0, blk.rect.x0, "block", blk))

        for idx, cluster in enumerate(unocrd_clusters, start=1):
            items.append((cluster.rect.y0, cluster.rect.x0, "image", (idx, cluster)))

        items.sort(key=lambda it: (round(it[0] / 8.0), it[1]))

        pending_lines: list[_StyledLine] = []
        used_page_ocr = False

        def flush_native() -> None:
            nonlocal pending_lines
            if not pending_lines:
                return
            _mark_emphasized_options(pending_lines)
            txt = "\n".join(ln.text for ln in pending_lines if ln.text.strip())
            if txt.strip():
                result.segments.append(TextSegment(text=txt))
            pending_lines = []

        for _, _, item_type, payload in items:
            if item_type == "block":
                blk = payload  # type: ignore[assignment]
                pending_lines.extend(blk.lines)
                continue

            flush_native()
            img_idx, cluster = payload  # type: ignore[misc]
            label = f"page {page_number} image {img_idx}"
            if self.ocr.is_available:
                try:
                    ocr_text = self.ocr.ocr_clip(page, cluster.rect, native_dpi=cluster.dpi)
                except Exception as exc:
                    logger.warning("Local OCR failed on %s: %s", label, exc)
                    ocr_text = ""
                if ocr_text and ocr_text.strip():
                    result.segments.append(TextSegment(text=ocr_text, source="ocr", label=label))
                    result.ocr_images += 1
                    used_page_ocr = True
            else:
                result.segments.append(TextSegment(
                    source="pending",
                    image=_render_rect_jpeg(page, cluster.rect, preferred_dpi=max(220, int(cluster.dpi))),
                    label=label,
                ))

        flush_native()
        if used_page_ocr and page_number not in result.ocr_pages:
            result.ocr_pages.append(page_number)

    @staticmethod
    def _format_pdf_blocks(blocks: list[_PdfTextBlock]) -> str:
        all_lines: list[_StyledLine] = []
        for blk in blocks:
            all_lines.extend(blk.lines)
        if not all_lines:
            return ""
        _mark_emphasized_options(all_lines)
        return "\n".join(ln.text for ln in all_lines if ln.text.strip())

    def _analyze_pdf_page(
        self,
        page: fitz.Page,
        blocks: list[_PdfTextBlock],
        raw_page_text: str,
        clusters: list[_PdfImageCluster],
    ) -> tuple[str, list[_PdfImageCluster]]:
        """
        Trả về ``(kind, unocrd_clusters)`` với ``kind`` thuộc
        ``{"empty", "text", "scan", "mixed"}``.
        """
        total_meaningful = sum(b.meaningful_chars for b in blocks)

        if self.has_damaged_ocr_text(raw_page_text):
            return "scan", clusters

        unocrd: list[_PdfImageCluster] = []
        for cl in clusters:
            chars_in_cluster = sum(
                b.meaningful_chars
                for b in blocks
                if _overlap_ratio(b.rect, cl.rect) >= 0.35
            )
            if chars_in_cluster < self.MIN_CHARS_IN_IMAGE_CLUSTER:
                unocrd.append(cl)

        if not unocrd:
            if total_meaningful == 0:
                try:
                    if len(page.get_drawings()) >= self.OUTLINED_TEXT_MIN_DRAWINGS:
                        return "scan", []
                except Exception:
                    pass
                return ("text", []) if raw_page_text.strip() else ("empty", [])
            return "text", []

        outside_chars = sum(
            b.meaningful_chars
            for b in blocks
            if not any(_overlap_ratio(b.rect, cl.rect) >= 0.35 for cl in unocrd)
        )
        if outside_chars < self.MIN_OUTSIDE_TEXT_CHARS:
            return "scan", unocrd
        return "mixed", unocrd

    def _content_image_clusters(self, page: fitz.Page) -> list[_PdfImageCluster]:
        """
        Tìm các vùng ảnh trên trang PDF, tự động gộp các dải ảnh nằm sát nhau
        (máy scan / máy in PDF cũ thường cắt 1 trang scan thành hàng chục lát ngang).
        """
        page_rect = page.rect
        page_area = abs(page_rect) or 1.0
        raw_items: list[_PdfImageCluster] = []
        try:
            infos = page.get_image_info(xrefs=True)
        except Exception:
            return []

        for info in infos:
            rect = fitz.Rect(info.get("bbox", (0, 0, 0, 0))) & page_rect
            if rect.is_empty or rect.width < 12 or rect.height < 6:
                continue
            px_w = float(info.get("width") or 0)
            px_h = float(info.get("height") or 0)
            dpi_x = (px_w * 72.0 / rect.width) if px_w and rect.width > 0 else 300.0
            dpi_y = (px_h * 72.0 / rect.height) if px_h and rect.height > 0 else 300.0
            raw_items.append(_PdfImageCluster(rect=rect, dpi=max(dpi_x, dpi_y, 72.0)))

        # Gộp các hình chữ nhật chạm nhau hoặc cách nhau <= 6pt
        merged = True
        while merged and len(raw_items) > 1:
            merged = False
            next_items: list[_PdfImageCluster] = []
            used = [False] * len(raw_items)
            for i, a in enumerate(raw_items):
                if used[i]:
                    continue
                cur_rect = fitz.Rect(a.rect)
                cur_dpi = a.dpi
                expanded = fitz.Rect(
                    cur_rect.x0 - 6, cur_rect.y0 - 6, cur_rect.x1 + 6, cur_rect.y1 + 6
                )
                for j in range(i + 1, len(raw_items)):
                    if used[j]:
                        continue
                    if expanded.intersects(raw_items[j].rect):
                        cur_rect |= raw_items[j].rect
                        cur_dpi = max(cur_dpi, raw_items[j].dpi)
                        expanded = fitz.Rect(
                            cur_rect.x0 - 6, cur_rect.y0 - 6, cur_rect.x1 + 6, cur_rect.y1 + 6
                        )
                        used[j] = True
                        merged = True
                next_items.append(_PdfImageCluster(rect=cur_rect, dpi=cur_dpi))
            raw_items = next_items

        clusters: list[_PdfImageCluster] = []
        for item in raw_items:
            r = item.rect
            if r.width < 40 or r.height < 16:
                continue
            area_ratio = abs(r) / page_area
            is_question_strip = r.width >= 100 and r.height >= 20 and area_ratio >= 0.008
            if area_ratio >= self.MIN_CONTENT_IMAGE_RATIO or is_question_strip:
                clusters.append(item)
        return clusters

    @staticmethod
    def _read_pdf_native_blocks(page: fitz.Page) -> tuple[list[_PdfTextBlock], str]:
        """
        Đọc các block chữ gốc từ trang PDF theo thứ tự đọc, đồng thời thu thập
        kiểu định dạng (in đậm, màu chữ, highlight/gạch chân từ annotation & vector)
        để nhận diện đáp án được đánh dấu sẵn.
        """
        highlight_rects, underline_rects = _collect_pdf_markup_rects(page)
        try:
            data = page.get_text("rawdict")
        except Exception:
            return [], ""

        raw_blocks = [b for b in data.get("blocks", []) if b.get("type") == 0]
        raw_blocks.sort(key=lambda b: (round(b["bbox"][1] / 6.0), b["bbox"][0]))

        blocks: list[_PdfTextBlock] = []
        raw_lines_all: list[str] = []

        for block in raw_blocks:
            block_styled_lines: list[_StyledLine] = []
            meaningful_chars = 0
            lines = sorted(
                block.get("lines", []),
                key=lambda ln: (round(ln["bbox"][1] / 4.0), ln["bbox"][0]),
            )

            for line in lines:
                pieces: list[tuple[str, frozenset]] = []
                prev_x1: float | None = None
                prev_size: float = 12.0
                for span in line.get("spans", []):
                    chars = span.get("chars") or []
                    if not chars:
                        continue
                    span_text = "".join(c["c"] for c in chars)
                    if not span_text:
                        continue
                    size = float(span.get("size") or prev_size or 12.0)
                    first_x0 = float(chars[0]["bbox"][0])
                    if (
                        pieces
                        and not pieces[-1][0].endswith((" ", "\t"))
                        and not span_text.startswith((" ", "\t"))
                        and prev_x1 is not None
                    ):
                        gap = first_x0 - prev_x1
                        min_size = max(1.0, min(size, prev_size))
                        # Khoảng cách rất lớn trong cùng 1 dòng PDF tương đương tab cột (A. ...    B. ...)
                        if gap > 2.2 * min_size:
                            pieces.append(("\t", frozenset()))
                        elif gap > 0.18 * min_size:
                            pieces.append((" ", frozenset()))

                    kinds = _pdf_span_kinds(span, highlight_rects, underline_rects)
                    pieces.append((span_text, kinds))
                    prev_x1 = float(chars[-1]["bbox"][2])
                    prev_size = size

                styled_lines = _build_styled_lines_from_pieces(pieces)
                for sl in styled_lines:
                    raw_lines_all.append(sl.text)
                    if not WATERMARK_LINE_PATTERN.search(sl.text) and not _TRIVIAL_PAGE_NO_LINE.match(sl.text):
                        meaningful_chars += len(re.sub(r"\s+", "", sl.text))
                    block_styled_lines.append(sl)

            if block_styled_lines:
                blocks.append(_PdfTextBlock(
                    rect=fitz.Rect(block["bbox"]),
                    lines=block_styled_lines,
                    meaningful_chars=meaningful_chars,
                ))

        return blocks, "\n".join(raw_lines_all)

    # ============================================
    # DOCX extraction
    # ============================================

    def _extract_docx(self, file_bytes: bytes, result: ExtractionResult) -> None:
        """
        Trích xuất text từ DOCX dùng python-docx + XML walker.

        Hỗ trợ:
        - Đọc paragraphs và tables THEO ĐÚNG THỨ TỰ xuất hiện trong tài liệu
        - Khôi phục đánh số tự động (numbering.xml: Câu 1., 1., A., B., C., D.)
        - Bảng phương án 2x2 / 1x4 (không chèn ký tự '|' làm bẩn đáp án)
        - Bảng dữ liệu / bảng đáp án cuối đề (giữ định dạng '1 | A | 2 | B')
        - Text box, công thức toán OMML (phân số, số mũ, chỉ số dưới, căn bậc hai)
        - Nhận diện đáp án tô đậm / gạch chân / highlight / tô màu
        - OCR cho ảnh chụp / ảnh scan chèn trong Word
        """
        if file_bytes[:4] == b"\xd0\xcf\x11\xe0":
            raise ValueError(
                "Failed to extract text from DOCX: Legacy Word 97-2003 (.doc) binary "
                "format detected. Please save the file as .docx or .pdf and upload again."
            )
        try:
            doc = Document(BytesIO(file_bytes))
        except Exception as e:
            raise ValueError(f"Failed to extract text from DOCX: {str(e)}")

        try:
            reader = _DocxReader(doc, self.ocr, result)
            reader.read_body()
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Failed to extract text from DOCX: {str(e)}")

    # ============================================
    # TXT extraction
    # ============================================

    @staticmethod
    def _extract_txt(file_bytes: bytes, result: ExtractionResult) -> None:
        """Đọc file TXT với ưu tiên BOM / UTF-8 chuẩn trước khi fallback sang chardet."""
        try:
            if not file_bytes:
                result.segments.append(TextSegment(text=""))
                return

            for bom_enc in ("utf-8-sig", "utf-16"):
                if bom_enc == "utf-16" and not file_bytes.startswith((b"\xff\xfe", b"\xfe\xff")):
                    continue
                try:
                    result.segments.append(TextSegment(text=file_bytes.decode(bom_enc)))
                    return
                except UnicodeDecodeError:
                    pass

            detected = chardet.detect(file_bytes)
            encoding = detected.get("encoding", "utf-8") or "utf-8"
            confidence = detected.get("confidence", 0)
            if confidence < 0.5:
                encoding = "utf-8"

            result.segments.append(TextSegment(text=file_bytes.decode(encoding, errors="replace")))

        except Exception as e:
            raise ValueError(f"Failed to read TXT file: {str(e)}")

    # ============================================
    # Text cleaning
    # ============================================

    @staticmethod
    def _clean_text(text: str) -> str:
        """
        Clean và normalize text sau khi extract.

        - Bỏ watermark chia sẻ tài liệu / máy scan điện thoại
        - Chuẩn hoá ligatures (ﬁ, ﬂ), xoá ký tự ẩn zero-width & null
        - Bỏ multiple blank lines liên tiếp (giữ tối đa 2)
        """
        if not text:
            return ""

        text = text.replace("\x00", "")
        text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
        text = (
            text.replace("\ufb00", "ff")
            .replace("\ufb01", "fi")
            .replace("\ufb02", "fl")
            .replace("\ufb03", "ffi")
            .replace("\ufb04", "ffl")
        )
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")

        lines = text.split("\n")
        cleaned_lines = []
        blank_count = 0

        for line in lines:
            stripped = re.sub(r"[ \t\u00a0]+", " ", line).strip()
            if WATERMARK_LINE_PATTERN.search(stripped):
                continue
            if not stripped:
                blank_count += 1
                if blank_count <= 2:
                    cleaned_lines.append("")
            else:
                blank_count = 0
                cleaned_lines.append(stripped)

        return "\n".join(cleaned_lines).strip()


# ============================================
# PDF formatting & geometry helpers
# ============================================

def _overlap_ratio(inner: fitz.Rect, outer: fitz.Rect) -> float:
    area = abs(inner)
    if area <= 0:
        return 0.0
    inter = inner & outer
    if inter.is_empty:
        return 0.0
    return abs(inter) / area


def _render_rect_jpeg(
    page: fitz.Page,
    rect: fitz.Rect,
    preferred_dpi: int = 200,
) -> bytes:
    """Render trang hoặc vùng ảnh trên trang PDF sang JPEG gọn nhẹ cho Vision OCR."""
    dpi = LocalOCREngine.adaptive_dpi(rect, preferred_dpi=preferred_dpi, min_side_px=1000)
    dpi = min(dpi, 300)
    pixmap = page.get_pixmap(dpi=dpi, clip=rect, alpha=False)
    return pixmap.tobytes("jpeg")


def _collect_pdf_markup_rects(page: fitz.Page) -> tuple[list[fitz.Rect], list[fitz.Rect]]:
    """
    Thu thập vùng highlight và gạch chân trên trang PDF từ cả:
    1. PDF Annotations (Highlight=8, Underline=9, Squiggly=10, Square=4, Circle=5)
    2. Vector drawings do Word/PowerPoint xuất sang PDF (hình chữ nhật tô màu nền
       vàng/xanh phía sau chữ hoặc đường kẻ ngang mỏng sát chân chữ).
    """
    highlights: list[fitz.Rect] = []
    underlines: list[fitz.Rect] = []

    try:
        annots = page.annots() or []
        for annot in annots:
            code = annot.type[0] if annot.type else -1
            if code in {8, 4, 5}:
                highlights.append(fitz.Rect(annot.rect))
            elif code in {9, 10}:
                underlines.append(fitz.Rect(annot.rect))
    except Exception:
        pass

    try:
        page_area = abs(page.rect) or 1.0
        for d in page.get_drawings():
            rect = fitz.Rect(d.get("rect", (0, 0, 0, 0)))
            if rect.is_empty or abs(rect) / page_area > 0.25:
                continue
            fill = d.get("fill")
            stroke = d.get("color")
            # Highlight rectangle exported from Word (colored non-white, non-black box)
            if (
                fill
                and len(fill) >= 3
                and 6 <= rect.height <= 32
                and rect.width >= 8
                and (min(fill[:3]) < 0.94 and max(fill[:3]) > 0.25)
                and (max(fill[:3]) - min(fill[:3]) > 0.08)
            ):
                highlights.append(rect)
            # Thin horizontal underline exported from Word/LaTeX
            elif (
                (fill or stroke)
                and rect.height <= 2.5
                and rect.width >= 8
                and rect.width > rect.height * 4
            ):
                underlines.append(rect)
    except Exception:
        pass

    return highlights, underlines


def _pdf_span_kinds(
    span: dict,
    highlight_rects: list[fitz.Rect],
    underline_rects: list[fitz.Rect],
) -> frozenset:
    kinds: set[str] = set()
    flags = int(span.get("flags") or 0)
    font_name = (span.get("font") or "").lower()

    if (flags & 16) or any(w in font_name for w in ("bold", "black", "heavy", "demi", "-bd", ",bd")):
        kinds.add("bold")
    if (flags & 2) or "italic" in font_name or "oblique" in font_name:
        kinds.add("italic")

    color_int = span.get("color")
    if isinstance(color_int, int):
        r = (color_int >> 16) & 0xFF
        g = (color_int >> 8) & 0xFF
        b = color_int & 0xFF
        # Bỏ qua màu đen/xám đậm và màu trắng
        if not (r < 45 and g < 45 and b < 45) and not (r > 240 and g > 240 and b > 240):
            if max(r, g, b) - min(r, g, b) >= 25:
                kinds.add(f"color:{r:02X}{g:02X}{b:02X}")

    bbox = fitz.Rect(span.get("bbox", (0, 0, 0, 0)))
    if not bbox.is_empty:
        if any(_overlap_ratio(bbox, hr) >= 0.45 for hr in highlight_rects):
            kinds.add("highlight")
        for ur in underline_rects:
            # Đường gạch chân nằm gần cạnh dưới của span và phủ phần lớn chiều ngang span
            if (
                abs(ur.y0 - bbox.y1) <= max(4.0, bbox.height * 0.35)
                and min(bbox.x1, ur.x1) - max(bbox.x0, ur.x0) >= max(6.0, bbox.width * 0.5)
            ):
                kinds.add("underline")
                break

    return frozenset(kinds)


# ============================================
# DOCX reader (document-order walker + numbering + OMML + OCR)
# ============================================

_W_P = qn("w:p")
_W_PPR = qn("w:pPr")
_W_PSTYLE = qn("w:pStyle")
_W_NUMPR = qn("w:numPr")
_W_NUMID = qn("w:numId")
_W_ILVL = qn("w:ilvl")
_W_TBL = qn("w:tbl")
_W_TR = qn("w:tr")
_W_TC = qn("w:tc")
_W_R = qn("w:r")
_W_T = qn("w:t")
_W_TAB = qn("w:tab")
_W_BR = qn("w:br")
_W_CR = qn("w:cr")
_W_SDT = qn("w:sdt")
_W_SDT_CONTENT = qn("w:sdtContent")
_W_TXBX_CONTENT = qn("w:txbxContent")
_W_RPR = qn("w:rPr")
_W_RSTYLE = qn("w:rStyle")
_W_DEL = qn("w:del")
_W_VMERGE = qn("w:vMerge")
_W_TCPR = qn("w:tcPr")
_W_VAL = qn("w:val")

_M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
_M_T = f"{{{_M_NS}}}t"
_M_F = f"{{{_M_NS}}}f"
_M_NUM = f"{{{_M_NS}}}num"
_M_DEN = f"{{{_M_NS}}}den"
_M_SSUP = f"{{{_M_NS}}}sSup"
_M_SSUB = f"{{{_M_NS}}}sSub"
_M_SSUBSUP = f"{{{_M_NS}}}sSubSup"
_M_RAD = f"{{{_M_NS}}}rad"
_M_E = f"{{{_M_NS}}}e"
_M_SUP = f"{{{_M_NS}}}sup"
_M_SUB = f"{{{_M_NS}}}sub"

_MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
_A_BLIP = qn("a:blip")
_V_IMAGEDATA = "{urn:schemas-microsoft-com:vml}imagedata"
_R_EMBED = qn("r:embed")
_R_ID = qn("r:id")


class _DocxNumbering:
    """
    Khôi phục tiền tố đánh số tự động (``1.``, ``Câu 1.``, ``A.``, ``b)``...) từ
    ``word/numbering.xml`` và ``styles.xml`` của file Word.
    """

    def __init__(self, doc):
        self.levels: dict[tuple[str, int], tuple[str, str, int]] = {}
        self.style_numpr: dict[str, tuple[str, int]] = {}
        self.style_rpr: dict[str, object] = {}
        self.counters: dict[tuple[str, int], int] = {}
        self._load_styles(doc)
        self._load_numbering(doc)

    def _load_styles(self, doc) -> None:
        try:
            styles_el = doc.styles.element
        except Exception:
            return
        for style in styles_el.findall(qn("w:style")):
            style_id = style.get(qn("w:styleId"))
            if not style_id:
                continue
            rpr = style.find(_W_RPR)
            if rpr is not None:
                self.style_rpr[style_id] = rpr
            ppr = style.find(_W_PPR)
            numpr = ppr.find(_W_NUMPR) if ppr is not None else None
            if numpr is not None:
                num_id_el = numpr.find(_W_NUMID)
                ilvl_el = numpr.find(_W_ILVL)
                if num_id_el is not None and num_id_el.get(_W_VAL):
                    ilvl = int(ilvl_el.get(_W_VAL, "0")) if ilvl_el is not None else 0
                    self.style_numpr[style_id] = (num_id_el.get(_W_VAL), ilvl)

    def _load_numbering(self, doc) -> None:
        try:
            numbering_el = doc.part.numbering_part.element
        except Exception:
            return

        abstract_map: dict[str, dict[int, tuple[str, str, int]]] = {}
        for abs_num in numbering_el.findall(qn("w:abstractNum")):
            abs_id = abs_num.get(qn("w:abstractNumId"))
            if abs_id is None:
                continue
            lvl_dict: dict[int, tuple[str, str, int]] = {}
            for lvl in abs_num.findall(qn("w:lvl")):
                ilvl = int(lvl.get(qn("w:ilvl"), "0"))
                lvl_dict[ilvl] = self._parse_lvl(lvl)
            abstract_map[abs_id] = lvl_dict

        for num in numbering_el.findall(qn("w:num")):
            num_id = num.get(qn("w:numId"))
            abs_id_el = num.find(qn("w:abstractNumId"))
            if not num_id or abs_id_el is None:
                continue
            abs_id = abs_id_el.get(_W_VAL, "")
            for ilvl, spec in abstract_map.get(abs_id, {}).items():
                self.levels[(num_id, ilvl)] = spec
            for ovr in num.findall(qn("w:lvlOverride")):
                ilvl = int(ovr.get(qn("w:ilvl"), "0"))
                ovr_lvl = ovr.find(qn("w:lvl"))
                if ovr_lvl is not None:
                    self.levels[(num_id, ilvl)] = self._parse_lvl(ovr_lvl)
                else:
                    start_ovr = ovr.find(qn("w:startOverride"))
                    if start_ovr is not None and (num_id, ilvl) in self.levels:
                        fmt, text, _ = self.levels[(num_id, ilvl)]
                        self.levels[(num_id, ilvl)] = (fmt, text, int(start_ovr.get(_W_VAL, "1")))

    @staticmethod
    def _parse_lvl(lvl) -> tuple[str, str, int]:
        fmt_el = lvl.find(qn("w:numFmt"))
        txt_el = lvl.find(qn("w:lvlText"))
        start_el = lvl.find(qn("w:start"))
        fmt = fmt_el.get(_W_VAL, "decimal") if fmt_el is not None else "decimal"
        txt = txt_el.get(_W_VAL, "%1.") if txt_el is not None else "%1."
        try:
            start = int(start_el.get(_W_VAL, "1")) if start_el is not None else 1
        except ValueError:
            start = 1
        return fmt, txt, start

    def next_prefix(self, p) -> str:
        ppr = p.find(_W_PPR)
        if ppr is None:
            return ""

        num_id = None
        ilvl = 0
        numpr = ppr.find(_W_NUMPR)
        if numpr is not None:
            num_id_el = numpr.find(_W_NUMID)
            ilvl_el = numpr.find(_W_ILVL)
            if num_id_el is not None:
                num_id = num_id_el.get(_W_VAL)
            if ilvl_el is not None and ilvl_el.get(_W_VAL):
                ilvl = int(ilvl_el.get(_W_VAL))
        else:
            pstyle = ppr.find(_W_PSTYLE)
            if pstyle is not None and pstyle.get(_W_VAL) in self.style_numpr:
                num_id, ilvl = self.style_numpr[pstyle.get(_W_VAL)]

        if not num_id or num_id == "0" or (num_id, ilvl) not in self.levels:
            return ""

        fmt, lvl_text, start = self.levels[(num_id, ilvl)]
        if fmt in {"bullet", "none"}:
            return ""

        # Reset các cấp sâu hơn khi cấp cha tăng
        for (nid, lv) in list(self.counters.keys()):
            if nid == num_id and lv > ilvl:
                del self.counters[(nid, lv)]

        current = self.counters.get((num_id, ilvl), start - 1) + 1
        self.counters[(num_id, ilvl)] = current

        rendered = lvl_text
        for lv in range(ilvl + 1):
            l_fmt, _, l_start = self.levels.get((num_id, lv), ("decimal", "%1.", 1))
            val = self.counters.get((num_id, lv), l_start)
            rendered = rendered.replace(f"%{lv + 1}", self._format_number(val, l_fmt))

        rendered = rendered.strip()
        if rendered and rendered[-1].isalnum():
            rendered += "."
        return f"{rendered} " if rendered else ""

    @staticmethod
    def _format_number(n: int, fmt: str) -> str:
        if n <= 0:
            return str(n)
        if fmt == "upperLetter":
            return chr(ord("A") + (n - 1) % 26)
        if fmt == "lowerLetter":
            return chr(ord("a") + (n - 1) % 26)
        if fmt in {"upperRoman", "lowerRoman"}:
            vals = [
                (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
                (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
                (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
            ]
            out = []
            rem = n
            for v, sym in vals:
                while rem >= v:
                    out.append(sym)
                    rem -= v
            roman = "".join(out)
            return roman.lower() if fmt == "lowerRoman" else roman
        return str(n)


class _DocxReader:
    """Đọc body DOCX theo đúng thứ tự tài liệu, gom dòng text + ảnh thành segment."""

    def __init__(self, doc, ocr: LocalOCREngine, result: ExtractionResult):
        self.doc = doc
        self.ocr = ocr
        self.result = result
        self.numbering = _DocxNumbering(doc)
        self.lines: list[_StyledLine] = []
        self.seen_images: set[str] = set()
        self.image_sink: list[str] | None = None

    def read_body(self) -> None:
        self._read_blocks(self.doc.element.body)
        self._flush_lines()

    def _read_blocks(self, container) -> None:
        for child in container.iterchildren():
            if child.tag == _W_P:
                self._read_paragraph(child)
            elif child.tag == _W_TBL:
                self._read_table(child)
            elif child.tag == _W_SDT:
                content = child.find(_W_SDT_CONTENT)
                if content is not None:
                    self._read_blocks(content)

    def _read_paragraph(self, p) -> None:
        p_kinds = self._paragraph_rpr_kinds(p)
        pieces: list[tuple[str, frozenset]] = []
        images: list[str] = []
        nested_paragraphs = []
        self._walk_inline(p, p_kinds, pieces, images, nested_paragraphs)

        raw_text = "".join(t for t, _ in pieces)
        if raw_text.strip():
            prefix = self.numbering.next_prefix(p)
            if prefix and not _already_has_list_prefix(raw_text, prefix):
                first_kinds = next((k for t, k in pieces if t.strip()), p_kinds)
                pieces.insert(0, (prefix, first_kinds))
            self.lines.extend(_build_styled_lines_from_pieces(pieces))

        for rid in images:
            self._add_image(rid)
        for nested in nested_paragraphs:
            self._read_blocks(nested)

    def _read_table(self, tbl) -> None:
        rows_cells: list[list[list[_StyledLine]]] = []
        row_images: list[str] = []

        for tr in tbl.iterchildren(_W_TR):
            row_cells: list[list[_StyledLine]] = []
            for tc in tr.iterchildren(_W_TC):
                tc_pr = tc.find(_W_TCPR)
                vmerge = tc_pr.find(_W_VMERGE) if tc_pr is not None else None
                if vmerge is not None and vmerge.get(_W_VAL) in (None, "continue"):
                    continue
                cell_lines = self._cell_styled_lines(tc, row_images)
                if cell_lines:
                    row_cells.append(cell_lines)
            if row_cells:
                rows_cells.append(row_cells)

        # Phân biệt bảng dàn trang phương án/câu hỏi (2x2, 1x4: A. ... | B. ...)
        # với bảng dữ liệu / bảng đáp án cuối bài (1 | B | 2 | D)
        all_cells = [cell for row in rows_cells for cell in row]
        option_like_cells = sum(
            1 for cell in all_cells
            if cell and _QUESTION_OR_OPTION_CELL_PATTERN.match(cell[0].text)
        )
        is_quiz_layout_table = bool(all_cells) and (
            option_like_cells >= 2 and option_like_cells / len(all_cells) >= 0.5
        )

        if is_quiz_layout_table:
            for row in rows_cells:
                for cell in row:
                    self.lines.extend(cell)
        else:
            for row in rows_cells:
                row_text = " | ".join(
                    " ".join(ln.text.strip() for ln in cell if ln.text.strip())
                    for cell in row
                ).strip()
                if row_text:
                    self.lines.append(_StyledLine(row_text))

        for rid in row_images:
            self._add_image(rid)

    def _cell_styled_lines(self, tc, row_images: list[str]) -> list[_StyledLine]:
        saved_lines, saved_sink = self.lines, self.image_sink
        self.lines = []
        self.image_sink = row_images
        try:
            self._read_blocks(tc)
            return [ln for ln in self.lines if ln.text.strip()]
        finally:
            self.lines, self.image_sink = saved_lines, saved_sink

    def _walk_inline(self, element, kinds, pieces, images, nested_paragraphs) -> None:
        for child in element.iterchildren():
            tag = child.tag
            if not isinstance(tag, str):
                continue
            if tag in (_MC_FALLBACK, _W_DEL, _W_PPR, _W_RPR):
                continue
            if tag == _W_TXBX_CONTENT:
                nested_paragraphs.append(child)
                continue
            if tag == _W_R:
                run_kinds = kinds | self._run_kinds(child)
                self._walk_inline(child, run_kinds, pieces, images, nested_paragraphs)
                continue
            if tag in (_W_T, _M_T):
                if child.text:
                    pieces.append((child.text, kinds))
                continue
            if tag == _W_TAB:
                pieces.append(("\t", kinds))
                continue
            if tag in (_W_BR, _W_CR):
                pieces.append(("\n", kinds))
                continue
            if tag in (_A_BLIP, _V_IMAGEDATA):
                rid = child.get(_R_EMBED) or child.get(_R_ID)
                if rid:
                    images.append(rid)
                continue
            if tag in (_M_F, _M_SSUP, _M_SSUB, _M_SSUBSUP, _M_RAD):
                math_text = self._render_omml(child)
                if math_text:
                    pieces.append((math_text, kinds))
                continue
            self._walk_inline(child, kinds, pieces, images, nested_paragraphs)

    def _render_omml(self, math_el) -> str:
        """Chuyển các cấu trúc toán học OMML phổ biến sang ký hiệu dễ đọc."""
        def text_of(node) -> str:
            if node is None:
                return ""
            sub_pieces: list[tuple[str, frozenset]] = []
            self._walk_inline(node, frozenset(), sub_pieces, [], [])
            return "".join(t for t, _ in sub_pieces).strip()

        tag = math_el.tag
        if tag == _M_F:
            num = text_of(math_el.find(_M_NUM))
            den = text_of(math_el.find(_M_DEN))
            n_str = f"({num})" if len(num) > 1 else num
            d_str = f"({den})" if len(den) > 1 else den
            return f"{n_str}/{d_str}" if (n_str or d_str) else ""
        if tag == _M_SSUP:
            return f"{text_of(math_el.find(_M_E))}^{text_of(math_el.find(_M_SUP))}"
        if tag == _M_SSUB:
            return f"{text_of(math_el.find(_M_E))}_{text_of(math_el.find(_M_SUB))}"
        if tag == _M_SSUBSUP:
            return (
                f"{text_of(math_el.find(_M_E))}"
                f"_{text_of(math_el.find(_M_SUB))}"
                f"^{text_of(math_el.find(_M_SUP))}"
            )
        if tag == _M_RAD:
            return f"√({text_of(math_el.find(_M_E))})"
        return ""

    def _paragraph_rpr_kinds(self, p) -> frozenset:
        ppr = p.find(_W_PPR)
        if ppr is None:
            return frozenset()
        rpr = ppr.find(_W_RPR)
        return self._rpr_to_kinds(rpr) if rpr is not None else frozenset()

    def _run_kinds(self, run) -> frozenset:
        rpr = run.find(_W_RPR)
        if rpr is None:
            return frozenset()
        kinds = set(self._rpr_to_kinds(rpr))
        rstyle = rpr.find(_W_RSTYLE)
        if rstyle is not None:
            style_rpr = self.numbering.style_rpr.get(rstyle.get(_W_VAL, ""))
            if style_rpr is not None:
                kinds |= self._rpr_to_kinds(style_rpr)
        return frozenset(kinds)

    @staticmethod
    def _rpr_to_kinds(rpr) -> frozenset:
        def flag(tag: str) -> bool:
            el = rpr.find(qn(tag))
            return el is not None and (el.get(_W_VAL) or "true").lower() not in _W_FALSE

        kinds = set()
        if flag("w:b"):
            kinds.add("bold")
        if flag("w:i"):
            kinds.add("italic")
        underline = rpr.find(qn("w:u"))
        if underline is not None and (underline.get(_W_VAL) or "single").lower() not in _W_FALSE:
            kinds.add("underline")
        highlight = rpr.find(qn("w:highlight"))
        if highlight is not None and (highlight.get(_W_VAL) or "").lower() not in _W_FALSE:
            kinds.add("highlight")
        shading = rpr.find(qn("w:shd"))
        if shading is not None and (shading.get(qn("w:fill")) or "auto").upper() not in {"AUTO", "FFFFFF"}:
            kinds.add("highlight")
        color = rpr.find(qn("w:color"))
        if color is not None:
            value = (color.get(_W_VAL) or "auto").upper()
            if value not in _NEUTRAL_COLORS:
                kinds.add(f"color:{value}")
        return frozenset(kinds)

    def _add_image(self, rid: str) -> None:
        if self.image_sink is not None:
            self.image_sink.append(rid)
            return
        self._flush_lines()
        if rid in self.seen_images:
            return
        self.seen_images.add(rid)

        part = self.doc.part.related_parts.get(rid)
        blob = getattr(part, "blob", None)
        if not blob:
            return

        if self.ocr.is_available:
            try:
                text = self.ocr.ocr_image(blob)
            except Exception as exc:
                logger.warning("Local OCR failed on DOCX image %s: %s", rid, exc)
                text = ""
            if text.strip():
                self.result.segments.append(TextSegment(text=text, source="ocr", label=rid))
                self.result.ocr_images += 1
            return

        jpeg = _to_jpeg(blob)
        if jpeg:
            self.result.segments.append(TextSegment(source="pending", image=jpeg, label=rid))

    def _flush_lines(self) -> None:
        if not self.lines:
            return
        _mark_emphasized_options(self.lines)
        text = "\n".join(line.text for line in self.lines)
        self.result.segments.append(TextSegment(text=text))
        self.lines = []


def _already_has_list_prefix(raw_text: str, prefix: str) -> bool:
    stripped = raw_text.lstrip()
    token = prefix.strip()
    if stripped.lower().startswith(token.lower()):
        return True
    # Nếu paragraph đã tự gõ "A. ..." hoặc "Câu 1..." thì không chèn thêm prefix tự động
    if _OPTION_LINE_PATTERN.match(stripped) and re.match(r"^[A-Da-d][.):]$", token):
        return True
    if re.match(r"^(?:Câu|Question)?\s*\d{1,4}\s*[.:)]", stripped, re.IGNORECASE) and re.search(r"\d", token):
        return True
    return False


def _to_jpeg(image_bytes: bytes) -> bytes | None:
    """Chuẩn hoá ảnh rời bất kỳ sang JPEG nền trắng (cho Gemini Vision fallback)."""
    pix = LocalOCREngine._prepare_pixmap(image_bytes)
    if pix is None:
        return None
    try:
        return pix.tobytes("jpeg")
    except Exception:
        return None
