import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { Brain, Search, Filter, Play, UploadCloud } from "lucide-react";
import { getQuizzes } from "../services/api";

function HomePage() {
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
      <section className="hero" style={{ padding: "4rem 2rem", textAlign: "center", background: "var(--card-bg)" }}>
        <div className="hero-content" style={{ maxWidth: "800px", margin: "0 auto" }}>
          <h1 style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "1rem", fontSize: "3rem", marginBottom: "1rem" }}>
            <Brain className="hero-icon" size={56} style={{ color: "var(--primary-color)" }} />
            AIQuiz
          </h1>
          <p className="hero-subtitle" style={{ fontSize: "1.2rem", color: "var(--text-secondary)", marginBottom: "2rem" }}>
            Nền tảng học tập và chia sẻ tài nguyên trắc nghiệm thông minh.
          </p>
          <div style={{ display: "flex", justifyContent: "center", gap: "1rem" }}>
            <Link to="/upload" className="btn btn-primary" style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.8rem 1.5rem", fontSize: "1.1rem" }}>
              <UploadCloud size={20} /> Tạo & Đóng góp tài liệu
            </Link>
          </div>
        </div>
      </section>

      <div className="home-container" style={{ padding: "3rem 2rem", maxWidth: "1200px", margin: "0 auto" }}>
        <div className="public-quizzes">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "2rem", flexWrap: "wrap", gap: "1rem" }}>
            <h2 style={{ margin: 0, fontSize: "1.8rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
              Tài nguyên cộng đồng
            </h2>
          </div>
          
          <div className="filters card" style={{ display: "flex", gap: "1rem", marginBottom: "2rem", flexWrap: "wrap", padding: "1.5rem", alignItems: "center" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontWeight: "bold", color: "var(--text-secondary)" }}>
              <Filter size={20} /> Lọc:
            </div>
            <input 
              type="text" 
              placeholder="Môn học (Toán, Lý...)" 
              value={subject} 
              onChange={e => setSubject(e.target.value)}
              className="form-input"
              style={{ flex: 1, minWidth: "150px" }}
            />
            <input 
              type="text" 
              placeholder="Chương / Bài" 
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
              placeholder="Trường học" 
              value={school} 
              onChange={e => setSchool(e.target.value)}
              className="form-input"
              style={{ flex: 1, minWidth: "150px" }}
            />
          </div>

          {loading ? (
            <div style={{ textAlign: "center", padding: "3rem", color: "var(--text-secondary)" }}>
              <p>Đang tải tài nguyên...</p>
            </div>
          ) : quizzes.length > 0 ? (
            <div className="quiz-grid" style={{ display: "grid", gap: "1.5rem", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))" }}>
              {quizzes.map(quiz => (
                <div key={quiz.id} className="quiz-card card" style={{ padding: "1.5rem", display: "flex", flexDirection: "column", height: "100%" }}>
                  <h3 style={{ marginTop: 0, marginBottom: "0.5rem", fontSize: "1.2rem", lineHeight: "1.4" }}>
                    {quiz.title}
                  </h3>
                  
                  <div style={{ margin: "1rem 0", flex: 1, display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                    {quiz.subject && <span className="badge" style={{ alignSelf: "flex-start", background: "var(--primary-color-light)", color: "var(--primary-color)", padding: "0.2rem 0.6rem", borderRadius: "4px", fontSize: "0.85rem" }}>{quiz.subject}</span>}
                    
                    <div style={{ fontSize: "0.95rem", color: "var(--text-secondary)", display: "flex", flexDirection: "column", gap: "0.3rem" }}>
                      {quiz.chapter && <div>• Chương: <strong>{quiz.chapter}</strong></div>}
                      {quiz.exam_type && <div>• Kỳ thi: <strong>{quiz.exam_type}</strong></div>}
                      {quiz.school && <div>• Trường: <strong>{quiz.school}</strong></div>}
                    </div>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "1rem", paddingTop: "1rem", borderTop: "1px solid var(--border-color)" }}>
                    <div style={{ fontSize: "0.9rem", color: "var(--text-secondary)" }}>
                      <strong>{quiz.total_questions}</strong> câu hỏi
                    </div>
                    <Link to={`/quiz/${quiz.id}`} className="btn btn-primary" style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem", padding: "0.5rem 1rem" }}>
                      <Play size={16} /> Bắt đầu làm
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="card" style={{ textAlign: "center", padding: "4rem 2rem" }}>
              <Search size={48} style={{ color: "var(--text-secondary)", marginBottom: "1rem" }} />
              <h3>Không tìm thấy kết quả</h3>
              <p style={{ color: "var(--text-secondary)" }}>Thử thay đổi bộ lọc hoặc tìm kiếm với từ khóa khác.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default HomePage;
