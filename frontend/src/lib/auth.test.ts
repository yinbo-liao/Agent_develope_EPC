import { beforeEach, describe, expect, it } from "vitest";

import { clearSession, decodeClaims, loadSession, saveSession } from "./auth";

function makeToken(claims: Record<string, unknown>): string {
  const payload = btoa(JSON.stringify(claims))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
  return `header.${payload}.signature`;
}

describe("auth session helpers", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("decodes JWT claims", () => {
    const token = makeToken({ sub: "user-1", role: "reviewer", tier: "starter" });
    expect(decodeClaims(token)).toMatchObject({
      sub: "user-1",
      role: "reviewer",
      tier: "starter",
    });
  });

  it("stores and reloads a session", () => {
    const token = makeToken({
      sub: "user-1",
      role: "viewer",
      tier: "free",
      exp: Math.floor(Date.now() / 1000) + 600,
    });
    saveSession(token, "refresh-1");
    expect(sessionStorage.getItem("aiwf.refresh_token")).toBe("refresh-1");

    const session = loadSession();
    expect(session?.userId).toBe("user-1");
    expect(session?.role).toBe("viewer");
  });

  it("drops an expired session", () => {
    const token = makeToken({
      sub: "user-1",
      exp: Math.floor(Date.now() / 1000) - 10,
    });
    sessionStorage.setItem("aiwf.access_token", token);
    expect(loadSession()).toBeNull();
    expect(sessionStorage.getItem("aiwf.access_token")).toBeNull();
  });

  it("clears both tokens", () => {
    sessionStorage.setItem("aiwf.access_token", "a");
    sessionStorage.setItem("aiwf.refresh_token", "r");
    clearSession();
    expect(sessionStorage.getItem("aiwf.access_token")).toBeNull();
    expect(sessionStorage.getItem("aiwf.refresh_token")).toBeNull();
  });
});