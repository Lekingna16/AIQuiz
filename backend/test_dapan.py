from app.utils.question_parser import parse_questions_from_text

text = """
Câu 3: Trước Chiến tranh thế giới thứ nhất, ở Việt Nam có những giai cấp nào?
a) Địa chủ phong kiến và nông dân
đáp án b) Địa chủ phong kiến, nông dân, tư sản, tiểu tư sản và công nhân
c) Địa chủ phong kiến, nông dân và công nhân
d) Địa chủ phong kiến, nông dân và tiểu tư sản

Câu 4: Dưới chế độ thực dân phong kiến, giai cấp nông dân Việt Nam có yêu cầu bức thiết nhất
đáp án a) Độc lập dân tộc
b) Ruộng đất
c) Quyền bình đẳng nam, nữ
d) Được giảm tô, giảm tức
"""

res = parse_questions_from_text(text)
for r in res:
    print(r["question_text"])
    print(r["options"])
    print("Correct answer:", r["correct_answer"])
    print("---")
