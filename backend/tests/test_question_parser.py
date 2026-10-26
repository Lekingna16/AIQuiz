from app.utils.question_parser import parse_questions_from_text


def test_shared_passage_belongs_to_following_question_range_not_previous_choice():
    options = "\nA. Mot\nB. Hai\nC. Ba\nD. Bon\n"
    text = (
        "Câu 6: Câu trước?" + options
        + "Phần câu hỏi 7-9: Một người đến khám.\nDữ kiện ở dòng tiếp theo.\n"
        + "Câu 7: Câu hỏi thứ bảy?" + options
        + "Câu 8: Câu hỏi thứ tám?" + options
        + "Câu 9: Câu hỏi thứ chín?" + options
        + "Câu 10: Ngoài nhóm?" + options
    )
    qs = parse_questions_from_text(text)
    assert len(qs) == 5
    assert qs[0]["options"][3]["text"] == "Bon"
    assert "Một người" not in qs[0]["question_text"]
    for q in qs[1:4]:
        assert q["question_text"].startswith("Một người đến khám. Dữ kiện ở dòng tiếp theo.\n\n")
        assert [o["text"] for o in q["options"]] == ["Mot", "Hai", "Ba", "Bon"]
    assert qs[4]["question_text"] == "Ngoài nhóm?"


def test_wrapped_unlabelled_line_is_not_automatically_a_new_option():
    qs = parse_questions_from_text("""Câu 1: Nội dung câu hỏi dài
tiếp tục trên dòng thứ hai?
A. Phương án A dài
tiếp tục trên dòng mới
B. Phương án B
C. Phương án C
D. Phương án D
""")
    assert len(qs[0]["options"]) == 4
    assert qs[0]["question_text"].endswith("tiếp tục trên dòng thứ hai?")
    assert qs[0]["options"][0]["text"] == "Phương án A dài tiếp tục trên dòng mới"


def test_missing_label_repair_does_not_steal_a_later_explicit_option():
    text = """Câu 1: Chọn nội dung?
A. Nội dung một
B. Vitamin C có trong thực phẩm
C. Nội dung ba
D. Nội dung bốn
"""
    q = parse_questions_from_text(text)[0]
    assert q["options"][1]["text"] == "Vitamin C có trong thực phẩm"
    assert q["options"][2]["text"] == "Nội dung ba"


def test_does_not_create_missing_c_from_a_medical_term():
    q = parse_questions_from_text("""Câu 1: Chọn nội dung?
A. Nội dung một
B. Vitamin C có trong thực phẩm
D. Nội dung bốn
""")[0]
    assert [o["key"] for o in q["options"]] == ["A", "B", "D"]


def test_preserves_medical_group_letter_at_the_end_of_an_option():
    q = parse_questions_from_text("""Câu 3: Xét nghiệm nào cần chỉ định?
A. cấy dịch ngoáy họng xác định liên cầu A.
B. cấy dịch khớp xác định liên cầu A. C. xét nghiệm ASLO bằng ELISA.
D. xét nghiệm ASLO bằng phản ứng ngưng kết.
""")[0]
    assert [o["key"] for o in q["options"]] == ["A", "B", "C", "D"]
    assert q["options"][0]["text"].endswith("liên cầu A.")
    assert q["options"][1]["text"].endswith("liên cầu A.")


def test_splits_option_labels_merged_by_ocr_without_punctuation():
    text = """Câu 3: Xét nghiệm cần chỉ định?
A. Cấy dịch ngoáy họng xác định liên cầu
B. Cấy dịch khớp xác định liên cầu C xét nghiệm máu xác định ASLO bằng ELISA.
D. Xét nghiệm máu xác định ASLO bằng phản ứng ngưng kết.
Câu 4: Vi khuẩn nào là tác nhân gây bệnh?
A Mycobacterium tuberculosis B Corynebacterium diphtheriae
C Streptococcus pyogenes
D Bordetella pertussis
"""

    questions = parse_questions_from_text(text)

    assert len(questions) == 2
    assert [option["key"] for option in questions[0]["options"]] == ["A", "B", "C", "D"]
    assert questions[0]["options"][1]["text"] == "Cấy dịch khớp xác định liên cầu"
    assert questions[0]["options"][2]["text"] == "xét nghiệm máu xác định ASLO bằng ELISA."
    assert [option["key"] for option in questions[1]["options"]] == ["A", "B", "C", "D"]
    assert questions[1]["options"][0]["text"] == "Mycobacterium tuberculosis"
    assert questions[1]["options"][1]["text"] == "Corynebacterium diphtheriae"


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
