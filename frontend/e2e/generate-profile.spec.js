// FRONTEND E2E — Playwright. UC2 Generate Learner Profile, browser-driven against the real UI.
//
// The Playwright counterpart to backend/tests/system/test_uc2_generate_profile.py (ST-2.1, ST-2.2).
// Both drive the same two branches through the same selectors, deliberately: two suites on one UI
// should break together when it changes, not one at a time. See ./README.md on tier overlap.
//
// ONLY TWO OF THE PLAN'S FOUR ST-2 BRANCHES EXIST. ST-2.3 and ST-2.4 were written against
// NoPatternError and ProfileGenerationError, both deleted along with ProfilingAlgorithm.analyse()
// and the learner_profiles table. UC2 is now a promotion — take the newest learner_sittings row and
// make it the learner's current marks — and a promotion derives nothing, so it cannot fail to find
// a pattern. NoScoresError (409) is the only error left. See backend/tests/README.md.
//
// Requires the app running (backend :8000, built frontend :4173) and TEST-project credentials.
import { expect, test } from "@playwright/test";
import { EMAIL, PASSWORD, openLearner } from "./_helpers.js";

// A learner WITH DIAL marks, and one with none. The same two the Selenium suite uses.
const SCORED_LEARNER_ID = process.env.TEST_LEARNER_ID;
const UNSCORED_LEARNER_ID = process.env.TEST_UNSCORED_LEARNER_ID;

test.skip(
  !EMAIL || !PASSWORD,
  "set TEST_THERAPIST_EMAIL and TEST_THERAPIST_PASSWORD (Supabase TEST project, never production)",
);

// `handleGenerateProfile` reports anything that is NOT a 409 through a bare alert()
// (LearnerDetailPage.jsx:121). Playwright auto-dismisses dialogs, which would turn a real backend
// failure into a silent pass, so capture the text and fail on it instead.
async function failOnAlert(page) {
  const seen = [];
  page.on("dialog", async (d) => { seen.push(d.message()); await d.dismiss(); });
  return () => expect(seen, `Generate Profile raised an alert: ${seen.join(" | ")}`).toHaveLength(0);
}

async function clickGenerateProfile(page) {
  const button = page.getByRole("button", { name: "Generate Profile" });
  await button.click();
  // The label flips to "Generating..." while the POST is in flight. Waiting for it to settle is
  // what proves the request COMPLETED — asserting sooner reads the pre-click page and passes for
  // a request that never returned.
  await expect(page.getByRole("button", { name: "Generating..." })).toBeHidden({ timeout: 30_000 });
}

test.describe("UC2 Generate Learner Profile", () => {
  test("therapist generates a profile and sees the visualisation", async ({ page }) => {
    test.skip(!SCORED_LEARNER_ID, "set TEST_LEARNER_ID to a learner with DIAL marks");

    const assertNoAlert = await failOnAlert(page);
    await openLearner(page, SCORED_LEARNER_ID);
    await clickGenerateProfile(page);
    assertNoAlert();

    // The profile IS the four DIAL marks, so the deficiency panel — rendered only when at least
    // one metric is assessed (LearnerDetailPage.jsx:176, 295) — is the visualisation's presence
    // check, and the "No DIAL marks" empty state is its negative half.
    await expect(page.getByRole("heading", { name: "Skill Deficiency Alerts" })).toBeVisible();
    await expect(page.getByText("No DIAL marks")).toBeHidden();

    // A successful promotion is not the no-scores branch: UC1's modal must not have opened.
    await expect(page.getByRole("heading", { name: "Upload Assessment Data" })).toBeHidden();
  });

  test("a learner with no scores opens the upload flow instead of erroring", async ({ page }) => {
    test.skip(!UNSCORED_LEARNER_ID, "set TEST_UNSCORED_LEARNER_ID to a learner with no DIAL marks");

    // THE DETERMINISTIC HALF, and the reason UC1 exists. With nothing to promote the service
    // raises NoScoresError -> 409, and the page turns that into UC1's upload modal rather than an
    // error: a learner with no scores is not something the therapist can retry out of, it is the
    // cue to upload one (LearnerDetailPage.jsx:117-119).
    //
    // 409 and not 404 is load-bearing. The learner exists and the request was well-formed; the
    // resource is just not in a state that can satisfy it yet. Collapsing the two would leave the
    // UI unable to tell "no such learner" from "no scores yet".
    const assertNoAlert = await failOnAlert(page);
    await openLearner(page, UNSCORED_LEARNER_ID);
    await clickGenerateProfile(page);
    assertNoAlert();

    await expect(page.getByRole("heading", { name: "Upload Assessment Data" })).toBeVisible();
    // No profile was generated, so the scored-state panel must not have appeared.
    await expect(page.getByRole("heading", { name: "Skill Deficiency Alerts" })).toBeHidden();
  });
});
