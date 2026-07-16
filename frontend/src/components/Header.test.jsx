import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { BrowserRouter } from 'react-router-dom';
import Header from './Header';
import useAuthStore from '../store/authStore';

// Mock the react-oauth/google module
vi.mock('@react-oauth/google', () => ({
  GoogleLogin: () => <button data-testid="google-login-btn">Mock Google Login</button>,
  googleLogout: vi.fn(),
}));

// Mock the Zustand store
vi.mock('../store/authStore', () => ({
  default: vi.fn(),
}));

describe('Header Component (TC-AUTH)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderWithRouter = (ui) => {
    return render(<BrowserRouter>{ui}</BrowserRouter>);
  };

  it('TC-AUTH-01: Displays Google Login button when not authenticated', () => {
    // Mock the store to return unauthenticated state
    useAuthStore.mockReturnValue({
      user: null,
      isAuthenticated: false,
      login: vi.fn(),
      logout: vi.fn(),
    });

    renderWithRouter(<Header />);

    // Check if the logo is present
    expect(screen.getByText('AIQuiz')).toBeInTheDocument();

    // Check if Google Login button is rendered
    expect(screen.getByTestId('google-login-btn')).toBeInTheDocument();
    
    // Check if user profile is NOT rendered
    expect(screen.queryByTitle('Đăng xuất')).not.toBeInTheDocument();
  });

  it('TC-AUTH-01/03: Displays user profile and Logout button when authenticated', () => {
    // Mock the store to return authenticated state
    useAuthStore.mockReturnValue({
      user: { full_name: 'Nguyen Van A', picture: 'https://example.com/avatar.jpg' },
      isAuthenticated: true,
      login: vi.fn(),
      logout: vi.fn(),
    });

    renderWithRouter(<Header />);

    // Google Login button should NOT be rendered
    expect(screen.queryByTestId('google-login-btn')).not.toBeInTheDocument();

    // User name should be displayed
    expect(screen.getByText('Nguyen Van A')).toBeInTheDocument();

    // Logout button should be rendered
    expect(screen.getByTitle('Đăng xuất')).toBeInTheDocument();
  });

  it('TC-AUTH-03: Triggers logout when Logout button is clicked', () => {
    const mockLogout = vi.fn();
    useAuthStore.mockReturnValue({
      user: { full_name: 'Nguyen Van A', picture: null },
      isAuthenticated: true,
      login: vi.fn(),
      logout: mockLogout,
    });

    renderWithRouter(<Header />);

    const logoutBtn = screen.getByTitle('Đăng xuất');
    fireEvent.click(logoutBtn);

    // The logout function from store should be called
    expect(mockLogout).toHaveBeenCalled();
  });
});
