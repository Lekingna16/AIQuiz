/**
 * App.jsx - Root Component với React Router
 * ============================================
 * 
 * React Router v6 pattern:
 * - BrowserRouter: dùng HTML5 History API (URL đẹp, không có #)
 * - Routes: container cho tất cả route definitions
 * - Route: map URL path → component
 * 
 * Tại sao dùng React Router thay vì conditional rendering?
 * → URL-based navigation: user có thể bookmark, share link
 * → Browser back/forward hoạt động đúng
 * → SEO friendly hơn (nếu cần SSR sau này)
 */

import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";

import HomePage from "./pages/HomePage";
import QuizPage from "./pages/QuizPage";
import HistoryPage from "./pages/HistoryPage";
import UploadPage from "./pages/UploadPage";

import Header from "./components/Header";

function App() {
  return (
    <BrowserRouter>
      {/* 
        Toaster: hiển thị toast notifications (success, error, loading)
        Sonner là toast library nhẹ, đẹp, dễ dùng.
        Đặt ở root để mọi component đều có thể trigger toast.
        
        Usage trong component bất kỳ:
          import { toast } from "sonner";
          toast.success("Upload thành công!");
          toast.error("Có lỗi xảy ra");
      */}
      <Toaster
        position="top-right"
        richColors
        toastOptions={{
          duration: 4000,
        }}
      />

      <Header />

      <main className="app-container">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/quiz/:quizId" element={<QuizPage />} />
          <Route path="/history" element={<HistoryPage />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}

export default App;
