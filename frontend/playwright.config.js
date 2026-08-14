// Playwright config for the frontend browser-e2e tier.
//
// Promoted from e2e/playwright.config.template.js when the tier was adopted. It lives at the
// frontend/ root rather than inside e2e/ because Playwright resolves its config relative to the
// working directory — left in e2e/, `npm run test:e2e` from frontend/ would not find it and
// would silently run with defaults.
//
// TIER OVERLAP, STATED DELIBERATELY: this covers the same pyramid level as the Selenium suite in
// backend/tests/system/ — a real browser against a running app. There is now one spec per use case
// here, overlapping the Selenium system cases on purpose, so the PM3 plan's frontend-E2E column has
// a slot for each. The specs assert the same postconditions through the same selectors so both
// suites break together rather than one at a time. The duplication is a known cost and the choice
// of which tier survives is still open — see e2e/README.md.
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
