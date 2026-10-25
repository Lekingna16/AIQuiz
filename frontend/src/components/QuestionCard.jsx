import React from 'react';

const QuestionCard = ({ question, currentAnswer, answerResult, isChecking, onSelectAnswer }) => {
  const isRevealed = Boolean(answerResult);

  return (
    <div className="question-card">
      <h3 className="question-text">
        <span className="question-number">Câu {question.order}:</span> {question.question_text}
      </h3>
      <div className="options-list">
        {question.options.map((opt) => {
          const isSelected = currentAnswer === opt.key;
          const isCorrect = isRevealed && answerResult.correct_answer === opt.key;
          const isIncorrect = isRevealed && isSelected && !answerResult.is_correct;

          return (
            <button
              key={opt.key}
              className={`option-btn ${isSelected ? "selected" : ""} ${isCorrect ? "correct" : ""} ${isIncorrect ? "incorrect" : ""}`}
              onClick={() => onSelectAnswer(question.id, opt.key)}
              disabled={Boolean(currentAnswer) || isChecking}
            >
              <span className="option-key">{opt.key}</span>
              <span className="option-text">{opt.text}</span>
            </button>
          );
        })}
      </div>
      {isChecking && <p className="answer-feedback checking">Đang kiểm tra đáp án...</p>}
      {answerResult && (
        <div className={`answer-feedback ${answerResult.is_correct ? "correct" : "incorrect"}`} role="status">
          <strong>{answerResult.is_correct ? "Chính xác!" : "Chưa chính xác."}</strong>
          <span> Đáp án đúng: <b>{answerResult.correct_answer}</b></span>
          {answerResult.explanation && <p><b>Giải thích:</b> {answerResult.explanation}</p>}
        </div>
      )}
    </div>
  );
};

export default QuestionCard;
