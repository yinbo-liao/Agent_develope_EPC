import { useState } from "react";

import { saveSession, type Session } from "../lib/auth";
import { runtimeConfig } from "../lib/runtime";

export function LoginPage({ onLogin }: { onLogin: (session: Session) => void }) {
  const [username, setUsername] = useState("demo");
  const [password, setPassword] = useState("demo-pass-1234");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const response = await fetch(`${runtimeConfig.apiBase}/api/v1/auth/token`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!response.ok) {
        throw new Error(response.status === 401 ? "Invalid username or password." : "Sign-in failed.");
      }
      const payload = (await response.json()) as { access_token: string };
      onLogin(saveSession(payload.access_token));
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : "Sign-in failed.");
    } finally {
      setPending(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-neutral-50 px-6 text-neutral-900">
      <form
        className="w-full max-w-md space-y-5 rounded-2xl border border-neutral-200 bg-white p-8 shadow-soft"
        onSubmit={(event) => void submit(event)}
      >
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">AI Workflow Platform</h1>
          <p className="mt-2 text-sm text-neutral-600">
            Sign in to create workflows and review high-risk runs.
          </p>
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium text-neutral-700" htmlFor="username">
            Username
          </label>
          <input
            id="username"
            className="w-full rounded-xl border border-neutral-200 px-4 py-2 text-sm"
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium text-neutral-700" htmlFor="password">
            Password
          </label>
          <input
            id="password"
            type="password"
            className="w-full rounded-xl border border-neutral-200 px-4 py-2 text-sm"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>
        {error ? (
          <p className="text-sm text-red-600" role="alert">
            {error}
          </p>
        ) : null}
        <button
          type="submit"
          className="w-full rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-60"
          disabled={pending}
        >
          {pending ? "Signing in..." : "Sign in"}
        </button>
        <p className="rounded-xl bg-neutral-50 p-3 text-xs text-neutral-500">
          Demo users: <span className="font-mono">demo</span> /{" "}
          <span className="font-mono">demo-pass-1234</span> (requester) and{" "}
          <span className="font-mono">reviewer</span> /{" "}
          <span className="font-mono">reviewer-pass-1234</span> (approver).
        </p>
      </form>
    </main>
  );
}