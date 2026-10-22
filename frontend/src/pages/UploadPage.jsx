import React from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, UploadCloud } from "lucide-react";
import FileUpload from "../components/FileUpload";

function UploadPage() {
  return (
    <div className="upload-page" style={{ maxWidth: "800px", margin: "0 auto", padding: "2rem" }}>
      <Link to="/" className="back-link" style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem", marginBottom: "2rem", textDecoration: "none", color: "var(--text-secondary)" }}>
        <ArrowLeft size={20} /> Về trang chủ
      </Link>

      <div className="header-section" style={{ textAlign: "center", marginBottom: "3rem" }}>
        <div style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: "64px", height: "64px", background: "var(--primary-color-light, rgba(79, 70, 229, 0.1))", color: "var(--primary-color, #4f46e5)", borderRadius: "50%", marginBottom: "1rem" }}>
          <UploadCloud size={32} />
        </div>
        <h1 style={{ fontSize: "2rem", marginBottom: "0.5rem", color: "var(--text-color)" }}>Upload tài liệu của bạn</h1>
        <p style={{ color: "var(--text-secondary)", fontSize: "1.1rem", maxWidth: "600px", margin: "0 auto" }}>
          Tải lên tài liệu của bạn để trích xuất và lưu trữ câu hỏi trắc nghiệm.
        </p>
      </div>

      <div className="upload-container">
        <FileUpload forcedMode="extract" />
      </div>
    </div>
  );
}

export default UploadPage;
