from app.utils.question_parser import parse_questions_from_text
import json

text = """Câu 34. Question 34 text.
A. Option A
B. Option B
C. Option C
D. Option D

Chương 2: Hệ thống chính trị
Câu 1: Đại hội VI của Đảng (12/1986) rút ra bốn bài học kinh nghiệm quý báu. A Đảng phải luôn luôn xuất phát từ thực tế, tôn trọng và hành động theo quy luật khách quan.
B. Trong toàn bộ hoạt động cách mạng của mình.
C. Phải biết kết hợp sức mạnh của dân tộc.
D. Phải xây dựng Đảng ngang tầm với một đảng cầm quyền.
"""

res = parse_questions_from_text(text)
print(json.dumps(res, indent=2, ensure_ascii=False))
