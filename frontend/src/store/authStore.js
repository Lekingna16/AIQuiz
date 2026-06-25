import { create } from 'zustand';
import { persist } from 'zustand/middleware';

/**
 * Auth Store (Zustand)
 * Quản lý trạng thái đăng nhập của người dùng toàn cục
 * 
 * Sử dụng persist middleware để lưu state vào localStorage,
 * giúp giữ trạng thái đăng nhập khi refresh trang.
 */
const useAuthStore = create(
  persist(
    (set) => ({
      user: null,
      token: null,
      isAuthenticated: false,

      // Action đăng nhập thành công
      login: (userData, tokenData) => set({
        user: userData,
        token: tokenData,
        isAuthenticated: true,
      }),

      // Action đăng xuất
      logout: () => set({
        user: null,
        token: null,
        isAuthenticated: false,
      }),
      
      // Update thông tin user
      setUser: (userData) => set({ user: userData }),
    }),
    {
      name: 'auth-storage', // Tên key trong localStorage
    }
  )
);

export default useAuthStore;
