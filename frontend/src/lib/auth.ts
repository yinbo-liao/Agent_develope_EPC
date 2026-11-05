/**
 * Demo authentication helper.
 *
 * Access and refresh tokens are kept in sessionStorage so a page refresh does not
 * lose the session. For a demo this is acceptable; a production build should move
 * them behind an httpOnly cookie or a backend-for-frontend.
 */

const ACCESS_KEY = "aiwf.access_token";
const REFRESH_KEY = "aiwf.refresh_token";

export type Session = {
  token: string;
  userId: string;
  role: string;
  tier: string;
};

type JwtClaims = {
  sub?: string;
  role?: string;
  tier?: string;
  exp?: number;
};

export function decodeClaims(token: string): JwtClaims {
  try {
    const payload = token.split(".")[1];
    if (!payload) {
      return {};
    }
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(normalized)) as JwtClaims;
  } catch {
    return {};
  }
}

export function loadSession(): Session | null {
  const token = sessionStorage.getItem(ACCESS_KEY);
  if (!token) {
    return null;
  }
  const claims = decodeClaims(token);
  if (!claims.sub || (claims.exp !== undefined && claims.exp * 1000 <= Date.now())) {
    sessionStorage.removeItem(ACCESS_KEY);
    sessionStorage.removeItem(REFRESH_KEY);
    return null;
  }
  return {
    token,
    userId: claims.sub,
    role: claims.role ?? "viewer",
    tier: claims.tier ?? "starter",
  };
}

export function saveSession(token: string, refreshToken?: string): Session {
  sessionStorage.setItem(ACCESS_KEY, token);
  if (refreshToken) {
    sessionStorage.setItem(REFRESH_KEY, refreshToken);
  }
  const claims = decodeClaims(token);
  return {
    token,
    userId: claims.sub ?? "unknown",
    role: claims.role ?? "viewer",
    tier: claims.tier ?? "starter",
  };
}

export function clearSession(): void {
  sessionStorage.removeItem(ACCESS_KEY);
  sessionStorage.removeItem(REFRESH_KEY);
}

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const token = sessionStorage.getItem(ACCESS_KEY);
  return token ? { ...extra, Authorization: `Bearer ${token}` } : { ...extra };
}

function expireSession(): void {
  clearSession();
  window.dispatchEvent(new Event("aiwf:auth-expired"));
}

let refreshInFlight: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  if (refreshInFlight) {
    return refreshInFlight;
  }
  const refreshToken = sessionStorage.getItem(REFRESH_KEY);
  if (!refreshToken) {
    return false;
  }
  refreshInFlight = (async () => {
    try {
      const response = await fetch(`${import.meta.env.VITE_API_URL ?? ""}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!response.ok) {
        return false;
      }
      const payload = (await response.json()) as {
        access_token: string;
        refresh_token: string;
      };
      sessionStorage.setItem(ACCESS_KEY, payload.access_token);
      sessionStorage.setItem(REFRESH_KEY, payload.refresh_token);
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

/** Fetch with the bearer token, refreshing once on a 401 before expiring. */
export async function authFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const request = { ...init, headers: authHeaders((init.headers as Record<string, string> | undefined) ?? {}) };
  let response = await fetch(input, request);
  if (response.status === 401) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      response = await fetch(input, {
        ...init,
        headers: authHeaders((init.headers as Record<string, string> | undefined) ?? {}),
      });
    }
    if (response.status === 401) {
      expireSession();
    }
  }
  return response;
}

/** Revoke the refresh token server-side, then clear local state. */
export async function logout(): Promise<void> {
  const refreshToken = sessionStorage.getItem(REFRESH_KEY);
  if (refreshToken) {
    try {
      await fetch(`${import.meta.env.VITE_API_URL ?? ""}/api/v1/auth/logout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    } catch {
      // Best effort: local sign-out still proceeds.
    }
  }
  clearSession();
}