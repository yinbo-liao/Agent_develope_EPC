import { createContext, useContext } from 'react';

/** Profile returned by GET /api/auth/me. */
export interface AuthUser {
  user_id: string;
  username: string;
  email: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
}

export interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

/**
 * Context lives in its own module so components (e.g. Dashboard) can consume
 * auth state without importing the provider's API-client dependencies.
 */
export const AuthContext = createContext<AuthContextValue | null>(null);

/** Use inside routes always wrapped by AuthProvider. Throws when misconfigured. */
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return ctx;
}

/**
 * Use in components that must render without an AuthProvider (tests, isolated
 * stories). Returns null when no provider is mounted.
 */
export function useOptionalAuth(): AuthContextValue | null {
  return useContext(AuthContext);
}
