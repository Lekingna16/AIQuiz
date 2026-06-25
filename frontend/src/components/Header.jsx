import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { GoogleLogin, googleLogout } from '@react-oauth/google';
import { LogOut, User as UserIcon, Moon, Sun } from 'lucide-react';
import { toast } from 'sonner';
import { loginWithGoogle } from '../services/api';
import useAuthStore from '../store/authStore';

const Header = () => {
  const { user, isAuthenticated, login, logout } = useAuthStore();
  const [isDark, setIsDark] = useState(() => {
    // Check local storage or system preference
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme) return savedTheme === 'dark';
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  });

  useEffect(() => {
    // Apply theme
    if (isDark) {
      document.documentElement.setAttribute('data-theme', 'dark');
      localStorage.setItem('theme', 'dark');
    } else {
      document.documentElement.setAttribute('data-theme', 'light');
      localStorage.setItem('theme', 'light');
    }
  }, [isDark]);

  return (
    <header className="app-header">
      <div className="header-container">
        <Link to="/" className="logo">
          <span className="logo-icon">🧠</span>
          <h1>AIQuiz</h1>
        </Link>
        
        <nav className="header-nav">
          <Link to="/history" className="nav-link">Lịch sử</Link>

          <button 
            className="theme-toggle" 
            onClick={() => setIsDark(!isDark)}
            aria-label="Toggle theme"
          >
            <div className={`theme-toggle-track ${isDark ? 'dark' : 'light'}`}>
              <div className="theme-toggle-thumb">
                {isDark ? <Moon size={14} className="icon-moon" /> : <Sun size={14} className="icon-sun" />}
              </div>
            </div>
          </button>
          
          {isAuthenticated && user ? (
            <div className="user-profile">
              <div className="user-info">
                {user.picture ? (
                  <img src={user.picture} alt={user.full_name} className="user-avatar" />
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
            <GoogleLogin
              onSuccess={async (credentialResponse) => {
                try {
                  const data = await loginWithGoogle(credentialResponse.credential);
                  login(data.user, data.access_token);
                  toast.success(`Xin chào, ${data.user.full_name}!`);
                } catch (error) {
                  toast.error('Lỗi xác thực từ Server');
                }
              }}
              onError={() => {
                toast.error('Đăng nhập Google thất bại');
              }}
              useOneTap
              shape="pill"
              theme={isDark ? "filled_black" : "outline"}
            />
          )}
        </nav>
      </div>
    </header>
  );
};

export default Header;
