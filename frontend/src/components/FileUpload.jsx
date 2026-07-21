import { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, File, X, Loader2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { uploadDocument } from "../services/api";

const FileUpload = ({ forcedMode }) => {
  const [file, setFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [numQuestions, setNumQuestions] = useState(10);
  const [difficulty, setDifficulty] = useState("mixed");
  const [language, setLanguage] = useState("vi");
  const [mode, setMode] = useState(forcedMode || "generate");
  const [isPublic, setIsPublic] = useState(false);
  
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

  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadPhase, setUploadPhase] = useState(""); // "uploading" | "processing" | ""

  const handleUpload = async () => {
    if (!file) return;
    
    setIsUploading(true);
    setUploadProgress(0);
    setUploadPhase("uploading");
    
    try {
      const result = await uploadDocument(
        file, 
        {
          num_questions: numQuestions,
          difficulty: difficulty,
          language: language,
          mode: mode,
          is_public: isPublic,
        },
        // Upload progress callback
        (percent) => {
          setUploadProgress(percent);
          if (percent >= 100) {
            setUploadPhase("processing");
            toast.info(
              mode === "extract" 
                ? "Đã tải file lên. Đang trích xuất và lọc câu hỏi trùng..." 
                : "Đã tải file lên. Đang xử lý bằng AI... Quá trình này có thể mất vài phút.",
              { duration: 10000 }
            );
          }
        }
      );
      
      toast.success("Tạo quiz thành công!");
      // Chuyển hướng tới trang làm quiz
      navigate(`/quiz/${result.quiz.id}`);
      
    } catch (error) {
      let errorMsg = "Không thể tạo quiz. Vui lòng thử lại.";

      if (error.friendlyMessage) {
        // Lỗi đã được interceptor xử lý với message thân thiện
        errorMsg = error.friendlyMessage;
      } else if (error.response) {
        // Server trả về lỗi HTTP (có response)
        const status = error.response.status;
        const detail = error.response.data?.detail;

        if (detail) {
          if (Array.isArray(detail)) {
            // Lỗi validate từ FastAPI (422) trả về mảng các lỗi
            errorMsg = detail.map(err => err.msg).join(', ');
          } else {
            // Lỗi HTTP thông thường trả về chuỗi
            errorMsg = String(detail);
          }
        } else {
          // Fallback theo status code
          switch (status) {
            case 400:
              errorMsg = "File không hợp lệ. Vui lòng kiểm tra định dạng và thử lại.";
              break;
            case 413:
              errorMsg = "File quá lớn. Vui lòng chọn file nhỏ hơn 10MB.";
              break;
            case 422:
              errorMsg = "Không thể trích xuất nội dung từ file. Vui lòng thử file khác.";
              break;
            case 500:
              errorMsg = "Lỗi server. Vui lòng thử lại sau ít phút.";
              break;
            case 502:
            case 503:
            case 504:
              errorMsg = "Server đang quá tải hoặc bảo trì. Vui lòng thử lại sau.";
              break;
            default:
              errorMsg = `Lỗi từ server (mã ${status}). Vui lòng thử lại.`;
          }
        }
      } else if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
        errorMsg = "Yêu cầu đã hết thời gian chờ. Tài liệu có thể quá lớn hoặc server đang quá tải. Vui lòng thử lại.";
      } else if (error.code === 'ERR_NETWORK' || error.message === 'Network Error') {
        errorMsg = "Không thể kết nối tới server. Vui lòng kiểm tra kết nối mạng và thử lại.";
      } else if (error.code === 'ERR_CANCELED') {
        errorMsg = "Yêu cầu đã bị hủy.";
      } else if (error.message) {
        // Lỗi khác không xác định
        errorMsg = `Đã xảy ra lỗi: ${error.message}`;
      }

      toast.error(errorMsg, { duration: 8000 });
    } finally {
      setIsUploading(false);
      setUploadProgress(0);
      setUploadPhase("");
    }
  };

  const clearFile = (e) => {
    e.stopPropagation();
    setFile(null);
  };

  return (
    <div className="file-upload-container card">
      {/* Chế độ hoạt động */}
      {!forcedMode && (
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
      )}

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

      {/* Thanh tiến trình upload */}
      {isUploading && (
        <div className="upload-progress" style={{ marginTop: "var(--spacing-sm)" }}>
          <div style={{ 
            display: "flex", 
            justifyContent: "space-between", 
            marginBottom: "var(--spacing-xs)",
            fontSize: "0.85rem",
            color: "var(--text-secondary)"
          }}>
            <span>
              {uploadPhase === "uploading" 
                ? `Đang tải file lên... ${uploadProgress}%` 
                : "⏳ AI đang xử lý tài liệu..."}
            </span>
            {uploadPhase === "processing" && (
              <span style={{ color: "var(--primary-color)" }}>Có thể mất vài phút</span>
            )}
          </div>
          <div style={{
            width: "100%",
            height: "6px",
            backgroundColor: "var(--border-color, #e2e8f0)",
            borderRadius: "3px",
            overflow: "hidden",
          }}>
            <div style={{
              width: uploadPhase === "processing" ? "100%" : `${uploadProgress}%`,
              height: "100%",
              backgroundColor: "var(--primary-color, #4f46e5)",
              borderRadius: "3px",
              transition: "width 0.3s ease",
              animation: uploadPhase === "processing" ? "pulse-progress 1.5s ease-in-out infinite" : "none",
            }} />
          </div>
        </div>
      )}

      {/* Nút Upload */}
      <button 
        className="btn btn-primary upload-btn" 
        onClick={handleUpload} 
        disabled={!file || isUploading}
      >
        {isUploading ? (
          <>
            <Loader2 size={20} className="spinner" />
            {uploadPhase === "uploading" 
              ? `Đang tải lên... ${uploadProgress}%` 
              : "AI đang xử lý..."}
          </>
        ) : (
          "Tạo Quiz Ngay"
        )}
      </button>
    </div>
  );
};

export default FileUpload;
