import React from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Lock, UploadCloud } from "lucide-react";
import FileUpload from "../components/FileUpload";
import useAuthStore from "../store/authStore";

function UploadPage() {
  const { isAuthenticated } = useAuthStore();

  return (
    <div className="upload-page" style={{ maxWidth: "800px", margin: "0 auto", padding: "2rem" }}>
      <Link to="/" className="back-link" style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem", marginBottom: "2rem", textDecoration: "none", color: "var(--text-secondary)" }}>
        <ArrowLeft size={20} /> Về trang chủ
      </Link>

      <div className="header-section" style={{ textAlign: "center", marginBottom: "3rem" }}>
        <div style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: "64px", height: "64px", background: "var(--primary-color-light, rgba(79, 70, 229, 0.1))", color: "var(--primary-color, #4f46e5)", borderRadius: "50%", marginBottom: "1rem" }}>
          <UploadCloud size={32} />
        </div>
        <h1 style={{ fontSize: "2rem", marginBottom: "0.5rem", color: "var(--text-color)" }}>Đóng góp tài liệu</h1>
        <p style={{ color: "var(--text-secondary)", fontSize: "1.1rem", maxWidth: "600px", margin: "0 auto" }}>
          Tải lên tài liệu của bạn để AI tự động trích xuất hoặc tạo mới bài trắc nghiệm. Các tài liệu chia sẻ cộng đồng sẽ cần chờ admin phê duyệt.
        </p>
      </div>

      <div className="upload-container">
        {isAuthenticated ? (
          <FileUpload />
        ) : (
          <div className="auth-required-card" style={{ textAlign: "center", padding: "4rem 2rem", background: "var(--card-bg, #ffffff)", borderRadius: "12px", border: "1px solid var(--border-color)", boxShadow: "0 4px 6px rgba(0,0,0,0.05)" }}>
            <Lock size={48} style={{ color: "var(--text-secondary)", marginBottom: "1.5rem" }} />
            <h2 style={{ marginBottom: "1rem", color: "var(--text-color)" }}>Yêu cầu đăng nhập</h2>
            <p style={{ color: "var(--text-secondary)", fontSize: "1.1rem", maxWidth: "400px", margin: "0 auto 2rem auto" }}>
              Bạn cần đăng nhập để có thể tải lên và đóng góp tài liệu cho cộng đồng học tập.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

export default UploadPage;
