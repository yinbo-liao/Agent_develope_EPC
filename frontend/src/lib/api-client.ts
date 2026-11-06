import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';

const ACCESS_TOKEN_KEY = 'fpso_access_token';
const REFRESH_TOKEN_KEY = 'fpso_refresh_token';

/** Shape returned by /api/auth/login and /api/auth/refresh. */
export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export const AUTH_REQUIRED_EVENT = 'fpso:auth-required';

// ---------------------------------------------------------------------------
// Token management
// ---------------------------------------------------------------------------

export function getStoredToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

/** Backwards-compatible helper: stores the access token only. */
export function setStoredToken(token: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, token);
}

export function getStoredRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setStoredTokens(accessToken: string, refreshToken?: string | null): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  if (refreshToken) {
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  }
}

/** Clears both tokens. Kept under the original name for compatibility. */
export function clearStoredToken(): void {
  clearStoredTokens();
}

export function clearStoredTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

/** Notify listeners (AuthProvider) that the session is no longer valid. */
export function notifyAuthRequired(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(AUTH_REQUIRED_EVENT));
  }
}

function handleAuthFailure(): void {
  clearStoredTokens();
  notifyAuthRequired();
}

// ---------------------------------------------------------------------------
// Token refresh (single-flight — concurrent 401s share one refresh request)
// ---------------------------------------------------------------------------

let refreshPromise: Promise<string> | null = null;

async function performRefresh(): Promise<string> {
  const refreshToken = getStoredRefreshToken();
  if (!refreshToken) {
    throw new Error('No refresh token available');
  }

  // Bare axios call: never routed through apiClient, so no Authorization
  // header is attached and a failing refresh cannot trigger another refresh.
  const response = await axios.post<AuthTokens>(
    '/api/auth/refresh',
    { refresh_token: refreshToken },
    { headers: { 'Content-Type': 'application/json' }, timeout: 30000 }
  );

  const { access_token, refresh_token } = response.data;
  setStoredTokens(access_token, refresh_token);
  return access_token;
}

/**
 * Exchange the stored refresh token for a new access token.
 * Concurrent callers share the same in-flight request; the promise is cleared
 * once it settles so a later expiry can refresh again.
 */
export function refreshAccessToken(): Promise<string> {
  if (!refreshPromise) {
    refreshPromise = performRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

// ---------------------------------------------------------------------------
// Axios client
// ---------------------------------------------------------------------------

function isAuthEndpoint(url: string | undefined): boolean {
  if (!url) return false;
  return url.includes('/api/auth/login') || url.includes('/api/auth/refresh');
}

type RetryableConfig = InternalAxiosRequestConfig & { _retry?: boolean };

export const apiClient = axios.create({
  baseURL: '/',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// Request interceptor — attach auth token (except login/refresh) + CSRF header
apiClient.interceptors.request.use((config) => {
  if (!isAuthEndpoint(config.url)) {
    const token = getStoredToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  // CSRF: send Origin header (browser does this automatically for same-origin)
  // For cross-origin, API clients should include X-Requested-With header
  config.headers['X-Requested-With'] = 'XMLHttpRequest';
  return config;
});

// Response interceptor — on 401, refresh once, retry once, then force login.
apiClient.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const status = error.response?.status;
    const original = error.config as RetryableConfig | undefined;

    if (status === 401 && original && !isAuthEndpoint(original.url)) {
      if (!original._retry) {
        original._retry = true;
        try {
          const token = await refreshAccessToken();
          original.headers.set('Authorization', `Bearer ${token}`);
          // Retry exactly once — the retried request carries _retry = true.
          return await apiClient(original);
        } catch {
          // Refresh failed — fall through and end the session.
        }
      }
      handleAuthFailure();
    }

    const responseData = error.response?.data as { detail?: string } | undefined;
    const msg = responseData?.detail || error.message;
    console.error(`[API Error ${status}]`, msg);
    return Promise.reject(error);
  }
);
