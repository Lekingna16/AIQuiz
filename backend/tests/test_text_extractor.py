"""
Test Text Extractor & OCR - Unit tests cho đọc file PDF, Word, TXT và ảnh scan
==============================================================================

Bao phủ:
- TXT: UTF-8, BOM, Latin-1, VNI-Windows, TCVN3
- DOCX: thứ tự tài liệu (paragraph + bảng xen kẽ), đánh số tự động (numPr),
  bảng phương án 2x2 không dính '|', đáp án tô đậm/tô màu/highlight, công thức
  toán OMML, ảnh chụp câu hỏi chèn trong Word (OCR), từ chối file .doc nhị phân cũ
- PDF: text gốc, nhận diện đáp án tô đậm/tô màu/highlight, trang scan tiếng Việt,
  trang scan dính watermark CamScanner, ảnh bị cắt dải ngang, trang scan xoay 90°,
  trang có lớp OCR cũ bị hỏng, trang lai (chữ gốc + ảnh chụp câu hỏi xen kẽ đúng
  thứ tự toạ độ), ảnh PNG nền trong suốt, và chế độ fallback Gemini Vision khi tắt OCR cục bộ
"""

from io import BytesIO

import fitz
import pytest
from docx import Document
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Inches, RGBColor

from app.services.ocr_service import LocalOCREngine
from app.services.text_extractor import TextExtractor
from app.utils.question_parser import parse_questions_from_text


# ============================================
# HELPERS & FIXTURES
# ============================================

def _make_html_image(html: str, width: int = 540, height: int = 240, dpi: int = 240) -> bytes:
    """Render một đoạn HTML tiếng Việt thành ảnh PNG sắc nét phục vụ test OCR."""
    doc = fitz.open()
    try:
        page = doc.new_page(width=width, height=height)
        styled = (
            "<div style='font-family:sans-serif;font-size:13pt;line-height:1.4;color:#000'>"
            f"{html}</div>"
        )
        page.insert_htmlbox(fitz.Rect(18, 16, width - 18, height - 16), styled)
        return page.get_pixmap(dpi=dpi, alpha=False).tobytes("png")
    finally:
        doc.close()


@pytest.fixture
def extractor():
    """Tạo TextExtractor instance (tự dùng backend/tessdata nếu có)."""
    return TextExtractor()


@pytest.fixture
def extractor_no_local_ocr():
    """TextExtractor khi không có OCR cục bộ (test luồng pending → Gemini Vision)."""
    return TextExtractor(ocr=LocalOCREngine(enabled=False))


@pytest.fixture
def sample_txt_bytes():
    text = (
        "Đây là nội dung tài liệu mẫu bằng tiếng Việt.\n"
        "Python là ngôn ngữ lập trình phổ biến nhất thế giới.\n"
        "Machine Learning là nhánh con của Artificial Intelligence.\n"
        "FastAPI là web framework hiện đại cho Python.\n"
        "MongoDB là cơ sở dữ liệu NoSQL document-oriented.\n"
    )
    return text.encode("utf-8")


@pytest.fixture
def sample_docx_bytes():
    doc = Document()
    doc.add_heading("Bài giảng Python cơ bản", level=1)
    doc.add_paragraph(
        "Python là ngôn ngữ lập trình bậc cao, được thiết kế bởi "
        "Guido van Rossum và ra mắt lần đầu vào năm 1991."
    )
    doc.add_paragraph(
        "Python hỗ trợ nhiều paradigm: lập trình hướng đối tượng, "
        "lập trình hàm, và lập trình thủ tục."
    )
    doc.add_paragraph(
        "Các thư viện phổ biến: NumPy, Pandas, TensorFlow, FastAPI, Django."
    )

    table = doc.add_table(rows=3, cols=2)
    table.cell(0, 0).text = "Library"
    table.cell(0, 1).text = "Use Case"
    table.cell(1, 0).text = "NumPy"
    table.cell(1, 1).text = "Scientific Computing"
    table.cell(2, 0).text = "FastAPI"
    table.cell(2, 1).text = "Web APIs"

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def sample_pdf_bytes():
    doc = fitz.open()
    page = doc.new_page()
    text = (
        "Machine Learning Fundamentals\n\n"
        "Machine Learning is a subset of Artificial Intelligence that "
        "enables computers to learn from data without being explicitly "
        "programmed.\n\n"
        "Supervised Learning includes algorithms like Linear Regression, "
        "Decision Trees, and Neural Networks.\n\n"
        "Unsupervised Learning includes Clustering, Dimensionality "
        "Reduction, and Association Rules."
    )
    page.insert_textbox(fitz.Rect(72, 72, 540, 720), text, fontsize=12)
    buffer = BytesIO()
    doc.save(buffer)
    doc.close()
    return buffer.getvalue()


# ============================================
# TXT & LEGACY ENCODING TESTS
# ============================================

class TestTxtAndEncodings:
    def test_extract_utf8(self, extractor, sample_txt_bytes):
        result = extractor.extract(sample_txt_bytes, "txt")
        assert "Python" in result
        assert "tiếng Việt" in result

    def test_extract_txt_with_bom(self, extractor):
        bom = b"\xef\xbb\xbf"
        content = bom + "Hello World with BOM marker and enough content to make this longer than minimum".encode("utf-8")
        result = extractor.extract(content, "txt")
        assert result.startswith("Hello World")

    def test_extract_txt_utf16(self, extractor):
        content = "Tài liệu tiếng Việt lưu ở định dạng UTF-16 từ Notepad trên Windows.".encode("utf-16")
        result = extractor.extract(content, "txt")
        assert "Tài liệu tiếng Việt" in result

    def test_extract_txt_latin1(self, extractor):
        content = "Café résumé naïve".encode("latin-1")
        result = extractor.extract(content, "txt")
        assert len(result) > 0

    def test_extract_empty_txt(self, extractor):
        assert extractor.extract(b"", "txt") == ""

    def test_vni_windows_converted_to_unicode(self, extractor):
        vni_text = (
            "Caâu 1: Ñaùp aùn ñuùng trong tröôøng hôïp naøy cuûa Vieät Nam laø gì?\n"
            "A. Haø Noäi\nB. Ñaø Naüng\nC. Hueá\nD. Caàn Thô"
        )
        result = extractor.extract(vni_text.encode("utf-8"), "txt")
        assert "Câu 1: Đáp án đúng trong trường hợp này của Việt Nam là gì?" in result
        assert "A. Hà Nội" in result
        assert "B. Đà Nẵng" in result


# ============================================
# DOCX EXTRACTION TESTS
# ============================================

class TestDocxExtraction:
    def test_extract_docx(self, extractor, sample_docx_bytes):
        result = extractor.extract(sample_docx_bytes, "docx")
        assert "Python" in result
        assert "Guido van Rossum" in result
        assert "NumPy | Scientific Computing" in result
        assert "FastAPI | Web APIs" in result

    def test_extract_docx_preserves_interleaved_order(self, extractor):
        """Bảng nằm giữa hai đoạn văn phải giữ đúng vị trí giữa hai đoạn đó."""
        doc = Document()
        doc.add_paragraph("ĐOẠN ĐẦU TRƯỚC BẢNG")
        tbl = doc.add_table(rows=1, cols=2)
        tbl.cell(0, 0).text = "Cột 1"
        tbl.cell(0, 1).text = "Cột 2"
        doc.add_paragraph("ĐOẠN SAU BẢNG")

        buf = BytesIO()
        doc.save(buf)
        result = extractor.extract(buf.getvalue(), "docx")
        assert result.index("ĐOẠN ĐẦU") < result.index("Cột 1 | Cột 2") < result.index("ĐOẠN SAU")

    def test_extract_docx_option_table_and_colored_answer(self, extractor):
        """Bảng 2x2 chứa phương án A/B/C/D không được chèn '|' và phải giữ đáp án tô màu."""
        doc = Document()
        doc.add_paragraph("Câu 1: Chiến thắng Điện Biên Phủ diễn ra vào năm nào?")
        tbl = doc.add_table(rows=2, cols=2)
        tbl.cell(0, 0).paragraphs[0].add_run("A. 1945")
        run_b = tbl.cell(0, 1).paragraphs[0].add_run("B. 1954")
        run_b.font.color.rgb = RGBColor(0xFF, 0x00, 0x00)
        tbl.cell(1, 0).paragraphs[0].add_run("C. 1968")
        tbl.cell(1, 1).paragraphs[0].add_run("D. 1975")

        buf = BytesIO()
        doc.save(buf)
        text = extractor.extract(buf.getvalue(), "docx")
        assert "|" not in text
        questions = parse_questions_from_text(text)
        assert len(questions) == 1
        assert questions[0]["correct_answer"] == "B"
        assert questions[0]["options"][0]["text"] == "1945"

    def test_extract_docx_inline_tabbed_options_with_bold_answer(self, extractor):
        """Phương án viết trên cùng 1 dòng ngăn bằng Tab, có 1 phương án in đậm."""
        doc = Document()
        doc.add_paragraph("Câu 1: Thủ đô của Việt Nam là thành phố nào?")
        p = doc.add_paragraph()
        p.add_run("A. Huế\t")
        r_b = p.add_run("B. Hà Nội")
        r_b.bold = True
        p.add_run("\tC. Đà Nẵng\tD. Cần Thơ")

        buf = BytesIO()
        doc.save(buf)
        text = extractor.extract(buf.getvalue(), "docx")
        questions = parse_questions_from_text(text)
        assert len(questions) == 1
        assert questions[0]["correct_answer"] == "B"

    def test_extract_docx_auto_numbering_lists(self, extractor):
        """Khôi phục A., B., C., D. khi giáo viên dùng Numbering tự động của Word."""
        doc = Document()
        numbering_part = doc.part.numbering_part
        numbering_el = numbering_part.element
        abs_xml = parse_xml(
            f'<w:abstractNum {nsdecls("w")} w:abstractNumId="99">'
            '  <w:lvl w:ilvl="0">'
            '    <w:start w:val="1"/>'
            '    <w:numFmt w:val="upperLetter"/>'
            '    <w:lvlText w:val="%1."/>'
            '  </w:lvl>'
            '</w:abstractNum>'
        )
        num_xml = parse_xml(
            f'<w:num {nsdecls("w")} w:numId="99">'
            '  <w:abstractNumId w:val="99"/>'
            '</w:num>'
        )
        numbering_el.append(abs_xml)
        numbering_el.append(num_xml)

        doc.add_paragraph("Câu 1: Kim loại nào dẫn điện tốt nhất?")
        for opt_text in ("Nhôm", "Bạc", "Đồng", "Sắt"):
            p = doc.add_paragraph(opt_text)
            ppr = p._p.get_or_add_pPr()
            numpr = OxmlElement("w:numPr")
            ilvl = OxmlElement("w:ilvl")
            ilvl.set(qn("w:val"), "0")
            numid = OxmlElement("w:numId")
            numid.set(qn("w:val"), "99")
            numpr.append(ilvl)
            numpr.append(numid)
            ppr.append(numpr)

        buf = BytesIO()
        doc.save(buf)
        text = extractor.extract(buf.getvalue(), "docx")
        questions = parse_questions_from_text(text)
        assert len(questions) == 1
        assert [o["key"] for o in questions[0]["options"]] == ["A", "B", "C", "D"]
        assert questions[0]["options"][1]["text"] == "Bạc"

    def test_extract_docx_omml_math(self, extractor):
        """Đọc công thức toán học OMML (phân số & số mũ)."""
        doc = Document()
        p = doc.add_paragraph("Tính giá trị biểu thức ")
        omath = parse_xml(
            '<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
            '  <m:f>'
            '    <m:num><m:sSup><m:e><m:r><m:t>x</m:t></m:r></m:e><m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup></m:num>'
            '    <m:den><m:r><m:t>2</m:t></m:r></m:den>'
            '  </m:f>'
            '</m:oMath>'
        )
        p._p.append(omath)
        buf = BytesIO()
        doc.save(buf)
        text = extractor.extract(buf.getvalue(), "docx")
        assert "(x^2)/2" in text

    def test_extract_docx_embedded_image_ocr(self, extractor):
        """Ảnh chụp câu hỏi chèn trong file Word được OCR sang tiếng Việt."""
        assert extractor.ocr.is_available, "Local OCR tessdata should be present in backend/tessdata"
        img = _make_html_image(
            "Câu 1: Thủ đô của Việt Nam là thành phố nào?<br/>"
            "A. Hà Nội<br/>B. Hồ Chí Minh<br/>C. Đà Nẵng<br/>D. Huế"
        )
        doc = Document()
        doc.add_paragraph("Phần trắc nghiệm từ ảnh chụp:")
        doc.add_picture(BytesIO(img), width=Inches(5.0))
        buf = BytesIO()
        doc.save(buf)

        res = extractor.extract_document(buf.getvalue(), "docx")
        text = extractor.finalize_text(res)
        assert res.ocr_images == 1
        assert "Thủ đô của Việt Nam" in text
        questions = parse_questions_from_text(text)
        assert len(questions) == 1

    def test_rejects_legacy_binary_doc_renamed_to_docx(self, extractor):
        ole2_fake = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 128
        with pytest.raises(ValueError, match="Legacy Word 97-2003"):
            extractor.extract(ole2_fake, "docx")


# ============================================
# PDF & SCANNED IMAGE OCR TESTS
# ============================================

class TestPdfAndScannedOcr:
    def test_extract_pdf(self, extractor, sample_pdf_bytes):
        result = extractor.extract(sample_pdf_bytes, "pdf")
        assert "Machine Learning" in result
        assert "Supervised Learning" in result
        assert "\x00" not in result

    def test_pdf_detects_highlighted_and_colored_answers(self, extractor):
        """PDF gốc có phương án được tô highlight hoặc đổi màu chữ → nhận diện đáp án đúng."""
        doc = fitz.open()
        page = doc.new_page()
        page.insert_htmlbox(
            fitz.Rect(50, 50, 540, 260),
            "<div style='font-family:sans-serif;font-size:12pt;line-height:1.5'>"
            "Câu 1: Sông nào dài nhất thế giới?<br/>"
            "A. Sông Hồng<br/>"
            "B. Sông Mê Kông<br/>"
            "<span style='color:#d00000;font-weight:bold'>C. Sông Nin</span><br/>"
            "D. Sông Hương"
            "</div>",
        )
        pdf_bytes = doc.tobytes()
        doc.close()

        text = extractor.extract(pdf_bytes, "pdf")
        questions = parse_questions_from_text(text)
        assert len(questions) == 1
        assert questions[0]["correct_answer"] == "C"

    def test_scanned_pdf_vietnamese_ocr(self, extractor):
        """PDF chỉ chứa ảnh scan đề thi tiếng Việt → OCR đọc chính xác chữ và dấu cách."""
        assert extractor.ocr.is_available
        img = _make_html_image(
            "Câu 1: Thủ đô của Việt Nam là thành phố nào?<br/>"
            "A. Hà Nội<br/>B. Hồ Chí Minh<br/>C. Đà Nẵng<br/>D. Huế<br/>"
            "Câu 2: Nước sôi ở bao nhiêu độ C?<br/>"
            "A. 90<br/>B. 100<br/>C. 80<br/>D. 120",
            height=300,
        )
        doc = fitz.open()
        page = doc.new_page()
        page.insert_image(fitz.Rect(36, 36, 560, 360), stream=img)
        pdf_bytes = doc.tobytes()
        doc.close()

        res = extractor.extract_document(pdf_bytes, "pdf")
        text = extractor.finalize_text(res)
        assert res.ocr_pages == [1]
        assert "Thủ đô của Việt Nam là thành phố nào?" in text
        assert "Hồ Chí Minh" in text
        questions = parse_questions_from_text(text)
        assert len(questions) == 2

    def test_scanned_pdf_with_camscanner_watermark_still_ocrs(self, extractor):
        """Trang scan có dính dòng chữ watermark 'Scanned with CamScanner' + số trang vẫn phải được OCR."""
        assert extractor.ocr.is_available
        img = _make_html_image(
            "Câu 1: Hệ điều hành Linux thuộc loại mã nguồn nào?<br/>"
            "A. Mã nguồn mở<br/>B. Độc quyền<br/>C. Đóng<br/>D. Thương mại"
        )
        doc = fitz.open()
        page = doc.new_page()
        page.insert_image(fitz.Rect(20, 20, 575, 760), stream=img)
        page.insert_text((36, 810), "Scanned with CamScanner", fontsize=10)
        page.insert_text((500, 810), "Page 1 of 3", fontsize=10)
        pdf_bytes = doc.tobytes()
        doc.close()

        res = extractor.extract_document(pdf_bytes, "pdf")
        text = extractor.finalize_text(res)
        assert res.ocr_pages == [1]
        assert "CamScanner" not in text
        assert "Linux" in text
        assert len(parse_questions_from_text(text)) == 1

    def test_scanned_pdf_split_into_horizontal_strips(self, extractor):
        """Ảnh scan bị phần mềm cũ cắt thành nhiều dải ngang sát nhau vẫn được gộp và OCR nguyên vẹn."""
        assert extractor.ocr.is_available
        src_doc = fitz.open()
        src_page = src_doc.new_page(width=500, height=200)
        src_page.insert_htmlbox(
            fitz.Rect(18, 16, 482, 184),
            "<div style='font-family:sans-serif;font-size:13pt;line-height:1.4;color:#000'>"
            "Câu 1: Trái Đất quay quanh Mặt Trời mất bao lâu?<br/>"
            "A. 365 ngày<br/>B. 30 ngày<br/>C. 24 giờ<br/>D. 7 ngày</div>",
        )
        doc = fitz.open()
        page = doc.new_page()
        strips = 5
        strip_h = 200 / strips
        for i in range(strips):
            clip = fitz.Rect(0, i * strip_h, 500, (i + 1) * strip_h)
            clip_pix = src_page.get_pixmap(dpi=220, clip=clip, alpha=False)
            top_pt = 60 + i * strip_h
            bot_pt = 60 + (i + 1) * strip_h
            page.insert_image(fitz.Rect(50, top_pt, 550, bot_pt), pixmap=clip_pix)
        src_doc.close()
        pdf_bytes = doc.tobytes()
        doc.close()

        text = extractor.extract(pdf_bytes, "pdf")
        assert "Trái Đất" in text
        assert len(parse_questions_from_text(text)) == 1

    def test_mixed_pdf_interleaves_native_text_and_embedded_image_in_order(self, extractor):
        """Trang PDF vừa có chữ gốc (Câu 1, Câu 3) vừa chèn ảnh chụp (Câu 2 ở giữa) → đúng thứ tự 1-2-3."""
        assert extractor.ocr.is_available
        img_q2 = _make_html_image(
            "Câu 2: Hành tinh nào gần Mặt Trời nhất?<br/>"
            "A. Sao Thủy<br/>B. Sao Kim<br/>C. Sao Hỏa<br/>D. Sao Mộc",
            width=500,
            height=180,
        )
        doc = fitz.open()
        page = doc.new_page()
        page.insert_htmlbox(
            fitz.Rect(40, 30, 550, 150),
            "<div style='font-family:sans-serif;font-size:12pt'>"
            "Câu 1: Mặt Trời mọc ở hướng nào?<br/>"
            "A. Đông<br/>B. Tây<br/>C. Nam<br/>D. Bắc</div>",
        )
        page.insert_image(fitz.Rect(40, 170, 540, 350), stream=img_q2)
        page.insert_htmlbox(
            fitz.Rect(40, 380, 550, 520),
            "<div style='font-family:sans-serif;font-size:12pt'>"
            "Câu 3: Một năm nhuận có bao nhiêu ngày?<br/>"
            "A. 364<br/>B. 365<br/>C. 366<br/>D. 367</div>",
        )
        pdf_bytes = doc.tobytes()
        doc.close()

        res = extractor.extract_document(pdf_bytes, "pdf")
        text = extractor.finalize_text(res)
        assert res.ocr_images == 1
        assert text.index("Câu 1") < text.index("Câu 2") < text.index("Câu 3")
        questions = parse_questions_from_text(text)
        assert len(questions) == 3

    def test_transparent_png_flattened_to_white_not_black(self, extractor):
        """Ảnh PNG chữ đen trên nền trong suốt (RGBA=0,0,0,0) phải được làm phẳng lên nền trắng để OCR đọc được."""
        assert extractor.ocr.is_available
        src = fitz.open()
        p = src.new_page(width=480, height=160)
        p.insert_htmlbox(
            fitz.Rect(15, 15, 465, 145),
            "<div style='font-family:sans-serif;font-size:14pt;color:#000'>"
            "Câu 1: Công thức hóa học của nước là gì?<br/>"
            "A. H2O &nbsp;&nbsp; B. CO2 &nbsp;&nbsp; C. NaCl &nbsp;&nbsp; D. O2</div>",
        )
        rgba_png = p.get_pixmap(dpi=220, alpha=True).tobytes("png")
        src.close()

        ocr_text = extractor.ocr.ocr_image(rgba_png)
        assert "Công thức hóa học" in ocr_text

    def test_sideways_90deg_scanned_pdf_auto_rotated(self, extractor):
        """Ảnh scan bị đặt xoay ngang 90° trong PDF được tự động phát hiện và xoay lại để đọc."""
        assert extractor.ocr.is_available
        upright = _make_html_image(
            "Câu 1: Thủ đô của nước Pháp là thành phố nào?<br/>"
            "A. Paris<br/>B. London<br/>C. Berlin<br/>D. Madrid",
            width=480,
            height=190,
        )
        doc = fitz.open()
        page = doc.new_page(width=220, height=520)
        page.insert_image(fitz.Rect(15, 15, 205, 505), stream=upright, rotate=90)
        pdf_bytes = doc.tobytes()
        doc.close()

        text = extractor.extract(pdf_bytes, "pdf")
        assert "Paris" in text

    def test_pending_segments_created_when_local_ocr_disabled(self, extractor_no_local_ocr):
        """Khi tắt OCR cục bộ, trang scan tạo pending JPEG segment để Gemini Vision xử lý."""
        img = _make_html_image("Câu 1: Nội dung trên ảnh scan?")
        doc = fitz.open()
        page = doc.new_page()
        page.insert_image(fitz.Rect(40, 40, 540, 280), stream=img)
        pdf_bytes = doc.tobytes()
        doc.close()

        res = extractor_no_local_ocr.extract_document(pdf_bytes, "pdf")
        assert len(res.pending_segments) == 1
        assert res.pending_segments[0].image.startswith(b"\xff\xd8")
        res.resolve_pending(["Câu 1: Nội dung đã được Gemini OCR đọc thành công."])
        assert "Gemini OCR đọc thành công" in extractor_no_local_ocr.finalize_text(res)

    def test_render_scanned_pdf_pages_for_vision_ocr(self, extractor, sample_pdf_bytes):
        pages = extractor.render_scanned_pdf_pages(sample_pdf_bytes)
        assert len(pages) == 1
        assert pages[0].startswith(b"\xff\xd8")


# ============================================
# VALIDATION & EDGE CASES
# ============================================

class TestValidationAndEdgeCases:
    def test_validate_sufficient_text(self, extractor):
        is_valid, msg = extractor.validate_extracted_text("A" * 200)
        assert is_valid is True
        assert msg == ""

    def test_validate_short_text(self, extractor):
        is_valid, msg = extractor.validate_extracted_text("Short text")
        assert is_valid is False
        assert "too short" in msg

    def test_validate_empty_text(self, extractor):
        is_valid, msg = extractor.validate_extracted_text("")
        assert is_valid is False

    def test_validate_none_text(self, extractor):
        is_valid, _ = extractor.validate_extracted_text(None)
        assert is_valid is False

    def test_unsupported_file_type(self, extractor):
        with pytest.raises(ValueError, match="Unsupported file type"):
            extractor.extract(b"content", "xlsx")

    def test_file_type_case_and_whitespace(self, extractor, sample_txt_bytes):
        assert len(extractor.extract(sample_txt_bytes, "  TXT  ")) > 0

    def test_corrupt_docx(self, extractor):
        with pytest.raises(ValueError, match="Failed to extract"):
            extractor.extract(b"not a valid docx", "docx")

    def test_password_protected_pdf_rejected(self, extractor):
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Secret content")
        pdf_bytes = doc.tobytes(
            encryption=fitz.PDF_ENCRYPT_AES_256,
            owner_pw="owner123",
            user_pw="user123",
        )
        doc.close()
        with pytest.raises(ValueError, match="password-protected"):
            extractor.extract(pdf_bytes, "pdf")

    def test_clean_text_removes_watermarks_and_nulls(self, extractor):
        text = (
            "Question\x00 text\n"
            "Downloaded by someone@example.com\n"
            "lOMoARcPSD|34871021\n"
            "Scan to open on Studocu\n"
            "Scanned with CamScanner\n"
            "Answer text"
        )
        cleaned = extractor._clean_text(text)
        assert "\x00" not in cleaned
        assert "Studocu" not in cleaned
        assert "CamScanner" not in cleaned
        assert cleaned == "Question text\nAnswer text"

    def test_detects_damaged_ocr_text(self, extractor):
        assert extractor.has_damaged_ocr_text(
            "Nhà ntr6c có sự phân h6a giai cấp trong xa h0i."
        )
        assert not extractor.has_damaged_ocr_text(
            "Câu 10: Nhà nước có sự phân hóa giai cấp trong xã hội."
        )
