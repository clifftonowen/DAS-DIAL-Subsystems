// UNIT (frontend) — UC1 Upload Assessment Data.
//
// The api module is mocked, so what this asserts is the view's contract with the backend: which
// calls it makes, and exactly what it puts in the confirm payload. The wire itself is the
// integration tier's job (UploadView.uc1.integration.test.jsx).
//
// PM3's Week 11 row lists UC1 under Jest + RTL; none existed before this file.
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import * as api from "../../lib/api";
import UploadView from "../UploadView";

// A factory, not an automock: lib/api imports lib/supabase, which calls createClient() at module
// scope and throws without VITE_SUPABASE_URL.
jest.mock("../../lib/api", () => ({
  previewAssessment: jest.fn(),
  confirmAssessment: jest.fn(),
  getAssessmentMetrics: jest.fn(),
  getAssessmentSemesters: jest.fn(),
}));

const LEARNER = { id: "l1", pseudonym: "Aisha Binti Rahman", band: "A2" };

// The ceilings the backend serves. NOT hardcoded in the component any more — it reads them from
// GET /assessments/metrics so the form and the confirm validator enforce the same numbers.
const METRICS = [
  { key: "writing_score", label: "Writing", max: 30 },
  { key: "phonics_score", label: "Phonics", max: 50 },
  { key: "word_reading_score", label: "Word Reading", max: 10 },
  { key: "word_spelling_score", label: "Word Spelling", max: 10 },
];

const PREVIEW = {
  learner_id: "l1",
  assessment_date: "2026-07-24",
  tasks: [{ name: "Phoneme Segmentation", score: 7, max_score: 10 }],
  strengths: ["blending"],
  weaknesses: ["segmentation"],
  confidence_score: 0.6,
  risk_score: 0.4,
  task_results: { "Phoneme Segmentation": { score: 7, max_score: 10 } },
  notes: "",
  writing_score: null,
  phonics_score: null,
  word_reading_score: null,
  word_spelling_score: null,
};

beforeEach(() => {
  jest.clearAllMocks();
  api.getAssessmentMetrics.mockResolvedValue(METRICS);
  api.getAssessmentSemesters.mockResolvedValue(["2026 Sem 2", "2026 Sem 1", "2025 Sem 2"]);
  api.previewAssessment.mockResolvedValue(PREVIEW);
  api.confirmAssessment.mockResolvedValue({ status: "success" });
});

const renderView = (props = {}) =>
  render(<UploadView learners={[LEARNER]} onClose={() => {}} onSaved={() => {}} {...props} />);

const aFile = () =>
  new File(["report"], "report.docx", { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });

/** Fill the form and reach the preview card. */
async function reachPreview(user, { phonics = "30", writing = null } = {}) {
  await screen.findByRole("option", { name: "2026 Sem 2" });   // metadata has loaded
  if (phonics !== null) await user.type(screen.getByLabelText("Phonics"), phonics);
  if (writing !== null) await user.type(screen.getByLabelText("Writing"), writing);
  await user.upload(screen.getByLabelText(/Assessment file/), aFile());
  await user.click(screen.getByRole("button", { name: "Parse report" }));
  return screen.findByRole("button", { name: "Confirm & save" });
}

// ── the rubric comes from the backend ─────────────────────────────────────────
test("the valid range shown for each metric is the one the API serves", async () => {
  renderView();

  expect(await screen.findByText(/Valid range: 0–50/)).toBeInTheDocument();   // phonics
  expect(screen.getByText(/Valid range: 0–30/)).toBeInTheDocument();          // writing
  expect(screen.getAllByText(/Valid range: 0–10/)).toHaveLength(2);
  expect(api.getAssessmentMetrics).toHaveBeenCalledTimes(1);
});

test("a metric above its ceiling is rejected before any request is made", async () => {
  const user = userEvent.setup();
  renderView();
  await screen.findByText(/Valid range: 0–50/);

  await user.type(screen.getByLabelText("Phonics"), "51");

  expect(await screen.findByText("Must be between 0 and 50")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Parse report" })).toBeDisabled();
  expect(api.previewAssessment).not.toHaveBeenCalled();
});

// ── not assessed is not zero ──────────────────────────────────────────────────
test("a blank metric is sent as null, not as 0", async () => {
  const user = userEvent.setup();
  renderView();
  await reachPreview(user, { phonics: "30" });      // writing left untouched

  await user.click(screen.getByRole("button", { name: "Confirm & save" }));

  // THE ASSERTION THIS FILE EXISTS FOR. Writing is never administered to band A, so an untouched
  // field means "not assessed". Number("") is 0, and a 0 here would rank as the learner's
  // weakest skill and steer UC3 into generating a writing activity for a paper never sat.
  await waitFor(() => expect(api.confirmAssessment).toHaveBeenCalled());
  const payload = api.confirmAssessment.mock.calls[0][0];
  expect(payload.writing_score).toBeNull();
  expect(payload.phonics_score).toBe(30);
});

test("a blank metric is valid input, not an error", async () => {
  renderView();
  await screen.findByText(/Valid range: 0–50/);

  // Every field starts empty and the form is submittable — "not assessed" has to be expressible.
  expect(screen.queryByText("Enter a number")).not.toBeInTheDocument();
  expect(screen.getByLabelText("Writing")).toHaveValue("");
});

test("a genuine zero is kept as zero", async () => {
  const user = userEvent.setup();
  renderView();
  await reachPreview(user, { phonics: "0" });

  await user.click(screen.getByRole("button", { name: "Confirm & save" }));

  // The counterpart: a learner who scored 0 has a real mark. Conflating absence and zero in
  // either direction is the bug.
  await waitFor(() => expect(api.confirmAssessment).toHaveBeenCalled());
  expect(api.confirmAssessment.mock.calls[0][0].phonics_score).toBe(0);
});

test("the preview card distinguishes an unassessed paper from a zero", async () => {
  const user = userEvent.setup();
  renderView();
  await reachPreview(user, { phonics: "0" });

  // Phonics 0 and the three untouched metrics must not read the same on the confirmation card:
  // the therapist should see the distinction the database is about to record.
  expect(screen.getAllByText("Not assessed")).toHaveLength(3);
  expect(screen.getByText("0")).toBeInTheDocument();
});

// ── semester and band ─────────────────────────────────────────────────────────
test("the semester options come from the API, newest first", async () => {
  renderView();

  const select = await screen.findByLabelText("Semester");
  await waitFor(() =>
    expect([...select.options].map((o) => o.value))
      .toEqual(["2026 Sem 2", "2026 Sem 1", "2025 Sem 2"]));
  expect(select).toHaveValue("2026 Sem 2");        // defaults to the newest
});

test("the semester and band are sent with the marks", async () => {
  const user = userEvent.setup();
  renderView();
  await reachPreview(user);

  await user.click(screen.getByRole("button", { name: "Confirm & save" }));

  await waitFor(() => expect(api.confirmAssessment).toHaveBeenCalled());
  const payload = api.confirmAssessment.mock.calls[0][0];
  // Both belong to the SITTING, not just the record: semester is half its natural key, and the
  // band is the paper the marks were earned against.
  expect(payload.semester).toBe("2026 Sem 2");
  expect(payload.band).toBe("A2");
  expect(payload.band_group).toBe("A");            // derived from the band's first letter
});

test("the band is prefilled from the learner but stays editable", async () => {
  const user = userEvent.setup();
  renderView();

  const band = await screen.findByLabelText("Band");
  expect(band).toHaveValue("A2");                  // the learner's current band

  // A learner's band changes between sittings, so this records the paper actually sat.
  await user.selectOptions(band, "A3");
  expect(band).toHaveValue("A3");
});

test("a learner with no band on record leaves it unset rather than guessing", async () => {
  renderView({ learners: [{ id: "l2", pseudonym: "Ben", band: null }] });

  expect(await screen.findByLabelText("Band")).toHaveValue("");
});

// ── the learner list can arrive after the modal opens ─────────────────────────
test("a learner list that arrives after mount is actually usable", async () => {
  // THE BUG THIS PINS. LearnersPage mounts this modal the instant the button is clicked, which
  // can be before its own fetch resolves. `useState(learners[0]?.id)` runs once, so landing in
  // that window left learnerId "" with nothing to correct it — and handleParse's `!learnerId`
  // guard then made "Parse report" a button that did nothing at all, silently, forever.
  // Three of the four ST-1.x browser tests died on exactly this and reported only a timeout.
  //
  // ASSERT THE REQUEST, NOT THE DROPDOWN. A <select> whose React value is "" matches no option,
  // so the browser falls back to displaying the first one — the control READS "Aisha Binti
  // Rahman" while the state behind it is empty. An assertion on the DOM value passes with the
  // bug fully present (verified: removing the effect does not fail it). Only the call proves it.
  const user = userEvent.setup();
  const { rerender } = render(
    <UploadView learners={[]} onClose={() => {}} onSaved={() => {}} />
  );
  await screen.findByText(/Valid range: 0–50/);

  rerender(<UploadView learners={[LEARNER]} onClose={() => {}} onSaved={() => {}} />);
  await user.upload(screen.getByLabelText(/Assessment file/), aFile());
  await user.click(screen.getByRole("button", { name: "Parse report" }));

  await waitFor(() =>
    expect(api.previewAssessment).toHaveBeenCalledWith("l1", expect.any(File)));
});

test("a re-fetch does not yank the therapist's chosen learner away", async () => {
  const user = userEvent.setup();
  const OTHER = { id: "l9", pseudonym: "Ben Tan", band: "B1" };
  const { rerender } = render(
    <UploadView learners={[LEARNER, OTHER]} onClose={() => {}} onSaved={() => {}} />
  );

  await user.selectOptions(screen.getByLabelText("Learner"), "l9");

  // Searching or paging re-fetches and hands down a new array. The choice must survive it, or
  // the fix above would trade a silent no-op for a silent wrong learner — the worse bug, since
  // it writes an assessment to somebody else.
  rerender(<UploadView learners={[OTHER, LEARNER]} onClose={() => {}} onSaved={() => {}} />);

  await waitFor(() => expect(screen.getByLabelText("Learner")).toHaveValue("l9"));
});

test("parsing with no learner selected says so instead of doing nothing", async () => {
  const user = userEvent.setup();
  renderView({ learners: [] });
  await screen.findByText(/Valid range: 0–50/);

  await user.upload(screen.getByLabelText(/Assessment file/), aFile());
  await user.click(screen.getByRole("button", { name: "Parse report" }));

  // The button enables on a file alone, so it is reachable in this state. A click that returns
  // silently is indistinguishable from a broken app.
  expect(await screen.findByRole("alert")).toHaveTextContent("Pick a learner");
  expect(api.previewAssessment).not.toHaveBeenCalled();
});

// ── the three steps and their failures ────────────────────────────────────────
test("a parse failure is shown and the preview is never reached", async () => {
  const user = userEvent.setup();
  api.previewAssessment.mockRejectedValue(new Error("No extractable text found"));
  renderView();
  await screen.findByText(/Valid range: 0–50/);

  await user.upload(screen.getByLabelText(/Assessment file/), aFile());
  await user.click(screen.getByRole("button", { name: "Parse report" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("No extractable text found");
  expect(screen.queryByRole("button", { name: "Confirm & save" })).not.toBeInTheDocument();
  expect(api.confirmAssessment).not.toHaveBeenCalled();
});

test("a storage failure on confirm is shown and the step does not advance", async () => {
  const user = userEvent.setup();
  api.confirmAssessment.mockRejectedValue(new Error("Data could not be saved"));
  renderView();
  await reachPreview(user);

  await user.click(screen.getByRole("button", { name: "Confirm & save" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Data could not be saved");
  expect(screen.queryByText("Data saved successfully.")).not.toBeInTheDocument();
});

test("a successful confirm reports success and notifies the caller", async () => {
  const user = userEvent.setup();
  const onSaved = jest.fn();
  renderView({ onSaved });
  await reachPreview(user);

  await user.click(screen.getByRole("button", { name: "Confirm & save" }));

  expect(await screen.findByText("Data saved successfully.")).toBeInTheDocument();
  expect(onSaved).toHaveBeenCalled();              // the page behind reloads its data
});

test("the form still works when the metadata request fails", async () => {
  api.getAssessmentMetrics.mockRejectedValue(new Error("offline"));
  api.getAssessmentSemesters.mockRejectedValue(new Error("offline"));
  renderView();

  // Degraded, not broken: the inputs render unbounded and the API remains the authority on what
  // a valid mark is. Losing the rubric should not cost the therapist the upload.
  expect(await screen.findByLabelText("Assessment file (PDF or DOCX)")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Parse report" })).toBeInTheDocument();
});
