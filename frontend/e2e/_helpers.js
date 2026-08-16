// Shared helpers for the Playwright browser-e2e tier (not a spec file — Playwright's testMatch
// only picks up *.spec.js, so this is never collected as a test).
//
// The Python counterpart is backend/tests/system/_helpers.py, and the selectors are deliberately
// the same ones: #email / #password / "Log in" from AuthView.jsx, and the "My Profile" trigger
// from the authenticated shell. Two suites driving the same UI should break together when a
// selector changes, not one at a time.
//
// WHY login.spec.js DOES NOT IMPORT logIn FROM HERE. It is the spec that tests logging in. A test
// for login that authenticates through a shared login helper proves the helper works, not the
// feature — so it keeps its own inline copy on purpose. Every OTHER spec treats login as setup and
// should import this one.
import { expect } from "@playwright/test";

export const EMAIL = process.env.TEST_THERAPIST_EMAIL;
export const PASSWORD = process.env.TEST_THERAPIST_PASSWORD;

/** Drive the real login form and wait for the authenticated shell. */
export async function logIn(page) {
  await page.goto("/");                                   // baseURL from playwright.config.js
  await page.fill("#email", EMAIL);
  await page.fill("#password", PASSWORD);
  await page.getByRole("button", { name: "Log in" }).click();
  // The dashboard shell is the active-session postcondition — it proves the session was
  // established and main.jsx re-rendered, not merely that a token came back.
  await expect(page.getByRole("button", { name: /My Profile/ })).toBeVisible();
}

/** Log in and open one learner's detail page, where UC2/UC3/UC4/UC7 all live. */
export async function openLearner(page, learnerId) {
  await logIn(page);
  // Direct route: the session lives in localStorage, so BrowserRouter serves /learners/<id>
  // without going through the list first.
  await page.goto(`/learners/${learnerId}`);
}
