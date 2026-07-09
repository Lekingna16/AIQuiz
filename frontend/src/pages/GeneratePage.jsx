import React from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Lock, Wand2 } from "lucide-react";
import FileUpload from "../components/FileUpload";
import useAuthStore from "../store/authStore";

function GeneratePage() {
  const { isAuthenticated } = useAuthStore();

  return (
    <div className="upload-page" style={{ maxWidth: "800px", margin: "0 auto", padding: "2rem" }}>
      <Link to="/" className="back-link" style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem", marginBottom: "2rem", textDecoration: "none", color: "var(--text-secondary)" }}>
        <ArrowLeft size={20} /> Về trang chủ
      </Link>

      <div className="header-section" style={{ textAlign: "center", marginBottom: "3rem" }}>
        <div style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: "64px", height: "64px", background: "var(--primary-color-light, rgba(79, 70, 229, 0.1))", color: "var(--primary-color, #4f46e5)", borderRadius: "50%", marginBottom: "1rem" }}>
          <Wand2 size={32} />
        </div>
        <h1 style={{ fontSize: "2rem", marginBottom: "0.5rem", color: "var(--text-color)" }}>Sinh câu hỏi bằng AI</h1>
        <p style={{ color: "var(--text-secondary)", fontSize: "1.1rem", maxWidth: "600px", margin: "0 auto" }}>
          Sử dụng trí tuệ nhân tạo để tự động tạo ra bài tập trắc nghiệm từ bất kỳ tài liệu nào của bạn.
        </p>
      </div>

      <div className="upload-container">
        {isAuthenticated ? (
          <FileUpload forcedMode="generate" />
        ) : (
          <div className="auth-required-card" style={{ textAlign: "center", padding: "4rem 2rem", background: "var(--card-bg, #ffffff)", borderRadius: "12px", border: "1px solid var(--border-color)", boxShadow: "0 4px 6px rgba(0,0,0,0.05)" }}>
            <Lock size={48} style={{ color: "var(--text-secondary)", marginBottom: "1.5rem" }} />
            <h2 style={{ marginBottom: "1rem", color: "var(--text-color)" }}>Yêu cầu đăng nhập</h2>
            <p style={{ color: "var(--text-secondary)", fontSize: "1.1rem", maxWidth: "400px", margin: "0 auto 2rem auto" }}>
              Bạn cần đăng nhập để sử dụng tính năng sinh câu hỏi bằng AI.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

export default GeneratePage;
