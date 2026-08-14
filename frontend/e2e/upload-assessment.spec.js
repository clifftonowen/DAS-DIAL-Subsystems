// FRONTEND E2E — Playwright. UC1 Upload Assessment Data.
//
// The Playwright counterpart to backend/tests/system/test_uc1_upload_assessment.py (ST-1.1 - 1.3).
// See ./README.md on tier overlap.
//
// THIS SPEC STOPS AT THE PREVIEW AND NEVER CLICKS "Confirm & save". That is deliberate, and it is
// the one place this tier must NOT mirror the Selenium suite. Confirming writes a learner_sittings
// row, and the form only offers LOOKAHEAD semesters (on-record plus the next two), so a saved row
// is permanently that learner's NEWEST sitting. UC2 promotes the newest sitting — so an
// unreclaimed row here would silently change what UC2's tests read, in both suites, forever after.
// The Selenium suite can confirm because it has an `uploaded_sitting` fixture that deletes the row
// it created (test_uc1_upload_assessment.py:86-110). Playwright has no Supabase teardown here, so
// it covers steps 1-3 of the operational flow (prompt, fill, parse) and leaves step 4 (store) to
// the tier that can clean up after itself.
//
// Requires the app running (backend :8000, built frontend :4173) and TEST-project credentials.
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { EMAIL, PASSWORD, logIn } from "./_helpers.js";

test.skip(
  !EMAIL || !PASSWORD,
  "set TEST_THERAPIST_EMAIL and TEST_THERAPIST_PASSWORD (Supabase TEST project, never production)",
);

// A REAL .docx ON DISK, not a buffer built here. `validate_format` checks the EXTENSION and accepts
// only .pdf/.docx (assessment_parser.py:38), and `_extract_text` then opens a .docx as a zip
// archive — so a text buffer named report.txt is rejected before parsing, and one named report.docx
// blows up inside it. Neither reaches the preview this test is about. The fixture is a genuine
// python-docx document holding the same paragraphs the Selenium suite builds at runtime; it is
// committed rather than generated because Node has no zip writer in its standard library.
const REPORT_DOCX = fileURLToPath(new URL("./fixtures/report.docx", import.meta.url));

/**
 * From the learners list to the upload modal, with its SERVED METADATA already in.
 *
 * The waits here are load-bearing, and they guard the same trap the Selenium suite documents at
 * length. The modal renders instantly, but the rubric and the semester list arrive from two API
 * calls behind one Promise.all. Until both land the metric inputs do not exist, the semester
 * select holds only a "Loading…" placeholder, and handleSubmit bails on its `!semester` guard —
 * so a click on "Parse report" silently does nothing and the failure surfaces several steps from
 * its cause.
 *
 * GET /assessments/semesters used to be the slow half of that Promise.all — ~23 paged round trips
 * to deduplicate one column — until it moved onto the `distinct_semesters()` Postgres function
 * (infra/migrations/2026-08-14_distinct_semesters.sql). It is one request now, so these waits
 * should resolve almost immediately; they are kept because "almost" is not "always", and because
 * a project that has not run the migration still takes the old paged path.
 */
async function openUploadForm(page) {
  await logIn(page);
  await page.goto("/learners");
  await page.getByRole("button", { name: "Upload Assessment" }).click();

  await expect(page.locator("#upload-file")).toBeVisible();

  // BOTH WAITS BELOW ARE POSITIVE EXISTENCE CHECKS, ON PURPOSE. The obvious translation of the
  // Selenium version is a negated assertion on the rubric hint ("no longer says 0–…"), and it is
  // silently useless here: before the rubric lands the metric inputs are not rendered AT ALL, and
  // `expect(missing).not.toContainText(...)` resolves immediately rather than waiting. The wait
  // would pass instantly and the failure would surface two steps later, at selectOption.
  //
  // The metric field existing proves `metricSpecs` populated, which is the rubric call.
  await expect(page.locator("#upload-phonics_score")).toBeVisible({ timeout: 20_000 });
  // A semester option with a real value proves the semesters call: while it is in flight the only
  // child is `<option value="">Loading…</option>` (UploadView.jsx:216), and handleSubmit bails on
  // its `!semester` guard, so "Parse report" would silently do nothing.
  await expect(page.locator("#upload-semester option[value]:not([value=''])").first())
    .toBeAttached({ timeout: 20_000 });

  // The learner list is a third async source, belonging to LearnersPage rather than the modal.
  // Its options must exist before anything is submitted or `learnerId` is empty and parse refuses.
  await expect(page.locator("#upload-learner option").first()).toBeAttached();
}

test.describe("UC1 Upload Assessment Data", () => {
  test("a valid report is parsed into a preview the therapist can confirm", async ({ page }) => {
    await openUploadForm(page);

    // Take whichever semester the form offers first — the endpoint guarantees it is a lookahead
    // one. Injecting a fixed far-future option cannot work here: the select is a CONTROLLED
    // component whose children come from the fetched array, so React strips a foreign option on
    // the next reconciliation and takes the selection with it.
    const semester = await page
      .locator("#upload-semester option[value]:not([value=''])")
      .first()
      .getAttribute("value");
    await page.selectOption("#upload-semester", semester);

    await page.fill("#upload-phonics_score", "30");
    // Writing is left BLANK on purpose: band A never sits that paper, and blank has to mean "not
    // assessed" rather than a mark of zero — a zero would rank as the learner's weakest skill and
    // steer UC3 at a paper they never took.
    await page.setInputFiles("#upload-file", REPORT_DOCX);

    await page.getByRole("button", { name: "Parse report" }).click();

    // The preview card echoes what WOULD be stored, including the distinction blank carries. The
    // "Confirm & save" button being present is the proof the parse succeeded; clicking it is what
    // this tier deliberately does not do (see the file header).
    await expect(page.getByRole("button", { name: "Confirm & save" })).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByText("Not assessed")).toBeVisible();
  });

  test("a corrupted file is rejected with an error and nothing is stored", async ({ page }) => {
    await openUploadForm(page);

    const semester = await page
      .locator("#upload-semester option[value]:not([value=''])")
      .first()
      .getAttribute("value");
    await page.selectOption("#upload-semester", semester);
    await page.fill("#upload-phonics_score", "30");

    // Alternative flow 2a/3a. A .docx EXTENSION over bytes that are not a document gets past
    // validate_format, which checks the extension only, and fails in extraction — the "corrupted
    // file" branch rather than the "wrong file type" one.
    await page.setInputFiles("#upload-file", {
      name: "corrupt.docx",
      mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      buffer: Buffer.from("this is not a docx"),
    });

    await page.getByRole("button", { name: "Parse report" }).click();

    await expect(page.locator("#upload-error")).toBeVisible({ timeout: 20_000 });
    // The refusal has to be a dead end for the SAVE, not just a red box: reaching the preview on
    // a file that could not be parsed is the failure this guards against.
    await expect(page.getByRole("button", { name: "Confirm & save" })).toBeHidden();
  });
});
