import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  getStoredToken: vi.fn(),
  getStoredRefreshToken: vi.fn(),
  setStoredToken: vi.fn(),
  setStoredTokens: vi.fn(),
  clearStoredToken: vi.fn(),
  clearStoredTokens: vi.fn(),
  refreshAccessToken: vi.fn(),
  notifyAuthRequired: vi.fn(),
}));

vi.mock('../lib/api-client', () => ({
  AUTH_REQUIRED_EVENT: 'fpso:auth-required',
  apiClient: { get: mocks.get, post: mocks.post },
  getStoredToken: mocks.getStoredToken,
  getStoredRefreshToken: mocks.getStoredRefreshToken,
  setStoredToken: mocks.setStoredToken,
  setStoredTokens: mocks.setStoredTokens,
  clearStoredToken: mocks.clearStoredToken,
  clearStoredTokens: mocks.clearStoredTokens,
  refreshAccessToken: mocks.refreshAccessToken,
  notifyAuthRequired: mocks.notifyAuthRequired,
}));

import { AuthProvider } from '../auth/AuthProvider';
import { ProtectedRoute } from '../auth/ProtectedRoute';

const TEST_USER = {
  user_id: 'user-1',
  username: 'alice',
  email: 'alice@example.com',
  full_name: 'Alice Doe',
  role: 'project_manager',
  is_active: true,
};

function renderApp(initialEntry: string) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<div>Login Page</div>} />
          <Route
            path="/secret"
            element={
              <ProtectedRoute>
                <div>Protected Content</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  );
}

describe('ProtectedRoute', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mocks.getStoredToken.mockReturnValue(null);
    mocks.getStoredRefreshToken.mockReturnValue(null);
  });

  it('redirects unauthenticated users to the login page', async () => {
    renderApp('/secret');

    expect(await screen.findByText('Login Page')).toBeInTheDocument();
    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument();
  });

  it('shows a loading state and does not redirect while restoring the session', () => {
    mocks.getStoredToken.mockReturnValue('stored-token');
    // Never resolves — keeps the provider in its loading state.
    mocks.get.mockReturnValue(new Promise(() => {}));

    renderApp('/secret');

    expect(screen.getByRole('status', { name: 'Checking authentication' })).toBeInTheDocument();
    expect(screen.getByText('Checking authentication')).toBeInTheDocument();
    expect(screen.queryByText('Login Page')).not.toBeInTheDocument();
    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument();
  });

  it('renders protected content for an authenticated user', async () => {
    mocks.getStoredToken.mockReturnValue('stored-token');
    mocks.get.mockResolvedValue({ data: TEST_USER });

    renderApp('/secret');

    expect(screen.getByText('Checking authentication')).toBeInTheDocument();
    expect(await screen.findByText('Protected Content')).toBeInTheDocument();
    expect(screen.queryByText('Login Page')).not.toBeInTheDocument();
  });
});
