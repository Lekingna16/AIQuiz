import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { GoogleOAuthProvider } from '@react-oauth/google'
import './index.css'
import App from './App.jsx'

// Loại bỏ khoảng trắng và dấu ngoặc thừa (nếu có) do lúc copy vào biến môi trường bị lỗi
const rawClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID || "936382741131-j7t3q6s6hndev66alq51160q67ni29k4.apps.googleusercontent.com";
const GOOGLE_CLIENT_ID = rawClientId.replace(/['"]/g, '').trim();

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>
      <App />
    </GoogleOAuthProvider>
  </StrictMode>,
)
