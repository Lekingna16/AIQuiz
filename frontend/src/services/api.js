/**
 * API Service - Centralized HTTP client
 * =======================================
 * 
 * Tại sao dùng Axios thay vì fetch()?
 * 1. Tự động parse JSON response
 * 2. Interceptors: thêm token, handle lỗi ở 1 chỗ
 * 3. Better error handling (axios phân biệt network error vs HTTP error)
 * 4. Request/response transformation tự động
 * 5. Cancel request dễ dàng
 * 
 * Pattern: tạo 1 instance với baseURL, tất cả components dùng chung.
 * Không import axios trực tiếp trong components → dễ thay đổi config.
 */

import axios from "axios";

// Base URL của backend API
// Vite dùng import.meta.env thay vì process.env (Create React App)
const API_BASE_URL = import.meta.env.VITE_API_URL || "https://aiquiz-hla0.onrender.com";

// Tạo axios instance với config chung
const api = axios.create({
  baseURL: API_BASE_URL,
  // Normal API calls should fail quickly instead of leaving the UI blocked.
  // Uploads return a job id quickly, then the UI polls its status.
  timeout: 15000,
  headers: {
    "Content-Type": "application/json",
  },
});

/**
 * Request Interceptor - Gắn Token vào Header
 * Trước khi gửi bất kỳ request nào, tự động lấy token từ Zustand
 * và gắn vào header Authorization.
 */
api.interceptors.request.use(
  (config) => {
    // Không thể import trực tiếp hook useAuthStore ở đây vì sẽ gây React hook error ngoài component
    // Đọc trực tiếp từ localStorage
    const authData = localStorage.getItem('auth-storage');
    if (authData) {
      try {
        const { state } = JSON.parse(authData);
        if (state.token) {
          config.headers.Authorization = `Bearer ${state.token}`;
        }
      } catch (e) {
        // Parse error, ignore
      }
    }
    return config;
  },
  (error) => Promise.reject(error)
);

/**
 * Response Interceptor - xử lý lỗi tập trung.
 * 
 * Thay vì try/catch trong mỗi component, interceptor bắt lỗi ở 1 chỗ.
 * Components chỉ cần handle business logic, không lo HTTP errors.
 */
api.interceptors.response.use(
  (response) => response, // Request thành công → trả nguyên
  (error) => {
    // Phân loại lỗi để hiển thị message phù hợp
    if (error.response) {
      // Nếu lỗi 401 hoặc 403 (Hết hạn token, user bị xóa, hoặc thiếu token), force logout
      // NHƯNG bỏ qua nếu đang gọi endpoint đăng nhập (auth) — vì 401 ở login là lỗi xác thực, không phải hết hạn token
      const requestUrl = error.config?.url || '';
      const isAuthRequest = requestUrl.includes('/api/auth/');
      if ((error.response.status === 401 || error.response.status === 403) && !isAuthRequest) {
        localStorage.removeItem('auth-storage');
        window.location.href = '/';
      }
      // Server trả về error (4xx, 5xx)
      const message = error.response.data?.detail || "Đã có lỗi xảy ra";
      console.error(`API Error [${error.response.status}]:`, message);
    } else if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
      // Timeout error
      console.error("Timeout Error: Request đã hết thời gian chờ");
      error.friendlyMessage = "Yêu cầu đã hết thời gian chờ. Tài liệu có thể quá lớn hoặc server đang quá tải. Vui lòng thử lại.";
    } else if (error.code === 'ERR_CANCELED') {
      // Request bị hủy (AbortController)
      console.error("Request cancelled");
      error.friendlyMessage = "Yêu cầu đã bị hủy.";
    } else if (error.code === 'ERR_NETWORK' || error.message === 'Network Error') {
      // Network error - không thể kết nối tới server
      console.error("Network Error: Không thể kết nối tới server");
      error.friendlyMessage = "Không thể kết nối tới server. Vui lòng kiểm tra kết nối mạng và thử lại.";
    } else if (error.request) {
      // Request gửi đi nhưng không nhận được response
      console.error("No Response Error: Server không phản hồi");
      error.friendlyMessage = "Server không phản hồi. Vui lòng thử lại sau.";
    }
    return Promise.reject(error);
  }
);

// ============================================
// API Functions - Mỗi function tương ứng 1 endpoint
// ============================================

/**
 * Upload file và sinh quiz
 * @param {File} file - File PDF/DOCX/TXT
 * @param {Object} options - { num_questions, difficulty, language, major, subject, exam_type, school }
 * @returns {Promise<{job_id: string, status: string}>} queued upload job
 */
export const uploadDocument = async (file, options = {}, onProgress = null) => {
  // Dùng FormData vì gửi file (multipart/form-data)
  const formData = new FormData();
  formData.append("file", file);

  // Build query params từ options
  const params = new URLSearchParams();
  if (options.num_questions) params.append("num_questions", options.num_questions);
  if (options.difficulty) params.append("difficulty", options.difficulty);
  if (options.language) params.append("language", options.language);
  if (options.mode) params.append("mode", options.mode);
  if (options.is_public !== undefined) params.append("is_public", options.is_public);
  if (options.subject) params.append("subject", options.subject);
  if (options.major) params.append("major", options.major);
  if (options.exam_type) params.append("exam_type", options.exam_type);
  if (options.school) params.append("school", options.school);

  const response = await api.post(
    `/api/documents/upload?${params.toString()}`,
    formData,
    {
      headers: { "Content-Type": "multipart/form-data" },
      // This request only transfers the file and queues work; it should not
      // stay open while OCR or AI generation runs.
      timeout: 60000,
      // Theo dõi tiến trình upload file
      onUploadProgress: onProgress
        ? (progressEvent) => {
            const percentCompleted = Math.round(
              (progressEvent.loaded * 100) / (progressEvent.total || progressEvent.loaded)
            );
            onProgress(percentCompleted);
          }
        : undefined,
    }
  );
  return response.data;
};

export const getUploadJob = async (jobId) => {
  const response = await api.get(`/api/documents/jobs/${jobId}`);
  return response.data;
};

export const waitForUploadJob = async (jobId, onStatus) => {
  const deadline = Date.now() + (15 * 60 * 1000);

  while (Date.now() < deadline) {
    const job = await getUploadJob(jobId);
    onStatus?.(job.status);

    if (job.status === "completed") return job;
    if (job.status === "failed") {
      const error = new Error(job.error || "Không thể xử lý tài liệu.");
      error.friendlyMessage = job.error;
      throw error;
    }

    await new Promise((resolve) => window.setTimeout(resolve, 2000));
  }

  const error = new Error("Tài liệu vẫn đang được xử lý.");
  error.friendlyMessage = "Tài liệu đang được xử lý lâu hơn dự kiến. Vui lòng mở lại Lịch sử sau ít phút.";
  throw error;
};

/**
 * Lấy các tuỳ chọn bộ lọc (dropdown)
 */
export const getQuizFilters = async ({ includeCatalog = false } = {}) => {
  const response = await api.get("/api/quizzes/filters", {
    params: includeCatalog ? { include_catalog: true } : undefined,
  });
  return response.data;
};

/**
 * Lấy danh sách quiz
 */
export const getQuizzes = async (page = 1, limit = 10, filters = {}) => {
  const response = await api.get("/api/quizzes", {
    params: { page, limit, ...filters },
  });
  return response.data;
};

/**
 * Lấy danh sách quiz của người dùng
 */
export const getMyQuizzes = async (page = 1, limit = 10) => {
  const response = await api.get("/api/quizzes/me", {
    params: { page, limit },
  });
  return response.data;
};

/** Lấy các tài liệu mà người dùng đã upload. */
export const getMyDocuments = async () => {
  const response = await api.get("/api/documents/me");
  return response.data;
};

/** Xóa một file upload cùng các quiz/câu hỏi sinh từ file đó. */
export const deleteDocument = async (documentId) => {
  await api.delete(`/api/documents/${documentId}`);
};

/**
 * Lấy chi tiết quiz để làm bài
 */
export const getQuiz = async (quizId) => {
  const response = await api.get(`/api/quizzes/${quizId}`);
  return response.data;
};

/**
 * Nộp bài làm
 */
export const submitQuiz = async (quizId, answers) => {
  const response = await api.post(`/api/quizzes/${quizId}/submit`, {
    answers,
  });
  return response.data;
};

/** Chấm ngay một đáp án khi người dùng chọn. */
export const checkQuizAnswer = async (quizId, questionId, selected) => {
  const response = await api.post(`/api/quizzes/${quizId}/questions/${questionId}/check`, {
    selected,
  });
  return response.data;
};

/**
 * Lấy lịch sử làm bài của user
 */
export const getMyAttempts = async (page = 1, limit = 10) => {
  const response = await api.get('/api/quizzes/attempts/me', {
    params: { page, limit },
  });
  return response.data;
};

/**
 * Lấy chi tiết một bài đã làm
 */
export const getAttemptDetails = async (attemptId) => {
  const response = await api.get(`/api/quizzes/attempts/${attemptId}`);
  return response.data;
};

/**
 * Authenticate với Google
 * @param {string} credential - JWT token từ Google
 */
export const loginWithGoogle = async (credential) => {
  const response = await api.post('/api/auth/google', { credential });
  return response.data;
};

/**
 * Mock login for development
 */
export const loginMock = async () => {
  const response = await api.post('/api/auth/mock');
  return response.data;
};

/**
 * Lấy thông tin user hiện tại
 */
export const getMe = async () => {
  const response = await api.get('/api/auth/me');
  return response.data;
};

export default api;
