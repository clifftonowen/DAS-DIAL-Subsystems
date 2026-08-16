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
  // 60s per test, not 30. These drive a real browser against a real backend and a real Supabase
  // project, and a single test can log in, navigate, submit and wait on a round trip. The budget
  // has to exceed the SUM of the individual locator waits inside a test, or the test dies before
  // any of them can report — turning "the semester list never arrived" into a bare "test timeout
  // exceeded" with nothing pointing at the cause. Individual waits stay well under this.
  timeout: 60_000,
  // Fail the run if a spec was committed with `test.only` left in it.
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  // On CI, emit a machine-readable summary alongside the human ones. The `frontend-e2e` job reads
  // its `stats` block to fail a run in which NOTHING executed — `playwright test` exits 0 when
  // every spec is skipped, so without that check a green job reads as browser coverage it does not
  // have. See the "Fail if no browser tests actually ran" step in .github/workflows/tests.yml.
  reporter: process.env.CI
    ? [["list"], ["html", { open: "never" }], ["json", { outputFile: "playwright-results.json" }]]
    : [["list"]],
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
