/**
 * QuizPage - Trang làm bài trắc nghiệm
 * 
 * Phase 1: Placeholder page
 * Phase 4: Full quiz player với navigation, timer, submit
 */

import { useParams, Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

function QuizPage() {
  const { quizId } = useParams();

  return (
    <div className="quiz-page">
      <Link to="/" className="back-link">
        <ArrowLeft size={20} />
        Về trang chủ
      </Link>

      <div className="quiz-placeholder">
        <h2>📝 Quiz Player</h2>
        <p>Quiz ID: {quizId}</p>
        <p className="placeholder-text">
          Giao diện làm bài sẽ được xây dựng ở Phase 4.
        </p>
      </div>
    </div>
  );
}

export default QuizPage;
