// FRONTEND E2E — Playwright. UC2 Generate Learner Profile (PLACEHOLDER).
//
// Browser-driven counterpart to the Selenium `system` tests / pytest `e2e` tier. NOT YET
// IMPLEMENTED — scaffolded so the Playwright tier shows a slot per use case. Fill in the steps
// and remove `.skip` on the describe block to activate.
//
// Requires the app running (backend :8000, built frontend :4173) and TEST-project credentials.
import { expect, test } from "@playwright/test";

const EMAIL = process.env.TEST_THERAPIST_EMAIL;
const PASSWORD = process.env.TEST_THERAPIST_PASSWORD;

test.describe.skip("UC2 Generate Learner Profile", () => {
  test("therapist generates a profile and sees the visualisation", async ({ page }) => {
    // TODO:
    // 1. logIn(page)
    // 2. navigate to /learners/${TEST_LEARNER_ID}
    // 3. click "Generate Profile"
    // 4. expect the profile visualisation (e.g. the radar chart / metrics) to render
    expect(EMAIL && PASSWORD).toBeTruthy();
  });
});
