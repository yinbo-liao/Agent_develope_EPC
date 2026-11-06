import { defineConfig, devices } from '@playwright/test';

/**
 * E2E configuration for the FPSO EPC dashboard.
 *
 * Assumes the API backend is already running on http://127.0.0.1:8080
 * (`backend/dev_main.py` for the SQLite dev backend). Vite is started here and
 * proxies /api and /ws to that backend.
 */
// Use `localhost` (not 127.0.0.1): the backend's default CORS/WS origin
// allow-list contains localhost:5173, and a mismatched Origin makes the
// dev WebSocket reject the handshake.
const HOST = 'localhost';
const PORT = 5173;
const BASE_URL = `http://${HOST}:${PORT}`;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  timeout: 90_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: `npm run dev -- --host ${HOST} --port ${PORT}`,
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
