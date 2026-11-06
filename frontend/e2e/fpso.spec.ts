import { test, expect, type Page } from '@playwright/test';

/**
 * End-to-end checks for the login flow and every dashboard tab.
 *
 * The dev backend seeds the `demo-project` project and the bootstrap admin
 * (admin / dev-admin-password by default). Override the credentials with
 * FPSO_E2E_USERNAME / FPSO_E2E_PASSWORD when running against another server.
 */
const ADMIN_USER = process.env.FPSO_E2E_USERNAME ?? 'admin';
const ADMIN_PASSWORD = process.env.FPSO_E2E_PASSWORD ?? 'dev-admin-password';

/** Sidebar tabs in render order (mirrors NAV_ITEMS in pages/Dashboard.tsx). */
const NAV_ITEMS = [
  'Overview',
  'Planning Board',
  'Engineering',
  'Procurement',
  'Construction',
  'System Completion',
  'Commissioning',
  'Inspection & NDT',
  'Quality (NCR)',
  'HSE Safety',
  'Training',
  'Stage Gates',
  'Conflicts',
  'Feedback Loop',
  'Traceability',
  'AI Insights',
  'Reports',
] as const;

interface ErrorCollectors {
  pageErrors: string[];
  apiFailures: string[];
}

/** Collect uncaught JS errors and any 5xx response from the API. */
function trackErrors(page: Page): ErrorCollectors {
  const pageErrors: string[] = [];
  const apiFailures: string[] = [];

  page.on('pageerror', (error) => pageErrors.push(error.message));
  page.on('response', (response) => {
    const url = response.url();
    if (url.includes('/api/') && response.status() >= 500) {
      apiFailures.push(`${response.status()} ${response.request().method()} ${url}`);
    }
  });

  return { pageErrors, apiFailures };
}

async function signIn(
  page: Page,
  username: string = ADMIN_USER,
  password: string = ADMIN_PASSWORD
): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('Username').fill(username);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Sign In', exact: true }).click();
}

test('rejects invalid credentials and stays on the login page', async ({ page }) => {
  const { pageErrors, apiFailures } = trackErrors(page);

  await signIn(page, ADMIN_USER, 'definitely-not-the-password');

  await expect(page.getByRole('alert')).toContainText('Invalid username or password.');
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('heading', { name: 'Sign in', exact: true })).toBeVisible();

  expect(apiFailures, `Unexpected API 5xx: ${apiFailures.join(', ')}`).toEqual([]);
  expect(pageErrors, `Uncaught page errors: ${pageErrors.join(' | ')}`).toEqual([]);
});

test('signs in, renders every dashboard tab, and logs out', async ({ page }) => {
  test.setTimeout(180_000);
  const { pageErrors, apiFailures } = trackErrors(page);

  await signIn(page);

  await expect(page).toHaveURL(/\/projects\/demo-project$/);
  await expect(page.getByRole('heading', { level: 2, name: 'Overview', exact: true })).toBeVisible();

  for (const label of NAV_ITEMS) {
    const tab = page.getByRole('button', { name: label, exact: true });
    await expect(tab, `nav tab "${label}" should be present`).toBeVisible();
    await tab.click();

    await expect(
      page.getByRole('heading', { level: 2, name: label, exact: true }),
      `header should switch to "${label}"`
    ).toBeVisible();
    await expect(page.getByText('This section encountered an error and could not be displayed.')).toHaveCount(0);
    await expect(page.getByText('Something went wrong')).toHaveCount(0);

    // Let the tab's initial queries settle before moving on.
    await page.waitForTimeout(500);
  }

  // Exercise the four AI analysis actions; each must reach a live endpoint.
  await page.getByRole('button', { name: 'AI Insights', exact: true }).click();
  await expect(page.getByRole('heading', { level: 2, name: 'AI Insights', exact: true })).toBeVisible();
  const analyzeButtons = page.getByRole('button', { name: 'Analyze', exact: true });
  await expect(analyzeButtons).toHaveCount(4);

  // Schedule Risk (0), Conflict Detection (1) and Weekly Report (3) call the API.
  for (const index of [0, 1, 3]) {
    const responsePromise = page.waitForResponse(
      (response) =>
        response.url().includes('/api/ai/analyze/') && response.request().method() === 'POST',
      { timeout: 30_000 }
    );
    await analyzeButtons.nth(index).click();
    const response = await responsePromise;
    expect(response.status(), `analysis request index ${index}`).toBe(200);
    await expect(page.getByText('Analysis failed')).toHaveCount(0);
  }

  // Gate Assessment needs a stage gate. The demo project has none, so the panel
  // must explain that instead of firing a request the API would reject with 400.
  await analyzeButtons.nth(2).click();
  await expect(
    page.getByText('No stage gates are available to assess for this project.')
  ).toBeVisible();
  await expect(page.getByText('Analysis failed')).toHaveCount(0);

  expect(apiFailures, `API 5xx responses: ${apiFailures.join(', ')}`).toEqual([]);
  expect(pageErrors, `Uncaught page errors: ${pageErrors.join(' | ')}`).toEqual([]);

  await page.getByRole('button', { name: 'Log out' }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('button', { name: 'Sign In', exact: true })).toBeVisible();

  const tokens = await page.evaluate(() => ({
    access: localStorage.getItem('fpso_access_token'),
    refresh: localStorage.getItem('fpso_refresh_token'),
  }));
  expect(tokens).toEqual({ access: null, refresh: null });
});
