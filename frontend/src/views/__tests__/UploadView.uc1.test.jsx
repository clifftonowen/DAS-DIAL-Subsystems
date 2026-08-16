// UNIT (frontend) — UC1 Upload Assessment Data: UploadView.jsx.
//
// The api module is mocked wholesale, so what this asserts is the component's own contract:
// metric-range validation blocks the parse step, the preview screen echoes back what was typed
// on step 1 (not anything derived from the parsed response), and confirm sends the metrics
// alongside the parsed fields and the sitting's identity.
//
// A factory, not an automock: lib/api imports lib/supabase, which calls createClient() at
// module scope and throws without VITE_SUPABASE_URL — same reason every other view unit test
// mocks "../../lib/api" as a self-contained factory (see LearnersPage.test.jsx).
//
// ALL FOUR functions UploadView imports have to be in the factory. Leave getAssessmentMetrics
// or getAssessmentSemesters out and they arrive as undefined, the Promise.all in the mount
// effect throws, and the component's own catch swallows it — so the form renders with raw
// metric keys for labels, no ceilings, and an empty semester list that blocks Parse report.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import UploadView from "../UploadView";
import {
  previewAssessment, confirmAssessment, getAssessmentMetrics, getAssessmentSemesters,
} from "../../lib/api";

jest.mock("../../lib/api", () => ({
  previewAssessment: jest.fn(),
  confirmAssessment: jest.fn(),
  getAssessmentMetrics: jest.fn(),
  getAssessmentSemesters: jest.fn(),
}));

// The ceilings the backend serves from GET /assessments/metrics. NOT hardcoded in the component
// any more, so the form and the confirm validator cannot disagree about what a valid mark is.
const METRICS = [
  { key: "writing_score", label: "Writing", max: 30 },
  { key: "phonics_score", label: "Phonics", max: 50 },
  { key: "word_reading_score", label: "Word Reading", max: 10 },
  { key: "word_spelling_score", label: "Word Spelling", max: 10 },
];

const SEMESTERS = ["2026 Sem 2", "2026 Sem 1", "2025 Sem 2"];

const LEARNERS = [
  { id: "l1", pseudonym: "Aisha Binti Rahman", band: "A2" },
  { id: "l2", pseudonym: "Ben Tan" },
];

const PREVIEW_RESPONSE = {
  learner_id: "l1",
  assessment_date: "2026-07-24",
  tasks: [
    { name: "Phoneme Segmentation", score: 7, max_score: 10 },
    { name: "Nonword Decoding", score: 4, max_score: 10 },
  ],
  strengths: ["Phoneme Segmentation"],
  weaknesses: ["Nonword Decoding"],
  confidence_score: 0.6,
  risk_score: 0.4,
  task_results: { "Phoneme Segmentation": { score: 7, max_score: 10 } },
  notes: "Generated for demonstration purposes only.",
};

function pdfFile(name = "report.pdf") {
  return new File(["%PDF-1.4 fake"], name, { type: "application/pdf" });
}

// ASYNC, and every test awaits it. The rubric and the semester list arrive from the backend
// after mount, so asserting on a label or clicking Parse report before they land reads the
// fallback render (raw keys, "Valid range: 0–…", an empty semester that fails the parse guard).
async function renderModal(props = {}) {
  const onClose = jest.fn();
  const onSaved = jest.fn();
  render(<UploadView learners={LEARNERS} onClose={onClose} onSaved={onSaved} {...props} />);
  await screen.findByRole("option", { name: "2026 Sem 2" });   // metadata has landed
  return { onClose, onSaved };
}

beforeEach(() => {
  jest.clearAllMocks();
  getAssessmentMetrics.mockResolvedValue(METRICS);
  getAssessmentSemesters.mockResolvedValue(SEMESTERS);
  previewAssessment.mockResolvedValue(PREVIEW_RESPONSE);
  confirmAssessment.mockResolvedValue({ status: "success" });
});

// ── the pick step ───────────────────────────────────────────────────────────
describe("the pick step", () => {
  test("opens with all four metric boxes blank and their served ranges shown", async () => {
    await renderModal();

    // BLANK, not "0". An untouched box means "not assessed", which is a different claim from a
    // mark of zero — see the comment on the metrics state in UploadView.
    expect(screen.getByLabelText("Writing")).toHaveValue("");
    expect(screen.getByLabelText("Phonics")).toHaveValue("");
    expect(screen.getByLabelText("Word Reading")).toHaveValue("");
    expect(screen.getByLabelText("Word Spelling")).toHaveValue("");

    // Regex, not an exact string: the hint paragraph also carries "· leave blank if not assessed".
    expect(screen.getByText(/Valid range: 0–30/)).toBeInTheDocument();     // writing
    expect(screen.getByText(/Valid range: 0–50/)).toBeInTheDocument();     // phonics
    expect(screen.getAllByText(/Valid range: 0–10/)).toHaveLength(2);      // word reading + spelling

    // The semester list is served too, and defaults to the most recent. Parse report is guarded
    // on it, so a form still showing "Loading…" here cannot submit at all.
    expect(screen.getByLabelText("Semester")).toHaveValue("2026 Sem 2");
    expect(screen.queryByRole("option", { name: "Loading…" })).not.toBeInTheDocument();
  });

  test("lists every learner passed in, and defaults to the first", async () => {
    await renderModal();

    const select = screen.getByLabelText("Learner");
    expect(select).toHaveValue("l1");
    expect(screen.getByRole("option", { name: "Aisha Binti Rahman" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Ben Tan" })).toBeInTheDocument();
  });

  test("Parse report is disabled until a file is chosen", async () => {
    await renderModal();
    expect(screen.getByRole("button", { name: "Parse report" })).toBeDisabled();
  });

  test("an out-of-range metric turns the box red and blocks Parse report, even with a file chosen", async () => {
    const user = userEvent.setup();
    await renderModal();

    await user.upload(screen.getByLabelText(/Assessment file/), pdfFile());
    const phonics = screen.getByLabelText("Phonics");
    await user.type(phonics, "60");   // ceiling is 50

    expect(phonics).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Must be between 0 and 50")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Parse report" })).toBeDisabled();
    expect(previewAssessment).not.toHaveBeenCalled();
  });

  test("a half-typed number shows 'Enter a number' rather than being read as a mark", async () => {
    const user = userEvent.setup();
    await renderModal();

    // A lone "-" passes the keystroke filter but is not a number. Leaving the box EMPTY is the
    // one non-numeric state that is valid, because that is how "not assessed" is expressed.
    const writing = screen.getByLabelText("Writing");
    await user.type(writing, "-");

    expect(screen.getByText("Enter a number")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Parse report" })).toBeDisabled();

    await user.clear(writing);
    expect(screen.queryByText("Enter a number")).not.toBeInTheDocument();
  });

  test("a value back within range clears the error and re-enables Parse report", async () => {
    const user = userEvent.setup();
    await renderModal();
    await user.upload(screen.getByLabelText(/Assessment file/), pdfFile());

    const phonics = screen.getByLabelText("Phonics");
    await user.type(phonics, "60");
    expect(screen.getByRole("button", { name: "Parse report" })).toBeDisabled();

    await user.clear(phonics);
    await user.type(phonics, "30");

    expect(screen.queryByText("Must be between 0 and 50")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Parse report" })).toBeEnabled();
  });
});

// ── parsing ──────────────────────────────────────────────────────────────────
describe("parsing", () => {
  test("Parse report calls previewAssessment with the selected learner and file", async () => {
    const user = userEvent.setup();
    await renderModal();

    const file = pdfFile();
    await user.selectOptions(screen.getByLabelText("Learner"), "l2");
    await user.upload(screen.getByLabelText(/Assessment file/), file);
    await user.click(screen.getByRole("button", { name: "Parse report" }));

    await waitFor(() => expect(previewAssessment).toHaveBeenCalledWith("l2", file));
  });

  test("a successful parse moves to the preview screen", async () => {
    const user = userEvent.setup();
    await renderModal();

    await user.upload(screen.getByLabelText(/Assessment file/), pdfFile());
    await user.click(screen.getByRole("button", { name: "Parse report" }));

    expect(await screen.findByRole("button", { name: "Confirm & save" })).toBeInTheDocument();
    // "Phoneme Segmentation" legitimately appears twice — once as a task row, once as a
    // strength — so this is scoped to the task table specifically.
    const table = screen.getByRole("table");
    expect(within(table).getByText("Phoneme Segmentation")).toBeInTheDocument();
    expect(within(table).getByText("Nonword Decoding")).toBeInTheDocument();
  });

  test("the preview screen echoes the metrics TYPED on step 1, not anything from the response", async () => {
    // UploadView never asks the backend for these four numbers — the therapist enters them,
    // and the preview screen is a read-only confirmation of exactly that, unaffected by
    // whatever the parsed report itself contains.
    const user = userEvent.setup();
    await renderModal();

    await user.type(screen.getByLabelText("Phonics"), "35");
    await user.upload(screen.getByLabelText(/Assessment file/), pdfFile());
    await user.click(screen.getByRole("button", { name: "Parse report" }));

    await screen.findByRole("button", { name: "Confirm & save" });
    expect(screen.getByText("35")).toBeInTheDocument();
    // And the three left blank read as absent, not as zero.
    expect(screen.getAllByText("Not assessed")).toHaveLength(3);
  });

  test("a preview failure shows the error and stays on the pick step", async () => {
    // A .pdf-named file, not .exe: user-event's upload() checks the file's name against the
    // input's accept=".pdf,.docx" and silently drops anything that doesn't match, which would
    // leave "Parse report" disabled and this test asserting on a request that never fired.
    // The rejection itself is what's under test here, not any particular filename.
    const user = userEvent.setup();
    previewAssessment.mockRejectedValue(
      new Error("Could not locate any recognizable assessment data in this report.")
    );
    await renderModal();

    await user.upload(screen.getByLabelText(/Assessment file/), pdfFile());
    await user.click(screen.getByRole("button", { name: "Parse report" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not locate any recognizable assessment data in this report."
    );
    expect(screen.queryByRole("button", { name: "Confirm & save" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Parse report" })).toBeInTheDocument();
  });
});

// ── confirming ───────────────────────────────────────────────────────────────
describe("confirming", () => {
  async function reachPreview(user) {
    await user.upload(screen.getByLabelText(/Assessment file/), pdfFile());
    await user.click(screen.getByRole("button", { name: "Parse report" }));
    await screen.findByRole("button", { name: "Confirm & save" });
  }

  test("Confirm & save sends the parsed fields, the sitting's identity and the metrics", async () => {
    const user = userEvent.setup();
    await renderModal();

    await user.type(screen.getByLabelText("Writing"), "22");
    await reachPreview(user);

    await user.click(screen.getByRole("button", { name: "Confirm & save" }));

    await waitFor(() =>
      expect(confirmAssessment).toHaveBeenCalledWith({
        learner_id: "l1",
        assessment_date: "2026-07-24",
        risk_score: 0.4,
        task_results: PREVIEW_RESPONSE.task_results,
        strengths: ["Phoneme Segmentation"],
        weaknesses: ["Nonword Decoding"],
        confidence_score: 0.6,
        // Which sitting these marks belong to. The band is prefilled from the learner, and the
        // group is derived from it, because the rubric moves between bands.
        semester: "2026 Sem 2",
        band: "A2",
        band_group: "A",
        writing_score: 22,          // a NUMBER, not the string "22"
        phonics_score: null,        // and blank is null, NOT Number("") === 0
        word_reading_score: null,
        word_spelling_score: null,
      })
    );
  });

  test("a successful save shows confirmation and calls onSaved", async () => {
    const user = userEvent.setup();
    const { onSaved } = await renderModal();
    await reachPreview(user);

    await user.click(screen.getByRole("button", { name: "Confirm & save" }));

    expect(await screen.findByText("Data saved successfully.")).toBeInTheDocument();
    expect(onSaved).toHaveBeenCalledTimes(1);
  });

  test("a save failure shows the error and does not call onSaved", async () => {
    const user = userEvent.setup();
    confirmAssessment.mockRejectedValue(new Error("connection refused"));
    const { onSaved } = await renderModal();
    await reachPreview(user);

    await user.click(screen.getByRole("button", { name: "Confirm & save" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("connection refused");
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Confirm & save" })).toBeInTheDocument();
  });

  test("Back returns to the pick step with the metric values still in place", async () => {
    const user = userEvent.setup();
    await renderModal();

    await user.type(screen.getByLabelText("Phonics"), "40");
    await reachPreview(user);

    await user.click(screen.getByRole("button", { name: "Back" }));

    expect(screen.getByLabelText("Phonics")).toHaveValue("40");
    expect(screen.getByRole("button", { name: "Parse report" })).toBeInTheDocument();
  });
});

// ── closing ──────────────────────────────────────────────────────────────────
test("the ✕ button calls onClose", async () => {
  const user = userEvent.setup();
  const { onClose } = await renderModal();

  await user.click(screen.getByText("✕"));

  expect(onClose).toHaveBeenCalledTimes(1);
});
