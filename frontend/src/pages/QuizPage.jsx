/**
 * QuizPage - Trang làm bài trắc nghiệm
 * 
 * Layout 2 cột:
 * - Sidebar trái: bảng chọn câu hỏi (grid số)
 * - Content phải: câu hỏi + navigation
 */

import { useState, useEffect, useRef } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, Loader2, Check, ChevronLeft, ChevronRight, LayoutGrid } from "lucide-react";
import { toast } from "sonner";
import { getQuiz, submitQuiz } from "../services/api";
import QuestionCard from "../components/QuestionCard";
import ResultsSummary from "../components/ResultsSummary";
import Comments from "../components/Comments";

function QuizPage() {
  const { quizId } = useParams();
  const [quiz, setQuiz] = useState(null);
  const [loading, setLoading] = useState(true);
  const [answers, setAnswers] = useState({});
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [resultsData, setResultsData] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const questionRef = useRef(null);

  useEffect(() => {
    const fetchQuiz = async () => {
      try {
        const data = await getQuiz(quizId);
        setQuiz(data);
      } catch (error) {
        toast.error("Không thể tải bài quiz. Vui lòng thử lại.");
      } finally {
        setLoading(false);
      }
    };
    fetchQuiz();
  }, [quizId]);

  const handleSelectAnswer = (questionId, selectedKey) => {
    setAnswers(prev => ({
      ...prev,
      [questionId]: selectedKey
    }));
  };

  const goToQuestion = (idx) => {
    setCurrentQuestionIndex(idx);
    questionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const handleNext = () => {
    if (currentQuestionIndex < quiz.questions.length - 1) {
      goToQuestion(currentQuestionIndex + 1);
    }
  };

  const handlePrev = () => {
    if (currentQuestionIndex > 0) {
      goToQuestion(currentQuestionIndex - 1);
    }
  };

  const handleSubmit = async () => {
    if (Object.keys(answers).length < quiz.questions.length) {
      const unanswered = quiz.questions.length - Object.keys(answers).length;
      const confirmSubmit = window.confirm(
        `Bạn còn ${unanswered} câu chưa trả lời. Bạn có chắc chắn muốn nộp bài?`
      );
      if (!confirmSubmit) return;
    }

    setIsSubmitting(true);
    try {
      const formattedAnswers = Object.entries(answers).map(([qId, sel]) => ({
        question_id: qId,
        selected: sel
      }));
      
      const res = await submitQuiz(quizId, formattedAnswers);
      setResultsData(res);
      toast.success("Nộp bài thành công!");
    } catch (error) {
      toast.error("Không thể nộp bài. Vui lòng thử lại.");
    } finally {
      setIsSubmitting(false);
    }
  };

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (!quiz || resultsData) return;
      if (e.key === "ArrowRight" || e.key === "ArrowDown") {
        e.preventDefault();
        handleNext();
      } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
        e.preventDefault();
        handlePrev();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [quiz, currentQuestionIndex, resultsData]);

  if (loading) {
    return (
      <div className="quiz-page loading-container">
        <Loader2 size={48} className="spinner" />
        <p>Đang tải bài tập...</p>
      </div>
    );
  }

  if (!quiz) {
    return (
      <div className="quiz-page">
        <Link to="/" className="back-link"><ArrowLeft size={20} /> Về trang chủ</Link>
        <div className="quiz-placeholder">Không tìm thấy bài quiz.</div>
      </div>
    );
  }

  if (resultsData) {
    return (
      <div className="quiz-page">
        <Link to="/" className="back-link"><ArrowLeft size={20} /> Về trang chủ</Link>
        <ResultsSummary 
          results={resultsData.results} 
          score={resultsData.score} 
          total={resultsData.total} 
          percentage={resultsData.percentage} 
          quizId={quizId}
          questions={quiz?.questions || []}
        />
      </div>
    );
  }

  const currentQuestion = quiz.questions[currentQuestionIndex];
  const totalQuestions = quiz.questions.length;
  const answeredCount = Object.keys(answers).length;
  const progress = ((currentQuestionIndex + 1) / totalQuestions) * 100;

  return (
    <div className="quiz-layout">
      <Link to="/" className="back-link"><ArrowLeft size={20} /> Về trang chủ</Link>

      <div className="quiz-layout-grid">
        {/* ===== SIDEBAR: Bảng chọn câu ===== */}
        <aside className={`quiz-sidebar ${sidebarOpen ? "open" : "collapsed"}`}>
          <div className="sidebar-header">
            <h3>Danh sách câu hỏi</h3>
            <button 
              className="sidebar-toggle"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              title={sidebarOpen ? "Thu gọn" : "Mở rộng"}
            >
              <LayoutGrid size={18} />
            </button>
          </div>

          <div className="sidebar-stats">
            <span className="stat-answered">{answeredCount}/{totalQuestions} đã trả lời</span>
          </div>

          <div className="question-grid">
            {quiz.questions.map((q, idx) => {
              const isActive = idx === currentQuestionIndex;
              const isAnswered = !!answers[q.id];
              return (
                <button
                  key={q.id}
                  className={`q-grid-btn ${isActive ? "active" : ""} ${isAnswered ? "answered" : ""}`}
                  onClick={() => goToQuestion(idx)}
                  title={`Câu ${idx + 1}${isAnswered ? " ✓" : ""}`}
                >
                  {idx + 1}
                </button>
              );
            })}
          </div>

          <button 
            className="btn btn-primary sidebar-submit"
            onClick={handleSubmit} 
            disabled={isSubmitting}
          >
            {isSubmitting ? <Loader2 size={18} className="spinner" /> : <Check size={18} />}
            Nộp bài ({answeredCount}/{totalQuestions})
          </button>
        </aside>

        {/* Toggle button khi sidebar đóng (mobile) */}
        {!sidebarOpen && (
          <button 
            className="sidebar-float-toggle"
            onClick={() => setSidebarOpen(true)}
          >
            <LayoutGrid size={20} />
            <span className="float-badge">{answeredCount}/{totalQuestions}</span>
          </button>
        )}

        {/* ===== MAIN CONTENT ===== */}
        <main className="quiz-main" ref={questionRef}>
          {/* Header */}
          <div className="quiz-header card">
            <div className="quiz-title-section">
              <h2>{quiz.title}</h2>
              {quiz.description && <p className="quiz-desc">{quiz.description}</p>}
            </div>
            <div className="quiz-progress-bar-wrapper">
              <div className="progress-bar">
                <div className="progress-fill" style={{ width: `${progress}%` }}></div>
              </div>
            </div>
          </div>

          {/* Question Card */}
          <div className="quiz-player card">
            <QuestionCard 
              question={currentQuestion} 
              currentAnswer={answers[currentQuestion.id]} 
              onSelectAnswer={handleSelectAnswer} 
            />

            <Comments questionId={currentQuestion.id} />

            {/* Navigation: Prev | 3-dot indicator | Next */}
            <div className="quiz-navigation">
              <button 
                className="btn btn-secondary nav-btn" 
                onClick={handlePrev} 
                disabled={currentQuestionIndex === 0}
              >
                <ChevronLeft size={20} />
                Trước
              </button>
              
              <div className="nav-indicator">
                <span className={`nav-dot ${currentQuestionIndex > 0 ? "visible" : ""}`}></span>
                <span className="nav-dot current">{currentQuestionIndex + 1}</span>
                <span className={`nav-dot ${currentQuestionIndex < totalQuestions - 1 ? "visible" : ""}`}></span>
              </div>

              {currentQuestionIndex === totalQuestions - 1 ? (
                <button 
                  className="btn btn-primary nav-btn" 
                  onClick={handleSubmit} 
                  disabled={isSubmitting}
                >
                  {isSubmitting ? <Loader2 size={18} className="spinner" /> : <><Check size={18} /> Nộp bài</>}
                </button>
              ) : (
                <button 
                  className="btn btn-primary nav-btn" 
                  onClick={handleNext}
                >
                  Tiếp
                  <ChevronRight size={20} />
                </button>
              )}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

export default QuizPage;
