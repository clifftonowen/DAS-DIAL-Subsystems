// FRONTEND E2E — Playwright. UC4 Review Learning Activity.
//
// The Playwright counterpart to backend/tests/system/test_uc4_review.py, driving the same flow
// through the same selectors. See ./README.md on tier overlap.
//
// THIS SPEC WRITES. A submitted review is a real row in the test project, and unlike UC1's
// lookahead sitting it is additive — it does not change what any other suite reads, so it is left
// in place rather than torn down. The text is stamped with a run id so a human reading the table
// later can tell an automated review from a therapist's.
//
// Requires the app running (backend :8000, built frontend :4173) and TEST-project credentials.
import { expect, test } from "@playwright/test";
import { EMAIL, PASSWORD, openLearner } from "./_helpers.js";

// The review box only renders under an activity (LearnerDetailPage.jsx:377), so this needs the
// same learner UC7 uses: one that already HAS a generated activity.
const REVIEW_LEARNER_ID = process.env.TEST_SHARE_LEARNER_ID || process.env.TEST_LEARNER_ID;

test.skip(
  !EMAIL || !PASSWORD,
  "set TEST_THERAPIST_EMAIL and TEST_THERAPIST_PASSWORD (Supabase TEST project, never production)",
);

test.describe("UC4 Review Learning Activity", () => {
  test("a submitted review survives a page reload", async ({ page }) => {
    test.skip(
      !REVIEW_LEARNER_ID,
      "set TEST_SHARE_LEARNER_ID (or TEST_LEARNER_ID) to a learner with a generated activity",
    );

    await openLearner(page, REVIEW_LEARNER_ID);

    const reviewBox = page.locator("#review-text");
    // Absent means the learner has no activity to review — a setup gap, not a UC4 failure, so say
    // which it is rather than failing on a missing selector.
    await expect(
      reviewBox,
      `learner ${REVIEW_LEARNER_ID} has no generated activity, so there is nothing to review`,
    ).toBeVisible({ timeout: 20_000 });

    const text = `Playwright e2e review ${Date.now()}`;
    await reviewBox.fill(text);
    // "Upload" is UC4's comment-only submit; the neighbouring buttons record an approval verdict,
    // which is a different (and irreversible) decision. The use case is "leaves a review".
    await page.getByRole("button", { name: "Upload", exact: true }).click();

    await expect(page.getByText(text)).toBeVisible({ timeout: 20_000 });

    // THE RELOAD IS THE POINT. Without it this passes on local React state alone, which is exactly
    // the bug the use case's postcondition ("the review is stored and displayed") guards against.
    // After a reload the text can only be on screen because it came back from the database.
    await page.reload();
    await expect(page.getByText(text)).toBeVisible({ timeout: 20_000 });
  });

  test("an empty review cannot be submitted", async ({ page }) => {
    test.skip(!REVIEW_LEARNER_ID, "set TEST_SHARE_LEARNER_ID (or TEST_LEARNER_ID)");

    await openLearner(page, REVIEW_LEARNER_ID);
    await expect(page.locator("#review-text")).toBeVisible({ timeout: 20_000 });

    // The submit is disabled until there is non-whitespace text (ReviewSection.jsx:141), so a
    // blank review never reaches the service. Whitespace only, not empty, because trimming is the
    // half that is easy to get wrong.
    await page.locator("#review-text").fill("   ");
    await expect(page.getByRole("button", { name: "Upload", exact: true })).toBeDisabled();
  });
});
