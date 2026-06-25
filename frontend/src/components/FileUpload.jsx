import { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, File, X, AlertCircle, Loader2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { uploadDocument } from "../services/api";

const FileUpload = () => {
  const [file, setFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [numQuestions, setNumQuestions] = useState(10);
  const [difficulty, setDifficulty] = useState("mixed");
  const [language, setLanguage] = useState("vi");
  const [mode, setMode] = useState("generate");
  const navigate = useNavigate();

  const onDrop = useCallback((acceptedFiles, rejectedFiles) => {
    if (rejectedFiles.length > 0) {
      toast.error("File không hợp lệ. Vui lòng chọn PDF, DOCX hoặc TXT dưới 10MB.");
      return;
    }
    if (acceptedFiles.length > 0) {
      setFile(acceptedFiles[0]);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
      "text/plain": [".txt"],
    },
    maxSize: 10 * 1024 * 1024, // 10MB
    multiple: false,
  });

  const handleUpload = async () => {
    if (!file) return;
    
    setIsUploading(true);
    toast.info(
      mode === "extract" 
        ? "Đang trích xuất và lọc câu hỏi trùng..." 
        : "Đang xử lý tài liệu và tạo câu hỏi... Quá trình này có thể mất vài phút."
    );
    
    try {
      const result = await uploadDocument(file, {
        num_questions: numQuestions,
        difficulty: difficulty,
        language: language,
        mode: mode,
      });
      
      toast.success("Tạo quiz thành công!");
      // Chuyển hướng tới trang làm quiz
      navigate(`/quiz/${result.quiz.id}`);
      
    } catch (error) {
      let errorMsg = "Không thể tạo quiz. Vui lòng thử lại.";
      if (error.response?.data?.detail) {
        if (Array.isArray(error.response.data.detail)) {
          // Lỗi validate từ FastAPI (422) trả về mảng các lỗi
          errorMsg = error.response.data.detail.map(err => err.msg).join(', ');
        } else {
          // Lỗi HTTP thông thường trả về chuỗi
          errorMsg = String(error.response.data.detail);
        }
      } else if (error.message) {
        errorMsg = error.message;
      }
      toast.error(errorMsg);
    } finally {
      setIsUploading(false);
    }
  };

  const clearFile = (e) => {
    e.stopPropagation();
    setFile(null);
  };

  return (
    <div className="file-upload-container card">
      {/* Chế độ hoạt động */}
      <div className="mode-selector" style={{ marginBottom: "var(--spacing-md)", display: "flex", gap: "var(--spacing-md)" }}>
        <button 
          className={`btn ${mode === "generate" ? "btn-primary" : "btn-secondary"}`}
          onClick={() => setMode("generate")}
          disabled={isUploading}
          style={{ flex: 1, padding: "var(--spacing-sm)" }}
        >
          Sinh câu hỏi mới
        </button>
        <button 
          className={`btn ${mode === "extract" ? "btn-primary" : "btn-secondary"}`}
          onClick={() => setMode("extract")}
          disabled={isUploading}
          style={{ flex: 1, padding: "var(--spacing-sm)" }}
        >
          Trích xuất & Lọc trùng
        </button>
      </div>

      {/* Cấu hình Quiz */}
      <div className="quiz-config">
        <div className="form-group" style={{ opacity: mode === "extract" ? 0.5 : 1, pointerEvents: mode === "extract" ? "none" : "auto" }}>
          <label>Số câu hỏi</label>
          <input 
            type="number" 
            min="5" 
            max="30" 
            value={numQuestions} 
            onChange={(e) => setNumQuestions(e.target.value)}
            disabled={isUploading || mode === "extract"}
          />
        </div>
        <div className="form-group" style={{ opacity: mode === "extract" ? 0.5 : 1, pointerEvents: mode === "extract" ? "none" : "auto" }}>
          <label>Độ khó</label>
          <select 
            value={difficulty} 
            onChange={(e) => setDifficulty(e.target.value)}
            disabled={isUploading || mode === "extract"}
          >
            <option value="easy">Dễ</option>
            <option value="medium">Trung bình</option>
            <option value="hard">Khó</option>
            <option value="mixed">Hỗn hợp</option>
          </select>
        </div>
        <div className="form-group">
          <label>Ngôn ngữ</label>
          <select 
            value={language} 
            onChange={(e) => setLanguage(e.target.value)}
            disabled={isUploading}
          >
            <option value="vi">Tiếng Việt</option>
            <option value="en">English</option>
          </select>
        </div>
      </div>

      {/* Khu vực Dropzone */}
      <div 
        {...getRootProps()} 
        className={`dropzone ${isDragActive ? "active" : ""} ${file ? "has-file" : ""} ${isUploading ? "disabled" : ""}`}
      >
        <input {...getInputProps()} disabled={isUploading} />
        
        {file ? (
          <div className="file-preview">
            <File size={40} className="file-icon" />
            <div className="file-info">
              <p className="file-name">{file.name}</p>
              <p className="file-size">{(file.size / (1024 * 1024)).toFixed(2)} MB</p>
            </div>
            {!isUploading && (
              <button className="clear-btn" onClick={clearFile} type="button">
                <X size={20} />
              </button>
            )}
          </div>
        ) : (
          <div className="dropzone-content">
            <Upload size={40} className="upload-icon" />
            <p className="dropzone-text">
              {isDragActive ? "Thả file vào đây..." : "Kéo thả file vào đây hoặc click để chọn"}
            </p>
            <span className="dropzone-hint">PDF, DOCX, TXT — Tối đa 10MB</span>
          </div>
        )}
      </div>

      {/* Nút Upload */}
      <button 
        className="btn btn-primary upload-btn" 
        onClick={handleUpload} 
        disabled={!file || isUploading}
      >
        {isUploading ? (
          <>
            <Loader2 size={20} className="spinner" />
            Đang xử lý...
          </>
        ) : (
          "Tạo Quiz Ngay"
        )}
      </button>
    </div>
  );
};

export default FileUpload;
