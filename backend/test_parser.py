import asyncio
import sys
import os

sys.path.insert(0, r"e:\personal project\AIQuiz\backend")

from app.utils.question_parser import parse_questions_from_text

sample_text = """
Chương 1: Mở đầu
Câu 1: Câu hỏi 1
A. 1
B. 2
C. 3
D. 4
Đáp án: A

Chương 2: Phần hai
Câu 2: Câu hỏi 2
A. 1
B. 2
C. 3
D. 4
Đáp án: B

Bài 3: Phần ba
Câu 3: Câu hỏi 3
A. 1
B. 2
C. 3
D. 4
Đáp án: C
"""

def test():
    questions = parse_questions_from_text(sample_text)
    with open("test_output_final.txt", "w", encoding="utf-8") as f:
        f.write(f"Total parsed: {len(questions)}\n")
        for q in questions:
            f.write(f"Q: {q['question_text']}, Chapter: {q.get('chapter', 'NONE')}\n")

if __name__ == "__main__":
    test()
