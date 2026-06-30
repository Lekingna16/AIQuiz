/**
 * HistoryPage - Lịch sử các quiz đã tạo
 * 
 * Phase 1: Placeholder
 * Phase 4: Danh sách quiz với pagination, click vào để làm lại
 */

import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Clock, Loader2, Play, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { getMyQuizzes } from "../services/api";
import axios from "axios";

function HistoryPage() {
  const [quizzes, setQuizzes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  const fetchHistory = async (pageToFetch) => {
    setLoading(true);
    try {
      const data = await getMyQuizzes(pageToFetch, 10);
      setQuizzes(data.quizzes);
      setTotalPages(data.pages);
      setPage(data.page);
    } catch (error) {
      toast.error("Không thể tải lịch sử. Vui lòng thử lại.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory(1);
  }, []);

  const handleDelete = async (id) => {
    if (!window.confirm("Bạn có chắc chắn muốn xóa bài quiz này?")) return;
    
    try {
      await axios.delete(`http://localhost:8000/api/quizzes/${id}`);
      toast.success("Đã xóa quiz.");
      fetchHistory(page);
    } catch (error) {
      toast.error("Không thể xóa quiz.");
    }
  };

  return (
    <div className="history-page">
      <Link to="/" className="back-link">
        <ArrowLeft size={20} /> Về trang chủ
      </Link>

      <h2><Clock size={28} /> Lịch sử Quiz</h2>

      {loading ? (
        <div className="loading-container">
          <Loader2 size={48} className="spinner" />
        </div>
      ) : quizzes.length === 0 ? (
        <div className="placeholder-text card">
          <p>Bạn chưa tạo bài quiz nào.</p>
          <Link to="/" className="btn btn-primary" style={{ marginTop: '1rem' }}>Tạo ngay</Link>
        </div>
      ) : (
        <div className="history-list">
          {quizzes.map(quiz => (
            <div key={quiz.id} className="history-card card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--spacing-md)" }}>
              <div className="history-info">
                <h3 style={{ marginBottom: "var(--spacing-xs)" }}>{quiz.title}</h3>
                <div className="history-meta" style={{ display: "flex", gap: "var(--spacing-sm)", color: "var(--color-text-secondary)", fontSize: "var(--font-size-sm)" }}>
                  <span className="badge" style={{ background: "rgba(255,255,255,0.1)", padding: "2px 8px", borderRadius: "var(--radius-full)" }}>{quiz.difficulty}</span>
                  <span>• {quiz.total_questions} câu hỏi</span>
                  <span>• {new Date(quiz.created_at).toLocaleDateString("vi-VN")}</span>
                </div>
              </div>
              <div className="history-actions" style={{ display: "flex", gap: "var(--spacing-sm)" }}>
                <Link to={`/quiz/${quiz.id}`} className="btn btn-primary">
                  <Play size={16} /> Làm bài
                </Link>
                <button className="btn btn-secondary icon-only" onClick={() => handleDelete(quiz.id)}>
                  <Trash2 size={16} color="var(--color-error)" />
                </button>
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
