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
const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Tạo axios instance với config chung
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 600000, // 600 giây (10 phút) để xử lý file lớn
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
      // Server trả về error (4xx, 5xx)
      const message = error.response.data?.detail || "Đã có lỗi xảy ra";
      console.error(`API Error [${error.response.status}]:`, message);
    } else if (error.request) {
      // Request gửi đi nhưng không nhận được response (network error)
      console.error("Network Error: Không thể kết nối tới server");
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
 * @param {Object} options - { num_questions, difficulty, language }
 * @returns {Promise} Quiz data
 */
export const uploadDocument = async (file, options = {}) => {
  // Dùng FormData vì gửi file (multipart/form-data)
  const formData = new FormData();
  formData.append("file", file);

  // Build query params từ options
  const params = new URLSearchParams();
  if (options.num_questions) params.append("num_questions", options.num_questions);
  if (options.difficulty) params.append("difficulty", options.difficulty);
  if (options.language) params.append("language", options.language);
  if (options.mode) params.append("mode", options.mode);

  const response = await api.post(
    `/api/documents/upload?${params.toString()}`,
    formData,
    {
      headers: { "Content-Type": "multipart/form-data" },
    }
  );
  return response.data;
};

/**
 * Lấy danh sách quiz
 */
export const getQuizzes = async (page = 1, limit = 10) => {
  const response = await api.get("/api/quizzes", {
    params: { page, limit },
  });
  return response.data;
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

/**
 * Authenticate với Google
 * @param {string} credential - JWT token từ Google
 */
export const loginWithGoogle = async (credential) => {
  const response = await api.post('/api/auth/google', { credential });
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
