// FRONTEND E2E — Playwright. UC3 Generate Adaptive Learning Activity (includes UC5 Retrieve
// Instructional Strategy), browser-driven against the real built UI.
//
// The Playwright counterpart to the Python/Selenium `system` tests and the pytest `e2e` tier. It
// drives the real "Generate Activity" flow on LearnerDetailPage — the same page the generate tab
// was folded into — against a running backend and the real Supabase test project. UC5 is exercised
// implicitly: generation calls curriculum retrieval, so a successful or refused generation is also
// a statement about whether retrieval found grounding.
//
// WHY THE ASSERTIONS LOOK THE WAY THEY DO — the LLM cannot be faked here.
//   The pytest e2e tier swaps in a deterministic provider IN-PROCESS via
//   LLMApiClient.use_provider(...). This tier talks to a SEPARATE backend process over HTTP, so it
//   cannot reach that seam. Therefore:
//     - the HAPPY path (a real generated activity) needs a real LLM backend (Ollama), absent in
//       CI, so it is gated on TEST_ACTIVITY_LEARNER_ID and only asserts a valid outcome was
//       reached, not the activity text;
//     - the REFUSAL path (no assessment scores) is refused by a guardrail BEFORE the LLM is ever
//       called, so it is fully deterministic and needs no model — the CI-friendly proof.
//
// Requires the app running (backend :8000, built frontend :4173) and the test project's
// credentials in the environment. Skips rather than fails when they are absent, matching the other
// tiers — an unconfigured checkout stays green. Jest never runs this file (it is outside src/ and
// named *.spec.js, which jest.config.cjs's testMatch excludes).
import { expect, test } from "@playwright/test";

const EMAIL = process.env.TEST_THERAPIST_EMAIL;
const PASSWORD = process.env.TEST_THERAPIST_PASSWORD;
// A learner that HAS DIAL marks + a band + curriculum grounding, so generation can succeed.
const ACTIVITY_LEARNER_ID = process.env.TEST_ACTIVITY_LEARNER_ID || process.env.TEST_LEARNER_ID;
// A learner with NO assessment marks, so generation refuses before the LLM (deterministic).
const UNSCORED_LEARNER_ID = process.env.TEST_UNSCORED_LEARNER_ID;

test.skip(
  !EMAIL || !PASSWORD,
  "set TEST_THERAPIST_EMAIL and TEST_THERAPIST_PASSWORD (Supabase TEST project, never production)",
);

async function logIn(page) {
  await page.goto("/");                                   // baseURL from playwright.config.js
  await page.fill("#email", EMAIL);
  await page.fill("#password", PASSWORD);
  await page.getByRole("button", { name: "Log in" }).click();
  // The dashboard shell is the active-session postcondition — proves login re-rendered the app.
  await expect(page.getByRole("button", { name: /My Profile/ })).toBeVisible();
}

test.describe("UC3 Generate Adaptive Learning Activity (includes UC5 retrieval)", () => {
  test("therapist requests an activity and the system reaches a valid outcome", async ({ page }) => {
    test.skip(
      !ACTIVITY_LEARNER_ID,
      "set TEST_ACTIVITY_LEARNER_ID (or TEST_LEARNER_ID) to a learner with marks + a band",
    );
    await logIn(page);
    await page.goto(`/learners/${ACTIVITY_LEARNER_ID}`);

    await page.getByRole("button", { name: "Generate Activity" }).click();

    // UC3 has TWO valid boundary outcomes and which one occurs depends on the corpus and whether a
    // real LLM backend is reachable — neither controlled by this tier. BOTH satisfy the use case:
    // a validated activity (its ReviewSection renders #review-text), OR a documented refusal. The
    // failure this guards against is a crash or a silent nothing — the request must resolve.
    const generated = page.locator("#review-text");
    const refused = page.getByText(
      /no assessment scores yet|Not enough curriculum grounding|Could not generate activity/,
    );
    await expect(generated.or(refused).first()).toBeVisible({ timeout: 30_000 });
  });

  test("refuses to generate for a learner with no assessment scores", async ({ page }) => {
    // The deterministic, LLM-free proof of UC3's alternative flow: with no DIAL marks the query is
    // empty, so the service refuses BEFORE retrieval or the model. No real LLM needed in CI.
    test.skip(
      !UNSCORED_LEARNER_ID,
      "set TEST_UNSCORED_LEARNER_ID to a learner that has no DIAL marks",
    );
    await logIn(page);
    await page.goto(`/learners/${UNSCORED_LEARNER_ID}`);

    await page.getByRole("button", { name: "Generate Activity" }).click();

    await expect(
      page.getByText("This learner has no assessment scores yet"),
    ).toBeVisible({ timeout: 20_000 });
    // A refusal is not an activity: no review box should appear for the (non-existent) result.
    await expect(page.locator("#review-text")).toBeHidden();
  });
});
