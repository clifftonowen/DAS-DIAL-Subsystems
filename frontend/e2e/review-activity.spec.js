// FRONTEND E2E — Playwright. UC4 Review Learning Activity (PLACEHOLDER).
//
// Browser-driven counterpart to the Selenium `system` tests / pytest `e2e` tier. NOT YET
// IMPLEMENTED — scaffolded so the Playwright tier shows a slot per use case. Fill in the steps
// and remove `.skip` on the describe block to activate.
//
// NOTE: the Selenium suite already owns UC4 (backend/tests/system/test_uc4_review.py). Only add
// here a flow it does not already drive, per e2e/README.md's tier-overlap policy.
//
// Requires the app running (backend :8000, built frontend :4173) and TEST-project credentials.
import { expect, test } from "@playwright/test";

const EMAIL = process.env.TEST_THERAPIST_EMAIL;
const PASSWORD = process.env.TEST_THERAPIST_PASSWORD;

test.describe.skip("UC4 Review Learning Activity", () => {
  test("therapist submits a review and it survives a refresh", async ({ page }) => {
    // TODO (learner must have a generated activity so #review-text renders):
    // 1. logIn(page)
    // 2. navigate to /learners/${TEST_LEARNER_ID}
    // 3. fill #review-text, click "Upload"
    // 4. expect the review text to appear
    // 5. page.reload(); expect the review to still be present (from the DB, not local state)
    expect(EMAIL && PASSWORD).toBeTruthy();
  });
});
