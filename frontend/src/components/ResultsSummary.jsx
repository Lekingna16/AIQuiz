import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle, XCircle, HelpCircle, ChevronDown, ChevronUp } from 'lucide-react';

const ResultsSummary = ({ results, score, total, percentage, quizId, questions = [] }) => {
  const [showAll, setShowAll] = useState(false);
  
  // Build question map for showing question text
  const questionMap = {};
  questions.forEach((q, idx) => {
    questionMap[q.id] = { ...q, index: idx };
  });

  // Count stats
  const correctCount = results.filter(r => r.is_correct).length;
  const incorrectCount = results.filter(r => !r.is_correct && r.selected && r.correct_answer).length;
  const skippedCount = results.filter(r => !r.selected && r.correct_answer).length;
  const unknownCount = results.filter(r => !r.is_correct && !r.correct_answer).length;
  
  // Show first 20 by default, toggle to show all
  const displayResults = showAll ? results : results.slice(0, 20);
  
  // Score circle animation
  const circumference = 2 * Math.PI * 54;
  const strokeDashoffset = circumference - (percentage / 100) * circumference;
  
  // Determine grade color
  const getGradeColor = () => {
    if (percentage >= 80) return 'var(--color-success)';
    if (percentage >= 60) return 'var(--color-primary)';
    if (percentage >= 40) return '#f59e0b';
    return 'var(--color-error)';
  };

  return (
    <div className="results-summary card">
      <div className="score-header">
        <h2>Kết quả bài làm</h2>
        <div className="score-circle">
          <svg viewBox="0 0 120 120" className="score-svg">
            <circle cx="60" cy="60" r="54" className="score-bg-circle" />
            <circle
              cx="60" cy="60" r="54"
              className="score-progress-circle"
              style={{
                strokeDasharray: circumference,
                strokeDashoffset: strokeDashoffset,
                stroke: getGradeColor(),
              }}
            />
          </svg>
          <div className="score-text">
            <span className="score-number">{score}/{total}</span>
            <span className="score-percentage" style={{ color: getGradeColor() }}>
              {percentage}%
            </span>
          </div>
        </div>
        
        {/* Stats bar */}
        <div className="score-stats">
          {correctCount > 0 && (
            <div className="stat-item correct">
              <CheckCircle size={16} />
              <span>{correctCount} đúng</span>
            </div>
          )}
          {incorrectCount > 0 && (
            <div className="stat-item incorrect">
              <XCircle size={16} />
              <span>{incorrectCount} sai</span>
            </div>
          )}
          {skippedCount > 0 && (
            <div className="stat-item" style={{ color: '#888' }}>
              <HelpCircle size={16} />
              <span>{skippedCount} bỏ qua</span>
            </div>
          )}
          {unknownCount > 0 && (
            <div className="stat-item unknown">
              <HelpCircle size={16} />
              <span>{unknownCount} chưa có đáp án</span>
            </div>
          )}
        </div>
      </div>

      <div className="detailed-results">
        <h3>Chi tiết từng câu</h3>
        {displayResults.map((res, index) => {
          const qInfo = questionMap[res.question_id];
          const hasAnswer = !!res.correct_answer;
          const statusClass = !hasAnswer ? 'unknown' : res.is_correct ? 'correct' : 'incorrect';
          
          // Find option text for selected and correct
          const getOptionText = (key) => {
            if (!qInfo || !key) return '';
            const opt = qInfo.options?.find(o => o.key === key);
            return opt ? opt.text : '';
          };
          
          return (
            <div key={res.question_id} className={`result-item ${statusClass}`}>
              <div className="result-header">
                <span className="q-num">Câu {index + 1}</span>
                {!hasAnswer ? (
                  <HelpCircle className="icon-unknown" size={20} />
                ) : res.is_correct ? (
                  <CheckCircle className="icon-correct" size={20} />
                ) : (
                  <XCircle className="icon-incorrect" size={20} />
                )}
              </div>
              
              {/* Question text */}
              {qInfo && (
                <p className="result-question-text">{qInfo.question_text}</p>
              )}
              
              <div className="result-answers">
                <p>
                  Bạn chọn: <strong>{res.selected || "Chưa chọn"}</strong>
                  {res.selected && getOptionText(res.selected) && (
                    <span className="option-text"> - {getOptionText(res.selected)}</span>
                  )}
                </p>
                {hasAnswer && !res.is_correct && (
                  <p className="correct-answer-line">
                    Đáp án đúng: <strong>{res.correct_answer}</strong>
                    {getOptionText(res.correct_answer) && (
                      <span className="option-text"> - {getOptionText(res.correct_answer)}</span>
                    )}
                  </p>
                )}
                {!hasAnswer && (
                  <p className="no-answer-note">
                    ⚠ Câu này chưa có đáp án trong hệ thống
                  </p>
                )}
              </div>
              {res.explanation && (
                <div className="explanation">
                  <strong>Giải thích:</strong> {res.explanation}
                </div>
              )}
            </div>
          );
        })}
        
        {/* Show more/less toggle */}
        {results.length > 20 && (
          <button 
            className="btn btn-secondary show-more-btn"
            onClick={() => setShowAll(!showAll)}
          >
            {showAll ? (
              <><ChevronUp size={18} /> Thu gọn</>
            ) : (
              <><ChevronDown size={18} /> Xem tất cả {results.length} câu</>
            )}
          </button>
        )}
      </div>

      <div className="results-actions">
        <Link to="/" className="btn btn-primary">Tạo Quiz mới</Link>
        <Link to="/history" className="btn btn-secondary">Xem lịch sử</Link>
      </div>
    </div>
  );
};

export default ResultsSummary;
