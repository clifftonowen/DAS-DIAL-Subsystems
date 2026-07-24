// FRONTEND E2E (placeholder) — Playwright.
//
// Browser-driven end-to-end flow through the real built UI, JS-side. This is the
// Playwright counterpart to the Python/Selenium `system` tests in
// backend/tests/system/ — see ../e2e/README.md for how the two relate.
//
// Status: skipped stub. Requires Playwright (not installed yet):
//   npm i -D @playwright/test && npx playwright install
//   npx playwright test          # from frontend/
//
// Jest never runs this file (it's outside src/ and not *.test.jsx), so the
// @playwright/test import below is harmless until you actually adopt Playwright.

import { test, expect } from "@playwright/test";

test.describe.skip("Login → dashboard", () => {
  test("therapist logs in and sees the dashboard shell", async ({ page }) => {
    await page.goto("/");                                   // baseURL from playwright.config
    await page.fill("#email", process.env.TEST_THERAPIST_EMAIL);
    await page.fill("#password", process.env.TEST_THERAPIST_PASSWORD);
    await page.getByRole("button", { name: "Log in" }).click();

    // Dashboard shell renders the profile menu + sidebar once signed in.
    await expect(page.getByRole("button", { name: /My Profile/ })).toBeVisible();
    await expect(page.getByText("Learners")).toBeVisible();
  });

  test("profile dropdown shows the email and signs out", async ({ page }) => {
    // TODO: log in (extract a helper), open "My Profile", assert the email,
    // click "Sign out", assert the #email field reappears.
  });
});
