import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { GoogleLogin, googleLogout } from '@react-oauth/google';
import { LogOut, User as UserIcon, Moon, Sun } from 'lucide-react';
import { toast } from 'sonner';
import { loginWithGoogle } from '../services/api';
import useAuthStore from '../store/authStore';

const Header = () => {
  const { user, isAuthenticated, login, logout } = useAuthStore();

  return (
    <header className="app-header">
      <div className="header-container">
        <Link to="/" className="logo">
          <h1>AIQuiz</h1>
        </Link>
        
        <nav className="header-nav">
          <Link to="/upload" className="nav-link">Upload tài liệu</Link>
          <Link to="/generate" className="nav-link" style={{ display: "flex", alignItems: "center", gap: "4px" }}>
            <span style={{ color: "var(--primary-color)", fontWeight: "bold" }}>✨ AI</span> Sinh câu hỏi
          </Link>
          <Link to="/history" className="nav-link">Lịch sử</Link>


          
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
          )}
        </nav>
      </div>
    </header>
  );
};

export default Header;
