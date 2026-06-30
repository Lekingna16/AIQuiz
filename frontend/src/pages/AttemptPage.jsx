import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { getAttemptDetails } from "../services/api";
import useAuthStore from "../store/authStore";
import ResultsSummary from "../components/ResultsSummary";

function AttemptPage() {
  const { attemptId } = useParams();
  const [attempt, setAttempt] = useState(null);
  const [loading, setLoading] = useState(true);
  const { isAuthenticated } = useAuthStore();

  useEffect(() => {
    const fetchAttempt = async () => {
      if (!isAuthenticated) {
        setLoading(false);
        return;
      }
      try {
        const data = await getAttemptDetails(attemptId);
        setAttempt(data);
      } catch (error) {
        toast.error("Không thể tải kết quả bài làm.");
      } finally {
        setLoading(false);
      }
    };
    fetchAttempt();
  }, [attemptId]);

  if (!isAuthenticated) {
    return (
      <div className="quiz-page">
        <Link to="/" className="back-link"><ArrowLeft size={20} /> Về trang chủ</Link>
        <div className="quiz-placeholder">Vui lòng đăng nhập để xem chi tiết bài làm.</div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="quiz-page loading-container">
        <Loader2 size={48} className="spinner" />
        <p>Đang tải kết quả...</p>
      </div>
    );
  }

  if (!attempt) {
    return (
      <div className="quiz-page">
        <Link to="/history" className="back-link"><ArrowLeft size={20} /> Về lịch sử</Link>
        <div className="quiz-placeholder">Không tìm thấy bài làm.</div>
      </div>
    );
  }

  return (
    <div className="quiz-page">
      <Link to="/history" className="back-link"><ArrowLeft size={20} /> Về lịch sử</Link>
      <ResultsSummary 
        results={attempt.results} 
        score={attempt.score} 
        total={attempt.total} 
        percentage={attempt.percentage} 
        quizId={attempt.quiz_id}
        questions={attempt.questions || []}
      />
    </div>
  );
}

export default AttemptPage;
