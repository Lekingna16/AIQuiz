from app.utils.question_parser import parse_questions_from_text
import json

text = """Câu 34. Nội dung nào...
A. Nắm vững nghệ thuật khởi nghĩa.
B. Toàn dân nổi dậy.
C. Lợi dụng mâu thuẫn.
D. Giương cao ngọn cờ độc lập dân tộc, kết hợp và giải quyết đúng đắn hai
nhiệm vụ chống đế quốc và chống phong kiến."""

res = parse_questions_from_text(text)
print(json.dumps(res, indent=2, ensure_ascii=False))
