import React from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle, XCircle } from 'lucide-react';

const ResultsSummary = ({ results, score, total, percentage, quizId }) => {
  return (
    <div className="results-summary card">
      <div className="score-header">
        <h2>Kết quả bài làm</h2>
        <div className="score-circle">
          <span className="score-number">{score}/{total}</span>
          <span className="score-percentage">{percentage}%</span>
        </div>
      </div>

      <div className="detailed-results">
        <h3>Chi tiết từng câu</h3>
        {results.map((res, index) => (
          <div key={res.question_id} className={`result-item ${res.is_correct ? 'correct' : 'incorrect'}`}>
            <div className="result-header">
              <span className="q-num">Câu {index + 1}</span>
              {res.is_correct ? <CheckCircle className="icon-correct" size={20} /> : <XCircle className="icon-incorrect" size={20} />}
            </div>
            <div className="result-answers">
              <p>Bạn chọn: <strong>{res.selected}</strong></p>
              {!res.is_correct && <p>Đáp án đúng: <strong>{res.correct_answer}</strong></p>}
            </div>
            {res.explanation && (
              <div className="explanation">
                <strong>Giải thích:</strong> {res.explanation}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="results-actions">
        <Link to="/" className="btn btn-primary">Tạo Quiz mới</Link>
        <Link to="/history" className="btn btn-secondary">Xem lịch sử</Link>
      </div>
    </div>
  );
};

export default ResultsSummary;
