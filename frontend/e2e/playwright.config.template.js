// Playwright config TEMPLATE for frontend e2e.
//
// This file is a template — it is intentionally NOT named `playwright.config.js`
// so Playwright doesn't auto-load it before you're ready. When adopting Playwright:
//   1. npm i -D @playwright/test && npx playwright install
//   2. rename this file to `playwright.config.js`
//   3. start the app (backend on :8000, `npm run preview` on :4173) or wire
//      `webServer` below to start it automatically.

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",                       // specs live in frontend/e2e/
  timeout: 30_000,
  use: {
    baseURL: process.env.FRONTEND_URL || "http://127.0.0.1:4173",
    trace: "on-first-retry",          // trace viewer on flaky retries
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],

  // Optional: let Playwright build + serve the frontend itself. Requires the
  // VITE_* env (Supabase test project) to be set so login works.
  // webServer: {
  //   command: "npm run build && npm run preview -- --port 4173 --host 127.0.0.1",
  //   url: "http://127.0.0.1:4173",
  //   reuseExistingServer: !process.env.CI,
  //   env: {
  //     VITE_API_URL: "http://127.0.0.1:8000",
  //     VITE_SUPABASE_URL: process.env.SUPABASE_URL,
  //     VITE_SUPABASE_ANON_KEY: process.env.SUPABASE_ANON_KEY,
  //   },
  // },
});
