/**
 * HistoryPage - Lịch sử các quiz đã tạo
 * 
 * Phase 1: Placeholder
 * Phase 4: Danh sách quiz với pagination, click vào để làm lại
 */

import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Clock, Loader2, Play, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { getMyAttempts, getMyDocuments, deleteDocument } from "../services/api";
import useAuthStore from "../store/authStore";

function HistoryPage() {
  const [quizzes, setQuizzes] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const { isAuthenticated } = useAuthStore();

  const fetchHistory = useCallback(async (pageToFetch) => {
    if (!isAuthenticated) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const [attemptData, documentData] = await Promise.all([
        getMyAttempts(pageToFetch, 10),
        getMyDocuments(),
      ]);
      setQuizzes(attemptData.attempts);
      setDocuments(documentData.documents);
      setTotalPages(attemptData.pages);
      setPage(attemptData.page);
    } catch {
      toast.error("Không thể tải lịch sử. Vui lòng thử lại.");
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated]);

  useEffect(() => {
    fetchHistory(1);
  }, [fetchHistory]);

  const handleDelete = async (id) => {
    if (!window.confirm("Bạn có chắc muốn xóa file upload này và toàn bộ quiz tạo từ file?")) return;
    
    try {
      await deleteDocument(id);
      toast.success("Đã xóa file upload và dữ liệu liên quan.");
      fetchHistory(page);
    } catch {
      toast.error("Không thể xóa file upload.");
    }
  };

  return (
    <div className="history-page">
      <Link to="/" className="back-link">
        <ArrowLeft size={20} /> Về trang chủ
      </Link>

      <h2><Clock size={28} /> Lịch sử Quiz</h2>

      {!isAuthenticated ? (
        <div className="placeholder-text card">
          <p>Vui lòng đăng nhập để xem lịch sử làm bài của bạn.</p>
          <Link to="/" className="btn btn-primary" style={{ marginTop: '1rem' }}>Về trang chủ</Link>
        </div>
      ) : loading ? (
        <div className="loading-container">
          <Loader2 size={48} className="spinner" />
        </div>
      ) : documents.length === 0 && quizzes.length === 0 ? (
        <div className="placeholder-text card">
          <p>Bạn chưa có file upload hoặc lịch sử làm bài.</p>
          <Link to="/upload" className="btn btn-primary" style={{ marginTop: '1rem' }}>Upload tài liệu</Link>
        </div>
      ) : (
        <div className="history-list">
          <h3 style={{ marginBottom: "var(--spacing-sm)" }}>File đã upload</h3>
          {documents.length === 0 ? (
            <p style={{ color: "var(--color-text-secondary)", marginBottom: "var(--spacing-lg)" }}>
              Bạn chưa upload file nào khi đăng nhập.
            </p>
          ) : documents.map(document => (
            <div key={document.id} className="history-card card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--spacing-md)" }}>
              <div className="history-info">
                <h3 style={{ marginBottom: "var(--spacing-xs)" }}>{document.original_filename}</h3>
                <div className="history-meta" style={{ display: "flex", gap: "var(--spacing-sm)", color: "var(--color-text-secondary)", fontSize: "var(--font-size-sm)" }}>
                  <span>{document.quiz_count} bài quiz</span>
                  <span>• {new Date(document.created_at).toLocaleDateString("vi-VN")}</span>
                </div>
              </div>
              <button type="button" className="btn btn-secondary" onClick={() => handleDelete(document.id)}>
                <Trash2 size={16} /> Xóa
              </button>
            </div>
          ))}

          <h3 style={{ margin: "var(--spacing-xl) 0 var(--spacing-sm)" }}>Lịch sử làm bài</h3>
          {quizzes.map(quiz => (
            <div key={quiz.id} className="history-card card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--spacing-md)" }}>
              <div className="history-info">
                <h3 style={{ marginBottom: "var(--spacing-xs)" }}>{quiz.quiz_title}</h3>
                <div className="history-meta" style={{ display: "flex", gap: "var(--spacing-sm)", color: "var(--color-text-secondary)", fontSize: "var(--font-size-sm)" }}>
                  <span className="badge" style={{ background: "var(--color-primary)", color: "white", padding: "2px 8px", borderRadius: "var(--radius-full)" }}>{quiz.score}/{quiz.total}</span>
                  <span>• {quiz.percentage}%</span>
                  <span>• {new Date(quiz.completed_at).toLocaleDateString("vi-VN")}</span>
                </div>
              </div>
              <div className="history-actions" style={{ display: "flex", gap: "var(--spacing-sm)" }}>
                <Link to={`/attempt/${quiz.id}`} className="btn btn-primary">
                  <Play size={16} /> Xem lại
                </Link>
              </div>
            </div>
          ))}
          
          {/* Pagination */}
          {totalPages > 1 && (
            <div className="pagination" style={{ display: "flex", justifyContent: "center", gap: "var(--spacing-md)", alignItems: "center", marginTop: "var(--spacing-xl)" }}>
              <button 
                className="btn btn-secondary" 
                disabled={page === 1}
                onClick={() => fetchHistory(page - 1)}
              >
                Trang trước
              </button>
              <span>{page} / {totalPages}</span>
              <button 
                className="btn btn-secondary" 
                disabled={page === totalPages}
                onClick={() => fetchHistory(page + 1)}
              >
                Trang tiếp
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default HistoryPage;
