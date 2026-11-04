/**
 * Demo authentication helper.
 *
 * The access token is kept in sessionStorage so a page refresh does not lose the
 * session. For a demo this is acceptable; a production build should move the
 * token behind an httpOnly cookie or a backend-for-frontend.
 */

const TOKEN_KEY = "aiwf.access_token";

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
  const token = sessionStorage.getItem(TOKEN_KEY);
  if (!token) {
    return null;
  }
  const claims = decodeClaims(token);
  if (!claims.sub || (claims.exp !== undefined && claims.exp * 1000 <= Date.now())) {
    sessionStorage.removeItem(TOKEN_KEY);
    return null;
  }
  return {
    token,
    userId: claims.sub,
    role: claims.role ?? "viewer",
    tier: claims.tier ?? "starter",
  };
}

export function saveSession(token: string): Session {
  sessionStorage.setItem(TOKEN_KEY, token);
  const claims = decodeClaims(token);
  return {
    token,
    userId: claims.sub ?? "unknown",
    role: claims.role ?? "viewer",
    tier: claims.tier ?? "starter",
  };
}

export function clearSession(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

export function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const token = sessionStorage.getItem(TOKEN_KEY);
  return token ? { ...extra, Authorization: `Bearer ${token}` } : { ...extra };
}

/** Fetch with the bearer token; expires the local session on a 401. */
export async function authFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const response = await fetch(input, {
    ...init,
    headers: authHeaders((init.headers as Record<string, string> | undefined) ?? {}),
  });
  if (response.status === 401) {
    clearSession();
    window.dispatchEvent(new Event("aiwf:auth-expired"));
  }
  return response;
}