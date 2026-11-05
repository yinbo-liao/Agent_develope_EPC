import { expect, test } from "@playwright/test";

test("demo user signs in and launches a workflow", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Username").fill("demo");
  await page.getByLabel("Password").fill("demo-pass-1234");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByRole("heading", { name: "AI Workflow Platform" })).toBeVisible();

  await page.getByLabel("Workflow request").fill("Review the deployment plan for security impact.");
  await page.getByRole("button", { name: /Create and monitor workflow/i }).click();

  await expect(page.getByText("Watching task")).toBeVisible();
  await expect(page.getByText("Current Status")).toBeVisible();
});

test("wrong password is rejected", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Username").fill("demo");
  await page.getByLabel("Password").fill("wrong-password");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByRole("alert")).toContainText(/invalid username or password/i);
});