import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AUTH_REQUIRED_EVENT,
  apiClient,
  clearStoredTokens,
  getStoredRefreshToken,
  getStoredToken,
  setStoredTokens,
  type AuthTokens,
} from '../lib/api-client';
import { AuthContext, type AuthContextValue, type AuthUser } from './context';

/** User-safe error raised by login(); never exposes backend internals. */
export class AuthError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = 'AuthError';
    this.status = status;
  }
}

function toAuthError(error: unknown): AuthError {
  const status = (error as { response?: { status?: number } })?.response?.status;
  if (status === 401) {
    return new AuthError('Invalid username or password.', status);
  }
  if (status === 422) {
    return new AuthError('Please check your username and password.', status);
  }
  return new AuthError('Unable to sign in. Please try again.', status);
}

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const navigate = useNavigate();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState<boolean>(() => getStoredToken() !== null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const refreshUser = useCallback(async (): Promise<void> => {
    if (!getStoredToken()) {
      if (mountedRef.current) {
        setUser(null);
        setLoading(false);
      }
      return;
    }

    try {
      const response = await apiClient.get<AuthUser>('/api/auth/me');
      if (mountedRef.current) {
        setUser(response.data);
      }
    } catch {
      // 401s are handled by the api-client interceptor (refresh + retry).
      // If we still land here the session is gone.
      if (mountedRef.current) {
        setUser(null);
      }
    } finally {
      if (mountedRef.current) {
        setLoading(false);
      }
    }
  }, []);

  // Restore the session on first mount when an access token is present.
  useEffect(() => {
    if (getStoredToken()) {
      void refreshUser();
    } else {
      setLoading(false);
    }
  }, [refreshUser]);

  // The api-client dispatches this when a refresh fails or no retry is possible.
  useEffect(() => {
    const onAuthRequired = () => {
      if (mountedRef.current) {
        setUser(null);
        setLoading(false);
      }
    };
    window.addEventListener(AUTH_REQUIRED_EVENT, onAuthRequired);
    return () => window.removeEventListener(AUTH_REQUIRED_EVENT, onAuthRequired);
  }, []);

  const login = useCallback(async (username: string, password: string): Promise<void> => {
    let tokens: AuthTokens;
    try {
      const response = await apiClient.post<AuthTokens>('/api/auth/login', {
        username,
        password,
      });
      tokens = response.data;
    } catch (error) {
      clearStoredTokens();
      throw toAuthError(error);
    }

    setStoredTokens(tokens.access_token, tokens.refresh_token);

    try {
      const response = await apiClient.get<AuthUser>('/api/auth/me');
      if (mountedRef.current) {
        setUser(response.data);
        setLoading(false);
      }
    } catch (error) {
      clearStoredTokens();
      throw toAuthError(error);
    }
  }, []);

  const logout = useCallback(async (): Promise<void> => {
    const refreshToken = getStoredRefreshToken();
    try {
      await apiClient.post('/api/auth/logout', refreshToken ? { refresh_token: refreshToken } : {});
    } catch {
      // Best effort — local session is cleared regardless.
    }

    clearStoredTokens();
    if (mountedRef.current) {
      setUser(null);
      setLoading(false);
    }
    navigate('/login', { replace: true });
  }, [navigate]);

  const value = useMemo<AuthContextValue>(
    () => ({ user, loading, login, logout, refreshUser }),
    [user, loading, login, logout, refreshUser]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
