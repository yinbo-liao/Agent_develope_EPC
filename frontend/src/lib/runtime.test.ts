import { describe, expect, it } from "vitest";

import { runtimeConfig } from "./runtime";

describe("runtime config", () => {
  it("uses same-origin defaults when VITE_API_URL is unset", () => {
    expect(runtimeConfig.apiBase).toBe("");
    expect(runtimeConfig.wsBase).toMatch(/^ws/);
  });
});