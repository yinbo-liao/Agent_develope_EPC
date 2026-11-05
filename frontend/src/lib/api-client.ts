import axios from 'axios';

const TOKEN_KEY = 'fpso_access_token';

// Token management
export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearStoredToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export const apiClient = axios.create({
  baseURL: '/',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// Request interceptor — attach auth token + CSRF header
apiClient.interceptors.request.use((config) => {
  const token = getStoredToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  // CSRF: send Origin header (browser does this automatically for same-origin)
  // For cross-origin, API clients should include X-Requested-With header
  config.headers['X-Requested-With'] = 'XMLHttpRequest';
  return config;
});

// Response interceptor — handle 401 (token expiry)
apiClient.interceptors.response.use(
  (r) => r,
  (err) => {
    const status = err.response?.status;
    const msg = err.response?.data?.detail || err.message;

    if (status === 401) {
      // Clear expired token — user must re-login
      clearStoredToken();
      // Dispatch custom event so the app can show login UI
      window.dispatchEvent(new CustomEvent('fpso:auth-required'));
    }

    console.error(`[API Error ${status}]`, msg);
    return Promise.reject(err);
  }
);
