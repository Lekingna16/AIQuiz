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


def test_does_not_crash_on_uppercase_i_and_recovers_ocr_d_option():
    text = """I. Phần trắc nghiệm nội khoa
Câu 1. Đặc điểm XQ ngực của tràn dịch màng phổi:
A. Mờ đồng nhất
C. Đường cong Damoiseau
B. Mất góc sườn hoành
D. Phế quản hơi
Câu 2. Tam chứng Galliard gồm:
A. Đau ngực, khó thở, gõ vang
C. Lồng ngực gồ, gõ vang
B. Đau ngực, mạch nhanh
I). Gõ vang, rung thanh giảm, âm phế bào giảm
"""

    questions = parse_questions_from_text(text)

    assert len(questions) == 2
    assert [o["key"] for o in questions[0]["options"]] == ["A", "B", "C", "D"]
    assert [o["key"] for o in questions[1]["options"]] == ["A", "B", "C", "D"]
    assert questions[1]["options"][3]["text"] == "Gõ vang, rung thanh giảm, âm phế bào giảm"


def test_parses_scanned_exam_ocr_variants_and_exam_code_answer_table():
    text = """TRƯỜNG ĐHYD CẦN THƠ
Mã đề thi: 2
TRẠM 1
Cau 1. Ý nào đúng về tăng huyết áp áo choàng trắng:
A. Tỉ lệ 12%
Ov
B. Vữa xơ thành mạch
oC. Khởi đầu tăng huyết áp
> D. Đo huyết áp tại phòng khám
Trang 1/5 - Mã đề thi 2
TRƯỜNG ĐHYD CẦN THƠ
"Câu 2. Thuốc điều trị trào ngược:
A, Dexlansoprazole
- B. Ranitidin
Cc. Sucralfate
© D. Misoprostol
Cầu 3. Triệu chứng suy thận:
TRẠM 2
A. Phù
B. Thiếu máu
C. Tăng huyết áp
cD. Tất cả đúng

mamon made cauhoi dapan
YY091602 1 1 A
YY091602 1 2 B
YY091602 1 3 C
YY091602 2 1 C
YY091602 2 2 A
YY091602 2 3 D
YY091602 2 4 B
YY091602 2 5 A
"""

    questions = parse_questions_from_text(text)

    assert len(questions) == 3
    assert [q["correct_answer"] for q in questions] == ["C", "A", "D"]
    assert "TRƯỜNG ĐHYD" not in questions[0]["options"][3]["text"]
    assert "Ov" not in questions[0]["options"][0]["text"]
