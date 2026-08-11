// Playwright config for the frontend browser-e2e tier.
//
// Promoted from e2e/playwright.config.template.js when the tier was adopted. It lives at the
// frontend/ root rather than inside e2e/ because Playwright resolves its config relative to the
// working directory — left in e2e/, `npm run test:e2e` from frontend/ would not find it and
// would silently run with defaults.
//
// TIER OVERLAP, STATED DEPLIBERATELY: this covers the same pyramid level as the Selenium suite in
// backend/tests/system/ — a real browser against a running app. Both are kept for now because the
// Selenium tier already carries the UC6/UC8/UC9/UC4/UC7 system cases and their plan IDs. Anything
// added here should be a flow those do not already drive, until a decision is made about which
// tier survives (see e2e/README.md).
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  // Fail the run if a spec was committed with `test.only` left in it.
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: process.env.FRONTEND_URL || "http://127.0.0.1:4173",
    trace: "on-first-retry",          // trace viewer on flaky retries
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],

  // The app is started by the workflow (as the `system` job already does), not by Playwright:
  // the backend has to come up alongside the frontend, and `webServer` only manages one of them.
  // Locally, start both by hand — see e2e/README.md.
});
