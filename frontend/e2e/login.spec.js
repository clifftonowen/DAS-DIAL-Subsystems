// FRONTEND E2E — Playwright. UC6 Log In, browser-driven against the real built UI.
//
// The Playwright counterpart to the Python/Selenium `system` tests in backend/tests/system/ —
// see ./README.md for how the two relate. Both drive a real browser against a running app and a
// real Supabase test project, so this file deliberately sticks to the login boundary rather than
// re-driving flows the Selenium suite already owns with their plan IDs.
//
// Requires the app to be running (backend :8000, built frontend :4173) and the test project's
// credentials in the environment. Skips rather than fails when they are absent, matching the
// backend tiers' behaviour — an unconfigured checkout stays green.
//
// Jest never runs this file: it is outside src/ and named *.spec.js, which the testMatch glob
// in jest.config.cjs excludes.
import { expect, test } from "@playwright/test";

const EMAIL = process.env.TEST_THERAPIST_EMAIL;
const PASSWORD = process.env.TEST_THERAPIST_PASSWORD;

test.skip(
  !EMAIL || !PASSWORD,
  "set TEST_THERAPIST_EMAIL and TEST_THERAPIST_PASSWORD (Supabase TEST project, never production)",
);

async function logIn(page, password = PASSWORD) {
  await page.goto("/");                                   // baseURL from playwright.config.js
  await page.fill("#email", EMAIL);
  await page.fill("#password", password);
  await page.getByRole("button", { name: "Log in" }).click();
}

test.describe("UC6 Log In", () => {
  test("therapist logs in and sees the dashboard shell", async ({ page }) => {
    await logIn(page);

    // The dashboard shell is the postcondition: an ACTIVE SESSION, not just a token. main.jsx
    // swaps AuthView for Dashboard on onAuthStateChange, so these two elements existing is the
    // observable proof that the session was established and the app re-rendered behind it.
    await expect(page.getByRole("button", { name: /My Profile/ })).toBeVisible();
    await expect(page.getByRole("link", { name: "Learners" })).toBeVisible();
  });

  test("a wrong password leaves the therapist signed out", async ({ page }) => {
    await logIn(page, "definitely-wrong");

    // The error has to reach the user: AuthController's 401 detail travels through api.js into
    // the alert. And the negative half matters as much — a failed login that still rendered the
    // dashboard would be the security bug this asserts against.
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.getByRole("button", { name: /My Profile/ })).toBeHidden();
    await expect(page.locator("#email")).toBeVisible();
  });

  test("the profile menu shows the signed-in email and signs out", async ({ page }) => {
    await logIn(page);
    await page.getByRole("button", { name: /My Profile/ }).click();

    await expect(page.getByText(EMAIL)).toBeVisible();
    await page.getByRole("button", { name: /Sign out/ }).click();

    // Back to the login form — the session is gone, not merely hidden.
    await expect(page.locator("#email")).toBeVisible();
    await expect(page.getByRole("button", { name: /My Profile/ })).toBeHidden();
  });
});
