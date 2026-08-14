// FRONTEND E2E — Playwright. UC8 Sign Up.
//
// The Playwright counterpart to backend/tests/system/test_uc8_sign_up.py (ST-8.1, ST-8.2). See
// ./README.md on tier overlap.
//
// THIS SPEC DRIVES THE REFUSAL BRANCH, NOT ACCOUNT CREATION, AND THAT IS THE POINT.
// A successful sign-up creates a real auth user plus a mirror row in the test project. The Selenium
// suite may do that because it has a `cleanup_emails` fixture that deletes what it created
// (system/conftest.py:43-71); Playwright has no Supabase teardown here, so mirroring ST-8.1 would
// leave one orphaned account behind on EVERY CI run — the exact accumulation backend/tests/README.md
// warns about. Sign-up also draws on the project's email quota, and a spent quota makes the Selenium
// suite skip, so a second suite creating accounts would degrade the one that covers this properly.
//
// What is left still covers UC8's alternative flow end to end through the browser: the duplicate
// refusal (3a -> "user already registered") and the client-side guard, neither of which writes
// anything. ST-8.1's create-path stays owned by the tier that can clean up after itself.
//
// Requires the app running (backend :8000, built frontend :4173) and TEST-project credentials.
import { expect, test } from "@playwright/test";
import { EMAIL, PASSWORD } from "./_helpers.js";

test.skip(
  !EMAIL || !PASSWORD,
  "set TEST_THERAPIST_EMAIL and TEST_THERAPIST_PASSWORD (Supabase TEST project, never production)",
);

/** Open AuthView in sign-up mode. It starts in login mode; the ghost button flips it. */
async function openSignUpForm(page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Need an account? Sign up" }).click();
  // The submit label flipping to "Sign up" is what proves the mode changed — #email and #password
  // are the same two fields in both modes, so their presence proves nothing.
  await expect(page.getByRole("button", { name: "Sign up", exact: true })).toBeVisible();
}

test.describe("UC8 Sign Up", () => {
  test("signing up with an address that already exists is refused", async ({ page }) => {
    await openSignUpForm(page);

    // The therapist account is guaranteed to exist — it is the one every other spec logs in with.
    // Reusing it is what makes this deterministic without creating anything.
    await page.fill("#email", EMAIL);
    await page.fill("#password", PASSWORD);
    await page.getByRole("button", { name: "Sign up", exact: true }).click();

    // Alternative flow 3a: the auth service refuses and the error reaches the user. AuthView
    // renders a failure as role="alert" and a success as role="status", so the ROLE is the
    // assertion — matching on message text would break on any wording change.
    const alert = page.getByRole("alert");
    await expect(alert).toBeVisible({ timeout: 20_000 });

    // Supabase surfaces a spent signup quota as an ordinary error too, which would pass the
    // assertion above for entirely the wrong reason. Skip on it rather than bank a false green —
    // the Python tiers do the same (system/_helpers.py::skip_if_rate_limited).
    const message = (await alert.textContent()) ?? "";
    test.skip(
      /rate limit/i.test(message),
      `Supabase rejected sign-up on quota, not as a duplicate: ${message}`,
    );

    // The refusal must leave the therapist SIGNED OUT. A failed sign-up that still rendered the
    // dashboard would be the security bug this asserts against.
    await expect(page.getByRole("button", { name: /My Profile/ })).toBeHidden();
    await expect(page.locator("#email")).toBeVisible();
  });

  test("the form will not submit without an email", async ({ page }) => {
    await openSignUpForm(page);

    // #email is a required type="email" input, so the browser blocks submission before any request
    // is made. No account is created and no network call goes out — the cheap half of "sign up is
    // unsuccessful" that costs the project nothing to assert.
    await page.fill("#password", "Passw0rd!");
    await page.getByRole("button", { name: "Sign up", exact: true }).click();

    await expect(page.locator("#email")).toBeVisible();
    await expect(page.getByRole("button", { name: /My Profile/ })).toBeHidden();
  });
});
