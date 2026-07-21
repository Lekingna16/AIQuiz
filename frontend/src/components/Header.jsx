import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { GoogleLogin, googleLogout } from '@react-oauth/google';
import { LogOut, User as UserIcon, Moon, Sun, Menu, X, UploadCloud, Sparkles, History } from 'lucide-react';
import { toast } from 'sonner';
import { loginWithGoogle, loginMock } from '../services/api';
import useAuthStore from '../store/authStore';

const Header = () => {
  const { user, isAuthenticated, login, logout } = useAuthStore();
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  return (
    <header className="app-header">
      <div className="header-container">
        <Link to="/" className="logo" onClick={() => setIsMenuOpen(false)}>
          <h1>AIQuiz</h1>
        </Link>
        
        <button 
          className="mobile-menu-toggle" 
          onClick={() => setIsMenuOpen(!isMenuOpen)}
          aria-label="Toggle menu"
        >
          {isMenuOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
        
        <nav className={`header-nav ${isMenuOpen ? 'open' : ''}`}>
          <Link to="/upload" className="nav-link" onClick={() => setIsMenuOpen(false)}>
            <UploadCloud size={18} /> Upload tài liệu
          </Link>
          <Link to="/generate" className="nav-link" onClick={() => setIsMenuOpen(false)}>
            <Sparkles size={18} style={{ color: "var(--color-primary)" }} /> Sinh câu hỏi AI
          </Link>
          <Link to="/history" className="nav-link" onClick={() => setIsMenuOpen(false)}>
            <History size={18} /> Lịch sử
          </Link>


          
          {isAuthenticated && user ? (
            <div className="user-profile">
              <div className="user-info">
                {user.picture ? (
                  <img src={user.picture} alt={user.full_name} className="user-avatar" referrerPolicy="no-referrer" />
                ) : (
                  <div className="user-avatar-placeholder">
                    <UserIcon size={16} />
                  </div>
                )}
                <span className="user-name">{user.full_name}</span>
              </div>
              <button 
                className="btn btn-secondary logout-btn"
                onClick={() => {
                  googleLogout();
                  logout();
                  toast.success('Đã đăng xuất');
                }}
                title="Đăng xuất"
              >
                <LogOut size={16} />
              </button>
            </div>
          ) : (
            <div className="auth-wrapper" style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <GoogleLogin
                onSuccess={async (credentialResponse) => {
                  try {
                    const data = await loginWithGoogle(credentialResponse.credential);
                    login(data.user, data.access_token);
                    toast.success(`Xin chào, ${data.user.full_name}!`);
                  } catch (error) {
                    const errorMsg = error.response?.data?.detail || 'Lỗi xác thực từ Server';
                    toast.error(errorMsg);
                  }
                }}
                onError={() => {
                  toast.error('Đăng nhập Google thất bại');
                }}
                useOneTap
                shape="pill"
                theme="outline"
              />
              <button
                className="btn btn-secondary"
                onClick={async () => {
                  try {
                    const data = await loginMock();
                    login(data.user, data.access_token);
                    toast.success(`Xin chào, ${data.user.full_name}! (Mock User)`);
                  } catch (error) {
                    const errorMsg = error.response?.data?.detail || 'Lỗi đăng nhập Mock';
                    toast.error(errorMsg);
                  }
                }}
                style={{ padding: '6px 12px', fontSize: '14px', borderRadius: '9999px', whiteSpace: 'nowrap' }}
              >
                Mock Login
              </button>
            </div>
          )}
        </nav>
      </div>
    </header>
  );
};

export default Header;
