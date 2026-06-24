/**
 * HomePage - Trang chính với chức năng upload file
 * 
 * Đây là landing page đầu tiên user thấy.
 * Phase 1: chỉ hiển thị layout cơ bản.
 * Phase 4: sẽ thêm FileUpload component với drag & drop.
 */

import { Link } from "react-router-dom";
import { Upload, Brain, CheckCircle, FileText } from "lucide-react";

function HomePage() {
  return (
    <div className="home-page">
      {/* Hero Section */}
      <section className="hero">
        <div className="hero-content">
          <h1>
            <Brain className="hero-icon" size={48} />
            AIQuiz
          </h1>
          <p className="hero-subtitle">
            Upload tài liệu — AI tự động sinh câu hỏi trắc nghiệm
          </p>
          <p className="hero-description">
            Hỗ trợ PDF, Word, TXT. Powered by Google Gemini AI.
          </p>

          {/* Upload Area - Placeholder cho Phase 4 */}
          <div className="upload-area">
            <Upload size={40} />
            <p>Kéo thả file vào đây hoặc click để chọn</p>
            <span className="upload-hint">PDF, DOCX, TXT — Tối đa 10MB</span>
          </div>

          <Link to="/history" className="btn btn-secondary">
            Xem lịch sử quiz
          </Link>
        </div>
      </section>

      {/* Features Section */}
      <section className="features">
        <div className="feature-card">
          <FileText size={32} />
          <h3>Đa dạng định dạng</h3>
          <p>Hỗ trợ PDF, Word (.docx), và Text (.txt)</p>
        </div>
        <div className="feature-card">
          <Brain size={32} />
          <h3>AI thông minh</h3>
          <p>Gemini AI tạo câu hỏi chất lượng cao, đáp án nhiễu logic</p>
        </div>
        <div className="feature-card">
          <CheckCircle size={32} />
          <h3>Chấm điểm tự động</h3>
          <p>Làm bài trực tiếp, xem kết quả và giải thích chi tiết</p>
        </div>
      </section>
    </div>
  );
}

export default HomePage;
