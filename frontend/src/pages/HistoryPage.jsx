/**
 * HistoryPage - Lịch sử các quiz đã tạo
 * 
 * Phase 1: Placeholder
 * Phase 4: Danh sách quiz với pagination, click vào để làm lại
 */

import { Link } from "react-router-dom";
import { ArrowLeft, Clock } from "lucide-react";

function HistoryPage() {
  return (
    <div className="history-page">
      <Link to="/" className="back-link">
        <ArrowLeft size={20} />
        Về trang chủ
      </Link>

      <h2>
        <Clock size={28} />
        Lịch sử Quiz
      </h2>

      <div className="placeholder-text">
        <p>Danh sách quiz sẽ hiển thị ở đây sau Phase 4.</p>
      </div>
    </div>
  );
}

export default HistoryPage;
