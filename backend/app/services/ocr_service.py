"""
OCR Service - Nhận dạng chữ từ ảnh (ảnh scan trong PDF, ảnh chèn trong PDF/Word)
================================================================================

Engine: Tesseract được tích hợp sẵn trong PyMuPDF (MuPDF build kèm Tesseract).
→ KHÔNG cần cài thêm package Python hay binary ``tesseract.exe``; chỉ cần
  các file ngôn ngữ ``*.traineddata`` (vd: ``vie.traineddata``, ``eng.traineddata``).

Thứ tự tìm thư mục tessdata:
1. Tham số ``tessdata_dir`` (từ Settings.TESSDATA_PREFIX)
2. Biến môi trường ``TESSDATA_PREFIX``
3. Thư mục ``backend/tessdata`` của dự án (có sẵn / tải bằng scripts/download_tessdata.py)
4. Tesseract cài trên máy (``pymupdf.get_tessdata()``)

Các xử lý chuyên biệt cho đề thi/tài liệu tiếng Việt:
- Adaptive DPI theo kích thước trang/vùng ảnh (tránh tràn RAM với PDF 1px=1pt,
  đồng thời giữ độ nét cao cho ảnh nhỏ chèn trong PDF/Word)
- Làm phẳng kênh trong suốt (alpha) lên nền TRẮNG (tránh nền đen làm mù OCR)
- Tự đảo màu cho ảnh chụp màn hình nền tối (dark mode)
- Khôi phục khoảng trắng tiếng Việt cho font ``GlyphLessFont`` của Tesseract
- Tự xoay lại (90°/270°) khi phát hiện trang scan bị chụp ngang
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from functools import cached_property
from pathlib import Path

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# backend/tessdata — thư mục mặc định trong dự án
PROJECT_TESSDATA_DIR = Path(__file__).resolve().parents[2] / "tessdata"


class OCRUnavailableError(RuntimeError):
    """Không có engine OCR cục bộ khả dụng (thiếu tessdata)."""


def extract_text_from_textpage(
    page: fitz.Page,
    textpage: fitz.TextPage | None = None,
) -> str:
    """
    Trích xuất text từ ``TextPage`` (OCR hoặc hỗn hợp text + OCR) mà không mất
    khoảng trắng sau các ký tự tiếng Việt có dấu chồng (``ủ``, ``ố``, ``ồ``, ``ở``, ``ộ``).

    Nguyên nhân: lớp chữ OCR của MuPDF dùng ``GlyphLessFont`` với mỗi từ là 1
    span riêng, và đôi khi không chèn ký tự ``' '`` giữa hai span mà chỉ thể hiện
    bằng khoảng cách toạ độ ngang ``x0 - prev_x1``.
    """
    data = page.get_text("rawdict", textpage=textpage)
    blocks = [b for b in data.get("blocks", []) if b.get("type") == 0]
    blocks.sort(key=lambda b: (round(b["bbox"][1] / 6.0), b["bbox"][0]))

    out_blocks: list[str] = []
    for block in blocks:
        block_lines: list[str] = []
        lines = sorted(block.get("lines", []), key=lambda ln: (round(ln["bbox"][1] / 4.0), ln["bbox"][0]))
        for line in lines:
            parts: list[str] = []
            prev_x1: float | None = None
            prev_size: float = 12.0
            prev_ocr = False
            for span in line.get("spans", []):
                chars = span.get("chars") or []
                if not chars:
                    continue
                is_ocr = span.get("font") == "GlyphLessFont"
                size = float(span.get("size") or prev_size or 12.0)
                for ch_info in chars:
                    ch = ch_info.get("c") or ""
                    if not ch:
                        continue
                    x0, _, x1, _ = ch_info["bbox"]
                    if (
                        parts
                        and not parts[-1].endswith((" ", "\t"))
                        and ch not in (" ", "\t")
                        and prev_x1 is not None
                    ):
                        gap = float(x0) - prev_x1
                        min_size = max(1.0, min(size, prev_size))
                        # Trong GlyphLessFont, các ký tự cùng 1 từ luôn chạm sát nhau (gap == 0),
                        # còn hai từ khác nhau có khoảng hở x0 - prev_x1 >= ~0.12 * font_size
                        # (kể cả khi MuPDF gộp 2 từ cùng cỡ chữ vào chung 1 span).
                        threshold = 0.10 * min_size if (is_ocr or prev_ocr) else 0.22 * min_size
                        if gap > threshold:
                            parts.append(" ")
                    parts.append(ch)
                    prev_x1 = float(x1)
                    prev_size = size
                    prev_ocr = is_ocr

            line_text = "".join(parts).strip()
            if line_text:
                block_lines.append(line_text)
        if block_lines:
            out_blocks.append("\n".join(block_lines))

    return unicodedata.normalize("NFC", "\n\n".join(out_blocks))


class LocalOCREngine:
    """
    OCR cục bộ dùng Tesseract nhúng trong PyMuPDF.

    Usage:
        ocr = LocalOCREngine(languages="vie+eng")
        if ocr.is_available:
            text = ocr.ocr_page(page)                # OCR cả trang PDF scan
            text = ocr.ocr_clip(page, rect)          # OCR vùng ảnh chèn trong PDF
            text = ocr.ocr_image(image_bytes)        # OCR ảnh rời (vd: ảnh trong DOCX)
    """

    # Ảnh nhỏ hơn ngưỡng này (px) gần như chắc chắn là icon/logo → bỏ qua
    MIN_IMAGE_SIDE = 32
    # Cạnh dài tối thiểu mong muốn khi phóng to ảnh độ phân giải thấp
    UPSCALE_BELOW = 1400
    # Giới hạn cạnh dài bitmap khi render trang/ảnh để bảo vệ bộ nhớ
    MAX_RENDER_SIDE = 3500
    # Ngưỡng độ sáng trung bình dưới đó ảnh được coi là nền tối (dark mode)
    DARK_BG_LUMA_THRESHOLD = 85

    def __init__(
        self,
        languages: str = "vie+eng",
        dpi: int = 300,
        tessdata_dir: str | None = None,
        enabled: bool = True,
    ):
        self.requested_languages = languages or "eng"
        self.dpi = dpi
        self._tessdata_hint = tessdata_dir
        self.enabled = enabled

    @classmethod
    def from_settings(cls, settings) -> "LocalOCREngine":
        return cls(
            languages=getattr(settings, "OCR_LANGUAGES", "vie+eng"),
            dpi=getattr(settings, "OCR_DPI", 300),
            tessdata_dir=getattr(settings, "TESSDATA_PREFIX", None),
            enabled=getattr(settings, "OCR_ENABLED", True),
        )

    # ============================================
    # Availability
    # ============================================

    @cached_property
    def tessdata(self) -> str | None:
        """Đường dẫn thư mục tessdata hợp lệ, hoặc None."""
        candidates = [
            self._tessdata_hint,
            os.environ.get("TESSDATA_PREFIX"),
            str(PROJECT_TESSDATA_DIR),
        ]
        for candidate in candidates:
            if candidate and Path(candidate).is_dir() and any(Path(candidate).glob("*.traineddata")):
                return str(Path(candidate))

        try:
            system_dir = fitz.get_tessdata()
            if system_dir and Path(system_dir).is_dir() and any(Path(system_dir).glob("*.traineddata")):
                return str(Path(system_dir))
        except Exception:
            pass
        return None

    @cached_property
    def languages(self) -> str | None:
        """Chỉ giữ những ngôn ngữ có file traineddata thật sự tồn tại."""
        if not self.tessdata:
            return None
        available = [
            lang for lang in self.requested_languages.split("+")
            if lang and (Path(self.tessdata) / f"{lang}.traineddata").is_file()
        ]
        missing = set(self.requested_languages.split("+")) - set(available) - {""}
        if missing:
            logger.warning(
                "OCR language data missing in %s: %s", self.tessdata, ", ".join(sorted(missing))
            )
        if not available:
            # Fallback nếu thư mục có sẵn eng.traineddata hoặc bất kỳ ngôn ngữ nào
            fallback = sorted(p.stem for p in Path(self.tessdata).glob("*.traineddata") if p.stem != "osd")
            available = fallback[:1]
        return "+".join(available) or None

    @property
    def is_available(self) -> bool:
        return bool(self.enabled and self.tessdata and self.languages)

    def _require(self) -> None:
        if not self.is_available:
            raise OCRUnavailableError(
                "Local OCR is unavailable: no Tesseract language data found. "
                "Run `python scripts/download_tessdata.py` or set TESSDATA_PREFIX."
            )

    # ============================================
    # OCR operations
    # ============================================

    def ocr_page(self, page: fitz.Page, full: bool = True) -> str:
        """
        OCR một trang PDF.

        - ``full=True``: render cả trang với DPI thích ứng (chuẩn hoá nền sáng,
          tự khôi phục nếu ảnh scan bị xoay ngang 90°/270°) rồi OCR.
        - ``full=False``: giữ nguyên text gốc của trang, chỉ OCR các vùng ảnh.
        """
        self._require()
        dpi = self.adaptive_dpi(page.rect, preferred_dpi=self.dpi)

        if not full:
            textpage = page.get_textpage_ocr(
                flags=fitz.TEXT_DEHYPHENATE,
                language=self.languages,
                dpi=dpi,
                full=False,
                tessdata=self.tessdata,
            )
            return extract_text_from_textpage(page, textpage)

        pix = page.get_pixmap(dpi=dpi, alpha=False)
        return self._ocr_pixmap(pix, allow_rotate=True)

    def ocr_clip(
        self,
        page: fitz.Page,
        clip_rect: fitz.Rect,
        native_dpi: float | None = None,
    ) -> str:
        """
        OCR một vùng ảnh cụ thể được đưa vào trang PDF.

        Nếu ảnh gốc nhúng trong PDF có độ phân giải thực cao hơn ``self.dpi``
        (ví dụ ảnh chụp lớn được thu nhỏ trên trang PDF), tự nâng DPI render
        lên sát độ phân giải gốc (tối đa 600 DPI và không quá MAX_RENDER_SIDE)
        để không làm mờ chữ nhỏ trong ảnh.
        """
        self._require()
        preferred = self.dpi
        if native_dpi and native_dpi > preferred:
            preferred = min(600, int(round(native_dpi)))
        dpi = self.adaptive_dpi(clip_rect, preferred_dpi=preferred, min_side_px=900)
        pix = page.get_pixmap(dpi=dpi, clip=clip_rect, alpha=False)
        if min(pix.width, pix.height) < self.MIN_IMAGE_SIDE:
            return ""
        return self._ocr_pixmap(pix, allow_rotate=True)

    def ocr_image(self, image_bytes: bytes) -> str:
        """
        OCR một ảnh rời (PNG/JPEG/BMP/TIFF/GIF/WebP... chèn trong Word hoặc PDF).
        """
        self._require()
        pix = self._prepare_pixmap(image_bytes)
        if pix is None:
            return ""
        return self._ocr_pixmap(pix, allow_rotate=True)

    # ============================================
    # Pixmap preparation & rotation recovery
    # ============================================

    @classmethod
    def adaptive_dpi(
        cls,
        rect: fitz.Rect,
        preferred_dpi: int = 300,
        min_side_px: int = 1400,
    ) -> int:
        """
        Tính DPI hợp lý cho ``rect`` (đơn vị PDF point = 1/72 inch):
        - Không vượt quá ``MAX_RENDER_SIDE`` (tránh tràn bộ nhớ với PDF scan 1px=1pt)
        - Nâng DPI cho vùng ảnh nhỏ để chữ đủ lớn cho Tesseract
        """
        longest_pt = max(float(rect.width), float(rect.height), 1.0)
        dpi = max(72, int(preferred_dpi))

        longest_px = longest_pt * dpi / 72.0
        if longest_px < min_side_px:
            dpi = min(600, int(min_side_px * 72.0 / longest_pt))
            longest_px = longest_pt * dpi / 72.0

        if longest_px > cls.MAX_RENDER_SIDE:
            dpi = max(72, int(cls.MAX_RENDER_SIDE * 72.0 / longest_pt))
        return dpi

    def _ocr_pixmap(self, pix: fitz.Pixmap, allow_rotate: bool = True) -> str:
        pix = self._normalize_background(pix)
        text = self._run_tesseract_on_pixmap(pix)

        if allow_rotate and self._looks_sideways_gibberish(text):
            initial_score = self._text_quality_score(text)
            best_text = text
            best_score = initial_score
            for angle in (90, 270):
                rotated = self._rotate_pixmap(pix, angle)
                candidate = self._run_tesseract_on_pixmap(rotated)
                score = self._text_quality_score(candidate)
                if score > best_score:
                    best_text = candidate
                    best_score = score
            if best_score > max(initial_score * 1.35, initial_score + 1.5):
                text = best_text

        return text

    def _run_tesseract_on_pixmap(self, pix: fitz.Pixmap) -> str:
        # Đảm bảo metadata DPI >= 300 để mô hình LSTM tiếng Việt của Tesseract nhận dấu chuẩn
        if (pix.xres or 0) < 240 or (pix.yres or 0) < 240:
            pix.set_dpi(300, 300)
        pdf_bytes = pix.pdfocr_tobytes(language=self.languages, tessdata=self.tessdata)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            return "\n".join(extract_text_from_textpage(page) for page in doc).strip()
        finally:
            doc.close()

    @classmethod
    def _prepare_pixmap(cls, image_bytes: bytes) -> fitz.Pixmap | None:
        """
        Chuẩn hoá ảnh rời về RGB nền trắng (không alpha), phóng to nếu ảnh nhỏ.

        Lưu ý: KHÔNG dùng ``fitz.Pixmap(pix, 0)`` để bỏ kênh alpha vì thao tác đó
        giữ nguyên RGB=(0,0,0) của vùng trong suốt → biến nền trong suốt thành
        nền đen tuyền, làm mất toàn bộ chữ màu đen!
        """
        try:
            raw = fitz.Pixmap(image_bytes)
        except Exception:
            # Định dạng MuPDF không đọc được (EMF/WMF...) → bỏ qua ảnh
            return None

        if min(raw.width, raw.height) < cls.MIN_IMAGE_SIDE:
            return None

        longest = max(raw.width, raw.height)
        scale = 1.0
        if longest < cls.UPSCALE_BELOW:
            scale = min(3.0, cls.UPSCALE_BELOW / longest)
        elif longest > cls.MAX_RENDER_SIDE:
            scale = cls.MAX_RENDER_SIDE / longest

        needs_page_composite = (
            raw.alpha
            or raw.colorspace is None
            or raw.colorspace.n not in (1, 3)
            or abs(scale - 1.0) > 0.05
        )
        if not needs_page_composite:
            return raw

        target_w = max(1, int(round(raw.width * scale)))
        target_h = max(1, int(round(raw.height * scale)))
        doc = fitz.open()
        try:
            page = doc.new_page(width=target_w, height=target_h)
            page.insert_image(page.rect, stream=image_bytes)
            return page.get_pixmap(dpi=72, alpha=False)
        except Exception:
            return None
        finally:
            doc.close()

    @classmethod
    def _normalize_background(cls, pix: fitz.Pixmap) -> fitz.Pixmap:
        """Nếu ảnh có nền tối (dark mode screenshot), đảo màu về chữ đen nền sáng."""
        samples = pix.samples
        if not samples:
            return pix
        step = max(1, len(samples) // 4096)
        sampled = samples[::step]
        mean_luma = sum(sampled) / len(sampled)
        if mean_luma < cls.DARK_BG_LUMA_THRESHOLD:
            inverted = fitz.Pixmap(pix)
            inverted.invert_irect(inverted.irect)
            return inverted
        return pix

    @staticmethod
    def _rotate_pixmap(pix: fitz.Pixmap, angle: int) -> fitz.Pixmap:
        swap = angle in (90, 270)
        w, h = (pix.height, pix.width) if swap else (pix.width, pix.height)
        doc = fitz.open()
        try:
            page = doc.new_page(width=w, height=h)
            page.insert_image(page.rect, pixmap=pix, rotate=angle)
            return page.get_pixmap(dpi=72, alpha=False)
        finally:
            doc.close()

    @staticmethod
    def _looks_sideways_gibberish(text: str) -> bool:
        """Nhận diện kết quả OCR bị vỡ vụn do ảnh scan nằm ngang (90°/270°)."""
        lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
        if len(lines) < 4:
            return False
        avg_len = sum(len(ln) for ln in lines) / len(lines)
        clean_multi_word = sum(
            1 for ln in lines
            if sum(1 for tok in ln.split() if re.fullmatch(r"[^\W\d_]{2,}[.,?:;)]?", tok)) >= 3
        )
        return avg_len < 10.0 and (clean_multi_word / len(lines)) < 0.25

    @staticmethod
    def _text_quality_score(text: str) -> float:
        """Điểm mật độ từ sạch trên mỗi dòng để chọn chiều xoay đúng nhất."""
        if not text or not text.strip():
            return 0.0
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return 0.0
        clean_words = sum(
            1
            for ln in lines
            for tok in ln.split()
            if re.fullmatch(r"[^\W\d_]{2,}[.,?:;)]?", tok)
        )
        clean_chars = sum(1 for ch in text if ch.isalnum() or ch in " \n.,?:;()-/")
        clean_ratio = clean_chars / max(1, len(text))
        words_per_line = clean_words / len(lines)
        quiz_markers = len(re.findall(r"(?m)^\s*(?:Câu\s*\d+|[A-D][.):])\s+\S", text))
        return (words_per_line * 6.0 + min(clean_words, 40) * 0.3 + quiz_markers * 4.0) * clean_ratio
