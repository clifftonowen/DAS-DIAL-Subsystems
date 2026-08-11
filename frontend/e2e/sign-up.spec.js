// FRONTEND E2E — Playwright. UC8 Sign Up (PLACEHOLDER).
//
// Browser-driven counterpart to the Selenium `system` tests / pytest `e2e` tier. NOT YET
// IMPLEMENTED — scaffolded so the Playwright tier shows a slot per use case. Fill in the steps
// and remove `.skip` on the describe block to activate.
//
// NOTE: the Selenium suite already owns UC8 (backend/tests/system/test_uc8_sign_up.py). Use a
// throwaway @example.com address per run and clean it up, mirroring the Selenium suite's fixtures.
//
// Requires the app running (backend :8000, built frontend :4173) and TEST-project credentials.
import { expect, test } from "@playwright/test";

test.describe.skip("UC8 Sign Up", () => {
  test("therapist signs up with a new email and password", async ({ page }) => {
    // TODO:
    // 1. page.goto("/")
    // 2. click "Need an account? Sign up"
    // 3. fill #email (unique @example.com), #password
    // 4. click "Sign up"
    // 5. expect the outcome — dashboard if confirmation OFF, or the "Account created" notice if ON
    // 6. clean up the created auth user in teardown
    expect(true).toBeTruthy();
  });
});
