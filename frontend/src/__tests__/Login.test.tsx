import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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
import { LoginPage } from '../pages/LoginPage';

const TEST_USER = {
  user_id: 'user-1',
  username: 'alice',
  email: 'alice@example.com',
  full_name: 'Alice Doe',
  role: 'viewer',
  is_active: true,
};

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/projects/demo-project" element={<div>Dashboard Stub</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  );
}

describe('LoginPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mocks.getStoredToken.mockReturnValue(null);
    mocks.getStoredRefreshToken.mockReturnValue(null);
  });

  it('renders accessible username and password fields', () => {
    renderLogin();

    const username = screen.getByLabelText('Username');
    const password = screen.getByLabelText('Password');

    expect(username).toHaveAttribute('type', 'text');
    expect(password).toHaveAttribute('type', 'password');
    expect(screen.getByRole('button', { name: 'Sign In' })).toBeInTheDocument();
  });

  it('stores tokens and redirects after a successful login', async () => {
    mocks.post.mockResolvedValue({
      data: {
        access_token: 'access-token',
        refresh_token: 'refresh-token',
        token_type: 'bearer',
        expires_in: 900,
      },
    });
    mocks.get.mockResolvedValue({ data: TEST_USER });

    const user = userEvent.setup();
    renderLogin();

    await user.type(screen.getByLabelText('Username'), 'alice');
    await user.type(screen.getByLabelText('Password'), 'correct horse');
    await user.click(screen.getByRole('button', { name: 'Sign In' }));

    expect(await screen.findByText('Dashboard Stub')).toBeInTheDocument();
    expect(mocks.setStoredTokens).toHaveBeenCalledWith('access-token', 'refresh-token');
    expect(mocks.post).toHaveBeenCalledWith('/api/auth/login', {
      username: 'alice',
      password: 'correct horse',
    });
  });

  it('submits on Enter', async () => {
    mocks.post.mockResolvedValue({
      data: { access_token: 'a', refresh_token: 'r', token_type: 'bearer', expires_in: 900 },
    });
    mocks.get.mockResolvedValue({ data: TEST_USER });

    const user = userEvent.setup();
    renderLogin();

    await user.type(screen.getByLabelText('Username'), 'alice');
    await user.type(screen.getByLabelText('Password'), 'secret{Enter}');

    expect(await screen.findByText('Dashboard Stub')).toBeInTheDocument();
  });

  it('shows a user-safe error when credentials are rejected', async () => {
    mocks.post.mockRejectedValue({
      response: { status: 401, data: { detail: 'Invalid username or password.' } },
    });

    const user = userEvent.setup();
    renderLogin();

    await user.type(screen.getByLabelText('Username'), 'alice');
    await user.type(screen.getByLabelText('Password'), 'wrong');
    await user.click(screen.getByRole('button', { name: 'Sign In' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid username or password.');
    expect(mocks.setStoredTokens).not.toHaveBeenCalled();
    expect(screen.queryByText('Dashboard Stub')).not.toBeInTheDocument();
  });

  it('blocks submission when fields are empty', async () => {
    const user = userEvent.setup();
    renderLogin();

    await user.click(screen.getByRole('button', { name: 'Sign In' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Enter your username and password to continue.'
    );
    expect(mocks.post).not.toHaveBeenCalled();
  });
});
