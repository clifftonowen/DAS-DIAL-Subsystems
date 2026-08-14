// FRONTEND E2E — Playwright. UC9 View Learner List, browser-driven against the real UI.
//
// The Playwright counterpart to backend/tests/system/test_uc9_view_learners.py (ST-9.1 - ST-9.3),
// driving the same three branches through the same selectors. See ./README.md on tier overlap.
//
// The empty-caseload and DB-failure branches are NOT driven here, for the same reason the Selenium
// suite leaves them out: they need a zero-learner or unreachable database, which is exactly what
// the hermetic integration tier already covers (IT-9.2, IT-9.3). Faking them at this tier would
// mean faking the thing this tier exists to avoid faking.
//
// Requires the app running (backend :8000, built frontend :4173) and TEST-project credentials.
import { expect, test } from "@playwright/test";
import { EMAIL, PASSWORD, logIn } from "./_helpers.js";

// A seeded caseload learner (infra/seed.sql) — its card is the proof the grid rendered, not just
// the page shell. The second name is the one that must DISAPPEAR when the search narrows.
const SEEDED_PSEUDONYM = "Aisha Binti Rahman";
const OTHER_PSEUDONYM = "Benjamin Lim Wei";
const COHORT_NOTE = /includes the anonymised DAS research cohort/;

test.skip(
  !EMAIL || !PASSWORD,
  "set TEST_THERAPIST_EMAIL and TEST_THERAPIST_PASSWORD (Supabase TEST project, never production)",
);

/** Signed in and on the Learners tab, with the grid settled into a list or an empty state. */
async function openLearners(page) {
  await logIn(page);
  await page.goto("/learners");
  await expect(page.getByLabel("Search learners")).toBeVisible();

  // The grid resolves to a card or to the empty-caseload message; skeletons contain neither, so
  // this cannot read a mid-fetch state. An unseeded project skips rather than failing, matching
  // the Selenium suite — a checkout without seed data stays green instead of timing out.
  //
  // The regex names only the TWO pre-search empty states. A loose /No learners/ would also match
  // "No learners match …", which is the search-empty message — a different condition entirely, and
  // matching several of them at once makes `.isVisible()` throw on strict mode rather than answer.
  const card = page.getByText(SEEDED_PSEUDONYM);
  const empty = page.getByText(/No learners (found|on your caseload yet)/);
  await expect(card.or(empty).first()).toBeVisible({ timeout: 20_000 });
  test.skip(
    await empty.first().isVisible(),
    "test project has no seeded learners; seed infra/seed.sql",
  );
}

test.describe("UC9 View Learner List", () => {
  test("therapist opens Learners and their caseload renders", async ({ page }) => {
    await openLearners(page);

    // A real card from the seeded caseload, proving the grid rendered.
    await expect(page.getByText(SEEDED_PSEUDONYM)).toBeVisible();
    // The count line is the pager's "Showing 1-24 of N" — the total came back from the server,
    // so this is the list the DATABASE returned, not a client-side placeholder.
    await expect(page.getByText(/Showing/)).toBeVisible();
  });

  test("search filters the list server-side", async ({ page }) => {
    await openLearners(page);
    const search = page.getByLabel("Search learners");

    // A match narrows the grid: the matching card stays, a different one goes.
    await search.fill("Aisha");
    await expect(page.getByText(SEEDED_PSEUDONYM)).toBeVisible();
    await expect(page.getByText(OTHER_PSEUDONYM)).toBeHidden();

    // A query with no hits renders the search-empty state, not a bare grid — the two empty states
    // say different things ("no match" vs "no caseload") and the UI has to pick the right one.
    await search.fill("zzz");
    await expect(page.getByText(/No learners match/)).toBeVisible();
  });

  test("the caseload toggle widens the list to the cohort and back", async ({ page }) => {
    await openLearners(page);
    const toggle = page.getByRole("button", { name: "My caseload only" });

    // Off -> the anonymised research cohort joins the count line.
    await toggle.click();
    await expect(page.getByText(COHORT_NOTE)).toBeVisible();

    // Back on -> the note goes, returning to the caseload-only view. The round trip matters: a
    // toggle that only widens would look correct on a single click.
    await toggle.click();
    await expect(page.getByText(COHORT_NOTE)).toBeHidden();
  });
});
