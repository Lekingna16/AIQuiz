import React, { useState, useEffect } from "react";
import { Send, User as UserIcon, Loader2 } from "lucide-react";
import { getComments, addComment } from "../services/api";
import useAuthStore from "../store/authStore";

const Comments = ({ questionId }) => {
  const { user, isAuthenticated } = useAuthStore();
  const [comments, setComments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newComment, setNewComment] = useState("");
  const [guestName, setGuestName] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    fetchComments();
  }, [questionId]);

  const fetchComments = async () => {
    setLoading(true);
    try {
      const data = await getComments(questionId);
      setComments(data);
    } catch (error) {
      console.error("Lỗi khi tải bình luận", error);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!newComment.trim()) return;

    setIsSubmitting(true);
    try {
      const data = {
        content: newComment,
        guest_name: !isAuthenticated ? (guestName || "Khách") : undefined,
      };
      const createdComment = await addComment(questionId, data);
      setComments([...comments, createdComment]);
      setNewComment("");
    } catch (error) {
      console.error("Lỗi khi thêm bình luận", error);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="comments-section" style={{ marginTop: "2rem", borderTop: "1px solid var(--border-color)", paddingTop: "1rem" }}>
      <h4 style={{ marginBottom: "1rem" }}>Bàn luận về câu hỏi này</h4>
      
      {/* Comment Form */}
      <form onSubmit={handleSubmit} className="comment-form" style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginBottom: "1.5rem" }}>
        {!isAuthenticated && (
          <input
            type="text"
            placeholder="Tên của bạn (Tùy chọn)"
            value={guestName}
            onChange={(e) => setGuestName(e.target.value)}
            className="form-input"
            style={{ padding: "0.5rem", borderRadius: "4px", border: "1px solid var(--border-color)", maxWidth: "300px" }}
          />
        )}
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <input
            type="text"
            placeholder="Viết bình luận..."
            value={newComment}
            onChange={(e) => setNewComment(e.target.value)}
            className="form-input"
            style={{ flex: 1, padding: "0.5rem", borderRadius: "4px", border: "1px solid var(--border-color)" }}
            required
          />
          <button 
            type="submit" 
            className="btn btn-primary" 
            disabled={isSubmitting || !newComment.trim()}
            style={{ padding: "0.5rem 1rem" }}
          >
            {isSubmitting ? <Loader2 size={16} className="spinner" /> : <Send size={16} />}
          </button>
        </div>
      </form>

      {/* Comment List */}
      <div className="comments-list" style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        {loading ? (
          <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem" }}>Đang tải bình luận...</p>
        ) : comments.length > 0 ? (
          comments.map((comment) => (
            <div key={comment.id} className="comment-item" style={{ display: "flex", gap: "0.5rem", background: "var(--bg-color)", padding: "0.8rem", borderRadius: "8px" }}>
              <div className="avatar" style={{ width: "32px", height: "32px", borderRadius: "50%", background: "var(--border-color)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-secondary)" }}>
                <UserIcon size={16} />
              </div>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <strong style={{ fontSize: "0.9rem" }}>{comment.guest_name || "Thành viên"}</strong>
                  <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                    {new Date(comment.created_at).toLocaleDateString('vi-VN')}
                  </span>
                </div>
                <p style={{ margin: "0.2rem 0 0 0", fontSize: "0.95rem" }}>{comment.content}</p>
              </div>
            </div>
          ))
        ) : (
          <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem" }}>Chưa có bình luận nào. Hãy là người đầu tiên!</p>
        )}
      </div>
    </div>
  );
};

export default Comments;
