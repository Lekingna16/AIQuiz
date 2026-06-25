import React from 'react';

const QuestionCard = ({ question, currentAnswer, onSelectAnswer }) => {
  return (
    <div className="question-card">
      <h3 className="question-text">
        <span className="question-number">Câu {question.order}:</span> {question.question_text}
      </h3>
      <div className="options-list">
        {question.options.map((opt) => (
          <button
            key={opt.key}
            className={`option-btn ${currentAnswer === opt.key ? "selected" : ""}`}
            onClick={() => onSelectAnswer(question.id, opt.key)}
          >
            <span className="option-key">{opt.key}</span>
            <span className="option-text">{opt.text}</span>
          </button>
        ))}
      </div>
    </div>
  );
};

export default QuestionCard;
