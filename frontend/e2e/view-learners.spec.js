// FRONTEND E2E — Playwright. UC9 View Learner List (PLACEHOLDER).
//
// Browser-driven counterpart to the Selenium `system` tests / pytest `e2e` tier. NOT YET
// IMPLEMENTED — scaffolded so the Playwright tier shows a slot per use case. Fill in the steps
// and remove `.skip` on the describe block to activate.
//
// NOTE: the Selenium suite already owns UC9 (backend/tests/system/test_uc9_view_learners.py).
// Only add here a flow it does not already drive, per e2e/README.md's tier-overlap policy.
//
// Requires the app running (backend :8000, built frontend :4173) and TEST-project credentials.
import { expect, test } from "@playwright/test";

const EMAIL = process.env.TEST_THERAPIST_EMAIL;
const PASSWORD = process.env.TEST_THERAPIST_PASSWORD;

test.describe.skip("UC9 View Learner List", () => {
  test("therapist opens Learners and the list renders", async ({ page }) => {
    // TODO:
    // 1. logIn(page)
    // 2. click the "Learners" nav link
    // 3. expect learner cards + a count to render
    // 4. (optional) type in the search box and expect the list to filter
    expect(EMAIL && PASSWORD).toBeTruthy();
  });
});
