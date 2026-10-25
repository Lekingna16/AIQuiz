import { useState, useCallback, useEffect } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, File, X, Loader2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { getQuizFilters, uploadDocument, waitForUploadJob } from "../services/api";

const normalizeForSearch = (value) => value
  .normalize("NFD")
  .replace(/[\u0300-\u036f]/g, "")
  .toLocaleLowerCase("vi-VN")
  .replace(/đ/g, "d")
  .replace(/\bdh\b/g, "dai hoc")
  .replace(/[^a-z0-9]+/g, " ")
  .trim();

const SearchableSelect = ({
  id,
  label,
  placeholder,
  options,
  value,
  onSelect,
  disabled,
  allowCustom = false,
  customOptionLabel = "mục mới",
}) => {
  const [query, setQuery] = useState(value);
  const [isOpen, setIsOpen] = useState(false);
  const trimmedQuery = query.trim();
  const queryTokens = normalizeForSearch(query).split(" ").filter(Boolean);
  const suggestions = queryTokens.length > 0
    ? options.filter((option) => {
        const normalizedOption = normalizeForSearch(option);
        return queryTokens.every((token) => normalizedOption.includes(token));
      }).slice(0, 8)
    : options.slice(0, 8);
  const isKnownOption = options.some((option) => option === trimmedQuery);

  useEffect(() => {
    setQuery(value);
  }, [value]);

  const selectOption = (option) => {
    setQuery(option);
    onSelect(option);
    setIsOpen(false);
  };

  return (
    <div className="form-group autocomplete-field">
      <label htmlFor={id}>{label}</label>
      <div className="autocomplete-control">
        <input
          id={id}
          type="search"
          value={query}
          placeholder={placeholder}
          autoComplete="off"
          aria-autocomplete="list"
          aria-expanded={isOpen}
          aria-invalid={Boolean(query && !value)}
          disabled={disabled}
          onFocus={() => setIsOpen(true)}
          onBlur={() => window.setTimeout(() => setIsOpen(false), 150)}
          onChange={(event) => {
            const nextValue = event.target.value;
            setQuery(nextValue);
            onSelect(allowCustom ? nextValue.trim() : "");
            setIsOpen(true);
          }}
        />
        {isOpen && !disabled && (
          <ul className="autocomplete-menu" role="listbox">
            {suggestions.length > 0 ? suggestions.map((option) => (
              <li key={option} role="option" aria-selected={option === value}>
                <button type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => selectOption(option)}>
                  {option}
                </button>
              </li>
            )) : <li className="autocomplete-empty">Không tìm thấy kết quả</li>}
            {allowCustom && trimmedQuery && !isKnownOption && (
              <li role="option" aria-selected={value === trimmedQuery}>
                <button type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => selectOption(trimmedQuery)}>
                  Dùng “{trimmedQuery}” ({customOptionLabel})
                </button>
              </li>
            )}
          </ul>
        )}
      </div>
    </div>
  );
};

const FileUpload = ({ forcedMode }) => {
  const [file, setFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [numQuestions, setNumQuestions] = useState(10);
  const [difficulty, setDifficulty] = useState("mixed");
  const [language, setLanguage] = useState("vi");
  const [mode, setMode] = useState(forcedMode || "generate");
  const [isPublic, setIsPublic] = useState(false);
  const [major, setMajor] = useState("");
  const [subject, setSubject] = useState("");
  const [examType, setExamType] = useState("");
  const DEFAULT_EXAM_TYPES = ["Ôn tập", "Giữa kỳ", "Cuối kỳ"];
  const [metadataOptions, setMetadataOptions] = useState({
    majors: [],
    courses_by_major: {},
    exam_types: DEFAULT_EXAM_TYPES,
  });
  const [isLoadingMetadata, setIsLoadingMetadata] = useState(true);
  
  const navigate = useNavigate();

  useEffect(() => {
    let isMounted = true;

    const loadMetadataOptions = async () => {
      try {
        const options = await getQuizFilters({ includeCatalog: true });
        if (isMounted) {
          setMetadataOptions({
            majors: options.majors || [],
            courses_by_major: options.courses_by_major || {},
            exam_types: options.exam_types?.length ? options.exam_types : DEFAULT_EXAM_TYPES,
          });
        }
      } catch (error) {
        console.error("Unable to load upload metadata options", error);
      } finally {
        if (isMounted) setIsLoadingMetadata(false);
      }
    };

    loadMetadataOptions();
    return () => { isMounted = false; };
  }, []);

  const onDrop = useCallback((acceptedFiles, rejectedFiles) => {
    if (rejectedFiles.length > 0) {
      toast.error("File không hợp lệ. Vui lòng chọn PDF, DOCX hoặc TXT dưới 50MB.");
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
    maxSize: 50 * 1024 * 1024, // 50MB
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
      const job = await uploadDocument(
        file, 
        {
          num_questions: numQuestions,
          difficulty: difficulty,
          language: language,
          mode: mode,
          is_public: isPublic,
          major: major,
          subject: subject,
          exam_type: examType,
        },
        // Upload progress callback
        (percent) => {
          setUploadProgress(percent);
          if (percent >= 100) {
            setUploadPhase("processing");
            toast.info(
              mode === "extract" 
                ? "Đã tải file lên. Đang trích xuất và lọc câu hỏi trùng..." 
                : "Đã tải file lên. Đang chuẩn bị bài quiz, quá trình này có thể mất vài phút.",
              { duration: 10000 }
            );
          }
        }
      );
      
      setUploadPhase("processing");
      const result = await waitForUploadJob(job.job_id, (status) => {
        if (status === "queued") setUploadPhase("processing");
      });

      toast.success("Tạo quiz thành công!");
      // Chuyển hướng tới trang làm quiz
      navigate(`/quiz/${result.quiz_id}`);
      
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
              errorMsg = "File quá lớn. Vui lòng chọn file nhỏ hơn 50MB.";
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
      <div className="quiz-config upload-metadata" aria-label="Upload metadata">
        <SearchableSelect
          id="upload-major"
          label="Ngành học"
          placeholder="Chọn hoặc nhập ngành học mới"
          options={metadataOptions.majors}
          value={major}
          onSelect={(nextMajor) => {
            setMajor(nextMajor);
            setSubject("");
          }}
          allowCustom
          customOptionLabel="ngành học mới"
          disabled={isUploading || isLoadingMetadata}
        />
        <div className="form-group">
          <label htmlFor="upload-exam-type">Kỳ thi</label>
          <select
            id="upload-exam-type"
            value={examType}
            onChange={(e) => setExamType(e.target.value)}
            disabled={isUploading || isLoadingMetadata}
          >
            <option value="" disabled>Chọn kỳ thi</option>
            {metadataOptions.exam_types.map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>
        </div>
        <SearchableSelect
          id="upload-subject"
          label="Học phần"
          placeholder={major ? "Chọn hoặc nhập học phần mới" : "Chọn ngành học trước"}
          options={major ? (metadataOptions.courses_by_major[major] || []) : []}
          value={subject}
          onSelect={setSubject}
          allowCustom
          customOptionLabel="học phần mới"
          disabled={isUploading || isLoadingMetadata || !major}
        />
      </div>

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
            <span className="dropzone-hint">PDF, DOCX, TXT — Tối đa 50MB</span>
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
                : "⏳ Đang chuẩn bị bài quiz..."}
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
        disabled={!file || isUploading || isLoadingMetadata || !major || !subject || !examType}
      >
        {isUploading ? (
          <>
            <Loader2 size={20} className="spinner" />
            {uploadPhase === "uploading" 
              ? `Đang tải lên... ${uploadProgress}%` 
              : "Đang tạo bài quiz..."}
          </>
        ) : (
          "Tạo Quiz Ngay"
        )}
      </button>
    </div>
  );
};

export default FileUpload;
