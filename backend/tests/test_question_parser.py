from app.utils.question_parser import parse_questions_from_text


def test_parses_numeric_options_and_converts_them_to_abcd():
    text = """41. Câu hỏi thứ nhất?
1. Lựa chọn một
2. Lựa chọn hai
3. Lựa chọn ba
4. Lựa chọn bốn
42. Câu hỏi thứ hai?
1. Đáp án một
2. Đáp án hai
3. Đáp án ba
4. Đáp án bốn
"""

    questions = parse_questions_from_text(text)

    assert len(questions) == 2
    assert questions[0]["question_text"] == "Câu hỏi thứ nhất?"
    assert [option["key"] for option in questions[0]["options"]] == [
        "A", "B", "C", "D"
    ]
    assert questions[1]["options"][3]["text"] == "Đáp án bốn"


def test_parses_ocr_one_and_option_labels_without_text():
    text = """l. Câu hỏi bị OCR sai số một?
a.
Lựa chọn một
b.
Lựa chọn hai
c.
Lựa chọn ba
d.
Lựa chọn bốn
2
Câu hỏi có số thứ tự nằm trên dòng riêng?
a. Đúng
b. Sai
"""

    questions = parse_questions_from_text(text)

    assert len(questions) == 2
    assert questions[0]["question_text"] == "Câu hỏi bị OCR sai số một?"
    assert [option["text"] for option in questions[0]["options"]] == [
        "Lựa chọn một", "Lựa chọn hai", "Lựa chọn ba", "Lựa chọn bốn"
    ]
