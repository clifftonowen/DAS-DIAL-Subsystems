// FRONTEND E2E — Playwright. UC7 Share Learning Activity / Learning Profile (PLACEHOLDER).
//
// Browser-driven counterpart to the Selenium `system` tests / pytest `e2e` tier. NOT YET
// IMPLEMENTED — scaffolded so the Playwright tier shows a slot per use case. Fill in the steps
// and remove `.skip` on the describe block to activate.
//
// NOTE: the Selenium suite already owns UC7 (backend/tests/system/test_uc7_share.py). Only add
// here a flow it does not already drive, per e2e/README.md's tier-overlap policy.
//
// Requires the app running (backend :8000, built frontend :4173) and TEST-project credentials.
import { expect, test } from "@playwright/test";

const EMAIL = process.env.TEST_THERAPIST_EMAIL;
const PASSWORD = process.env.TEST_THERAPIST_PASSWORD;

test.describe.skip("UC7 Share Learning Activity", () => {
  test("therapist shares an activity to a recipient email", async ({ page }) => {
    // TODO (learner must have a generated activity so "Share" is enabled):
    // 1. logIn(page)
    // 2. navigate to /learners/${TEST_SHARE_LEARNER_ID}
    // 3. click "Share", fill  cvv#share-email with a recipient
    // 4. click Send
    // 5. expect a confirmation ("Activity sent...") — mock/point the email server at a test sink
    expect(EMAIL && PASSWORD).toBeTruthy();
  });
});
