import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { Brain, Search, Filter, Lock, Play } from "lucide-react";
import FileUpload from "../components/FileUpload";
import { getQuizzes } from "../services/api";
import useAuthStore from "../store/authStore";

function HomePage() {
  const { isAuthenticated } = useAuthStore();
  const [quizzes, setQuizzes] = useState([]);
  const [loading, setLoading] = useState(true);
  
  // Filters
  const [subject, setSubject] = useState("");
  const [chapter, setChapter] = useState("");
  const [examType, setExamType] = useState("");
  const [school, setSchool] = useState("");

  const fetchQuizzes = async () => {
    setLoading(true);
    try {
      const filters = {};
      if (subject) filters.subject = subject;
      if (chapter) filters.chapter = chapter;
      if (examType) filters.exam_type = examType;
      if (school) filters.school = school;
      
      const data = await getQuizzes(1, 20, filters);
      setQuizzes(data.quizzes || []);
    } catch (error) {
      console.error("Failed to fetch quizzes", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchQuizzes();
  }, [subject, chapter, examType, school]);

  return (
    <div className="home-page">
      <section className="hero">
        <div className="hero-content">
          <h1>
            <Brain className="hero-icon" size={48} />
            AIQuiz
          </h1>
          <p className="hero-subtitle">
            Học tập và chia sẻ tài nguyên trắc nghiệm
          </p>
        </div>
      </section>

      <div className="home-container" style={{ display: "flex", gap: "2rem", padding: "2rem", maxWidth: "1200px", margin: "0 auto", flexWrap: "wrap" }}>
        
        {/* Cột trái: Danh sách quiz công khai */}
        <div className="public-quizzes" style={{ flex: "1 1 60%", minWidth: "300px" }}>
          <h2>Tài nguyên cộng đồng</h2>
          
          <div className="filters" style={{ display: "flex", gap: "1rem", marginBottom: "1.5rem", flexWrap: "wrap" }}>
            <input 
              type="text" 
              placeholder="Môn học..." 
              value={subject} 
              onChange={e => setSubject(e.target.value)}
              className="form-input"
              style={{ flex: 1, minWidth: "150px" }}
            />
            <input 
              type="text" 
              placeholder="Chương..." 
              value={chapter} 
              onChange={e => setChapter(e.target.value)}
              className="form-input"
              style={{ flex: 1, minWidth: "150px" }}
            />
            <select 
              value={examType} 
              onChange={e => setExamType(e.target.value)}
              className="form-input"
              style={{ flex: 1, minWidth: "150px" }}
            >
              <option value="">Tất cả kỳ thi</option>
              <option value="Giữa kì">Giữa kì</option>
              <option value="Cuối kì">Cuối kì</option>
            </select>
            <input 
              type="text" 
              placeholder="Trường..." 
              value={school} 
              onChange={e => setSchool(e.target.value)}
              className="form-input"
              style={{ flex: 1, minWidth: "150px" }}
            />
          </div>

          {loading ? (
            <p>Đang tải tài nguyên...</p>
          ) : quizzes.length > 0 ? (
            <div className="quiz-grid" style={{ display: "grid", gap: "1rem", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))" }}>
              {quizzes.map(quiz => (
                <div key={quiz.id} className="quiz-card" style={{ padding: "1.5rem", border: "1px solid var(--border-color)", borderRadius: "8px", background: "var(--card-bg)" }}>
                  <h3 style={{ marginTop: 0 }}>{quiz.title}</h3>
                  <div style={{ fontSize: "0.9rem", color: "var(--text-secondary)", marginBottom: "1rem", lineHeight: "1.6" }}>
                    {quiz.subject && <div><strong>Môn:</strong> {quiz.subject}</div>}
                    {quiz.chapter && <div><strong>Chương:</strong> {quiz.chapter}</div>}
                    {quiz.exam_type && <div><strong>Kỳ thi:</strong> {quiz.exam_type}</div>}
                    {quiz.school && <div><strong>Trường:</strong> {quiz.school}</div>}
                    <div><strong>Số câu:</strong> {quiz.total_questions}</div>
                  </div>
                  <Link to={`/quiz/${quiz.id}`} className="btn btn-primary" style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem", width: "100%", justifyContent: "center" }}>
                    <Play size={16} /> Bắt đầu làm
                  </Link>
                </div>
              ))}
            </div>
          ) : (
            <p>Không tìm thấy bài trắc nghiệm nào phù hợp.</p>
          )}
        </div>

        {/* Cột phải: Upload file */}
        <div className="upload-section" style={{ flex: "1 1 35%", minWidth: "300px" }}>
          <div style={{ padding: "1.5rem", border: "1px solid var(--border-color)", borderRadius: "8px", background: "var(--card-bg)", position: "sticky", top: "2rem" }}>
            <h2 style={{ marginTop: 0 }}>Đóng góp tài liệu</h2>
            <p style={{ fontSize: "0.9rem", color: "var(--text-secondary)", marginBottom: "1.5rem" }}>
              Tải lên tài liệu của bạn để AI tự động trích xuất hoặc tạo mới bài trắc nghiệm. 
              Các tài liệu chia sẻ cộng đồng sẽ cần chờ admin phê duyệt.
            </p>

            {isAuthenticated ? (
              <FileUpload />
            ) : (
              <div style={{ textAlign: "center", padding: "2rem 1rem", background: "var(--bg-color)", borderRadius: "8px" }}>
                <Lock size={48} style={{ color: "var(--text-secondary)", marginBottom: "1rem" }} />
                <h3>Yêu cầu đăng nhập</h3>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem", marginBottom: "1rem" }}>
                  Bạn cần đăng nhập để có thể tải lên và đóng góp tài liệu cho cộng đồng.
                </p>
              </div>
            )}
          </div>
        </div>

      </div>
    </div>
  );
}

export default HomePage;
