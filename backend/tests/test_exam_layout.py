import fitz
import pytest

from app.services.ocr_service import extract_text_from_textpage
from app.services.text_extractor import TextExtractor
from app.utils.question_parser import parse_questions_from_text


@pytest.mark.parametrize("keys", [("A", "B", "C", "D"), ("A", "C", "B", "D")])
@pytest.mark.parametrize("reader", ["native", "ocr_textpage"])
def test_two_column_choices_keep_their_wrapped_lines(keys, reader):
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((40, 40), "Cau 1: Question stem on one line")
        page.insert_text((40, 57), "continued before the options?")
        # Deliberately create the right column first in the PDF content stream.
        for key, x, y in [(keys[1], 330, 90), (keys[3], 330, 145),
                          (keys[0], 60, 90), (keys[2], 60, 145)]:
            page.insert_text((x, y), f"{key}. Choice {key} begins\nand continues for {key}", fontsize=11)
        page.insert_text((40, 200), "Cau 2: Next question?")
        for index, key in enumerate("ABCD"):
            page.insert_text((60, 225 + 18 * index), f"{key}. Next {key}")
        text = (TextExtractor().extract(doc.tobytes(), "pdf") if reader == "native"
                else extract_text_from_textpage(page))
    qs = parse_questions_from_text(text)
    assert len(qs) == 2
    assert qs[0]["question_text"] == "Question stem on one line continued before the options?"
    assert qs[0]["options"] == [
        {"key": key, "text": f"Choice {key} begins and continues for {key}"} for key in "ABCD"
    ]
    assert qs[1]["options"] == [{"key": key, "text": f"Next {key}"} for key in "ABCD"]
