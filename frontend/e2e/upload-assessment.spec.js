// FRONTEND E2E — Playwright. UC1 Upload Assessment Data (PLACEHOLDER).
//
// Browser-driven counterpart to the Selenium `system` tests / pytest `e2e` tier. NOT YET
// IMPLEMENTED — scaffolded so the Playwright tier shows a slot per use case. Fill in the steps
// and remove `.skip` on the describe block to activate.
//
// Requires the app running (backend :8000, built frontend :4173) and TEST-project credentials.
import { expect, test } from "@playwright/test";

const EMAIL = process.env.TEST_THERAPIST_EMAIL;
const PASSWORD = process.env.TEST_THERAPIST_PASSWORD;

test.describe.skip("UC1 Upload Assessment Data", () => {
  test("therapist uploads a valid assessment file and it is stored", async ({ page }) => {
    // TODO:
    // 1. logIn(page)  — #email / #password / "Log in" button
    // 2. navigate to the learner / upload UI (e.g. /learners/${TEST_LEARNER_ID})
    // 3. set the file input to a valid assessment fixture (page.setInputFiles(...))
    // 4. click Upload
    // 5. expect a success message, and the assessment/preview to render
    expect(EMAIL && PASSWORD).toBeTruthy();
  });
});
