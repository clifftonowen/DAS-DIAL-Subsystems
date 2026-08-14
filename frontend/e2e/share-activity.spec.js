// FRONTEND E2E — Playwright. UC7 Share Learning Activity / Learning Profile.
//
// The Playwright counterpart to backend/tests/system/test_uc7_share.py (TC7a, TC7b), driving the
// same branches through the same selectors. See ./README.md on tier overlap.
//
// THE RECIPIENT IS ALWAYS parent@example.com. RFC 2606 reserves example.com and it is never
// deliverable, so a passing run cannot mail a real person — the same rule the backend tiers follow
// for throwaway addresses. Do not point this at a real inbox to "check it arrives".
//
// TC7c (render failure) is NOT driven here. It needs an activity whose PDF render is made to fail,
// which the Selenium suite reaches through TEST_UNRENDERABLE_ACTIVITY_ID; reproducing that setup in
// a second suite buys nothing, and a browser test cannot force the failure on its own.
//
// Requires the app running (backend :8000, built frontend :4173) and TEST-project credentials.
import { expect, test } from "@playwright/test";
import { EMAIL, PASSWORD, openLearner } from "./_helpers.js";

// NOT TEST_LEARNER_ID — that one is UC2's profile learner. This must be a learner who already HAS
// a generated activity, because "Share" is disabled until `latestActivity` exists
// (LearnerDetailPage.jsx:250).
const SHARE_LEARNER_ID = process.env.TEST_SHARE_LEARNER_ID;

test.skip(
  !EMAIL || !PASSWORD,
  "set TEST_THERAPIST_EMAIL and TEST_THERAPIST_PASSWORD (Supabase TEST project, never production)",
);

/** Open the share dialog on a learner that has an activity to share. */
async function openShareWindow(page) {
  await openLearner(page, SHARE_LEARNER_ID);
  await page.getByRole("button", { name: "Share" }).click();
  await expect(page.locator("#share-email")).toBeVisible();
}

test.describe("UC7 Share Learning Activity", () => {
  test.beforeEach(() => {
    test.skip(
      !SHARE_LEARNER_ID,
      "set TEST_SHARE_LEARNER_ID to a learner that already has a generated activity",
    );
  });

  test("therapist shares an activity and gets a confirmation", async ({ page }) => {
    await openShareWindow(page);

    await page.fill("#share-email", "parent@example.com");
    await page.getByRole("button", { name: "Send", exact: true }).click();

    // The operational flow's postcondition, as the therapist sees it. Rendering the PDF and
    // handing it to the email server can take a moment, so this gets a longer budget than the
    // pure-UI assertions around it.
    await expect(page.getByText("Activity sent to recipient")).toBeVisible({ timeout: 30_000 });

    // The form is REPLACED by the confirmation, so the same activity cannot be sent twice by
    // clicking again. That is a property of the flow, not a cosmetic detail.
    await expect(page.getByRole("button", { name: "Send", exact: true })).toBeHidden();
  });

  test("an invalid address is rejected and the therapist can re-enter it", async ({ page }) => {
    await openShareWindow(page);

    // Alternative flow 1a. The input is type="email", so a string with no "@" is caught before any
    // request is made — the point is that the flow REFUSES and stays usable, not where it refuses.
    await page.fill("#share-email", "not-an-email");
    await page.getByRole("button", { name: "Send", exact: true }).click();

    // Nothing was sent, and the form is still there to correct — the use case says "prompts
    // re-entry", so a dead end here would be the bug.
    await expect(page.getByText("Activity sent to recipient")).toBeHidden();
    await expect(page.locator("#share-email")).toBeEditable();
  });
});
