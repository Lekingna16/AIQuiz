"""Persistent reading instructions and examples shared by both vision providers.

These are inference-time examples, not model training or a medical answer key.
"""

LAYOUT_READING_RULES = """
READING PROCEDURE
1. Identify question numbers and the spatial area belonging to each question.
   Finish the entire question stem, including wrapped lines, before its options.
2. Treat a new line with an option label as a NEW option, even if the dot is
   missing or the label is circled. A new question number starts a NEW question.
   An unlabelled line indented underneath text in the SAME column can be a
   continuation. Do not make each wrapped line a separate option.
3. Options may form a 2-column x 2-row grid. Read each labelled cell and its
   continuation lines separately. Never concatenate the left and right cells.
   Use the PRINTED labels, not their apparent reading order: both A B / C D and
   A C / B D layouts exist. Output A, B, C, D, keeping their original contents.
4. Do not append the next question's stem or options to the previous question.
   A heading such as 'Phần câu hỏi 7-9:' starts a shared passage for questions
   7 through 9. Transcribe that heading and passage as a separate paragraph
   BEFORE question 7, never inside option C or D of question 6.
5. Typography and location determine boundaries. Medical knowledge must not
   replace unreadable source text or move a plausible answer to another question.
6. Repeated bottom-of-page metadata such as 'M8, Đề A, NH 24-25, YLT23,
   trang 2' is a FOOTER. Omit it. Never append it to option D or to a question.

EXAMPLES (layout demonstrations only; never copy them into the source output)
Printed single column:
  A. Nội dung một
  B Nội dung hai
  C. Nội dung ba
  D Nội dung bốn
Output: four separate labelled lines, A through D.

Printed 2x2 grid with wrapped text:
  A. Nội dung dài bên trái       B. Nội dung bên phải
     tiếp tục của A                tiếp tục của B
  C. Nội dung thứ ba             D. Nội dung thứ tư
Output:
  A. Nội dung dài bên trái tiếp tục của A
  B. Nội dung bên phải tiếp tục của B
  C. Nội dung thứ ba
  D. Nội dung thứ tư

Printed alternative grid:
  A. Nội dung một                C. Nội dung ba
  B. Nội dung hai                D. Nội dung bốn
Output: A. Nội dung một / B. Nội dung hai / C. Nội dung ba / D. Nội dung bốn,
with ONE option per line, not literal slash separators.

Boundary example:
  Câu 6: Câu hỏi trước?
  A. Một  B. Hai
  C. Ba   D. Bốn
  Phần câu hỏi 7-9: Đoạn mô tả chung.
  Dòng tiếp theo của đoạn mô tả chung.
  Câu 7: Câu hỏi tiếp?
Keep the shared passage OUTSIDE question 6's options. Keep all its lines.
"""
