// INTEGRATION level 4 (frontend) — UC1 Upload Assessment Data.
//
// The UploadView -> AssessmentController messages across the real HTTP boundary. MSW intercepts
// the network rather than the module, so `lib/api.js` is REAL code under test. Levels 1-3 are in
// backend/tests/integration/test_uc1_upload_assessment.py.
//
// WHY UC1 NEEDS THIS TIER PARTICULARLY. The preview call is the only MULTIPART request the app
// makes, and it goes through `apiForm` rather than `api` — a separate code path that was missing
// both of the fixes `api` had already received. It stringified FastAPI's list-shaped 422 detail
// straight into the alert, so an unreadable report told the therapist "[object Object]", and it
// attached no status, so a caller could not tell a rejected file type from an unparseable one.
// A unit test mocks `previewAssessment` and sees none of that; only a real request does.
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

// createClient runs at import time, so the Supabase module is still mocked; it is the token
// *store*, not the thing under test. api.js reads the access token off it for every request.
jest.mock("../../lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: async () => ({ data: { session: { access_token: "jwt.test" } } }),
    },
  },
}));

import UploadView from "../UploadView";
import { server } from "../../test-utils/server";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const LEARNER = { id: "l1", pseudonym: "Aisha Binti Rahman", band: "A2" };

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

/** The form's two metadata reads. Every test needs them: `onUnhandledRequest: "error"` means an
 *  un-stubbed request is a loud failure, not a silent miss. */
function serveMetadata() {
  server.use(
    http.get("*/assessments/metrics", () => HttpResponse.json(METRICS)),
    http.get("*/assessments/semesters", () =>
      HttpResponse.json(["2026 Sem 2", "2026 Sem 1", "2025 Sem 2"])),
  );
}

const renderView = (props = {}) =>
  render(<UploadView learners={[LEARNER]} onClose={() => {}} onSaved={() => {}} {...props} />);

const aFile = () =>
  new File(["Assessment Date: 2026-07-24"], "report.docx", {
    type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  });

async function fillAndParse(user, { phonics = "30" } = {}) {
  await screen.findByRole("option", { name: "2026 Sem 2" });
  if (phonics !== null) await user.type(screen.getByLabelText("Phonics"), phonics);
  await user.upload(screen.getByLabelText(/Assessment file/), aFile());
  await user.click(screen.getByRole("button", { name: "Parse report" }));
}

// --------------------------------------------------------------------------- //
// The multipart request — the shape only this tier sees
// --------------------------------------------------------------------------- //
test("IT-1.10: the report is posted as multipart with the learner id alongside it", async () => {
  const user = userEvent.setup();
  let received;
  let contentType;
  serveMetadata();
  server.use(
    http.post("*/assessments/preview", async ({ request }) => {
      contentType = request.headers.get("content-type");
      const form = await request.formData();
      // NOTE: under jsdom the file part deserialises to a STRING, not a File — the filename and
      // MIME type do not survive, so there is nothing to assert about them here. That is a limit
      // of the environment, not of the app; the real filename is what `validate_format` checks,
      // and the backend tiers cover it (test_ut_1_4b, and IT-1.6 over the real boundary).
      received = { learnerId: form.get("learner_id"), hasFile: form.has("file") };
      return HttpResponse.json(PREVIEW);
    }),
  );
  renderView();
  await fillAndParse(user);

  await screen.findByRole("button", { name: "Confirm & save" });
  expect(received).toEqual({ learnerId: "l1", hasFile: true });
  // Multipart WITH a boundary. `apiForm` deliberately sets no Content-Type of its own so the
  // browser can generate one — naming the type by hand omits the boundary and the body arrives
  // unparseable, which is the failure this assertion guards.
  expect(contentType).toMatch(/^multipart\/form-data; boundary=/);
});

test("IT-1.11: the confirmed payload carries the sitting's identity and a null for blank", async () => {
  const user = userEvent.setup();
  let received;
  serveMetadata();
  server.use(
    http.post("*/assessments/preview", () => HttpResponse.json(PREVIEW)),
    http.post("*/assessments/confirm", async ({ request }) => {
      received = await request.json();
      return HttpResponse.json({ status: "success" });
    }),
  );
  renderView();
  await fillAndParse(user);
  await user.click(await screen.findByRole("button", { name: "Confirm & save" }));

  await waitFor(() => expect(received).toBeTruthy());
  // What makes it a SITTING rather than just a record: which semester, and which paper.
  expect(received.semester).toBe("2026 Sem 2");
  expect(received.band).toBe("A2");
  expect(received.band_group).toBe("A");
  expect(received.phonics_score).toBe(30);
  // JSON null, not 0 — this is the byte on the wire that carries "not assessed" to the backend,
  // and the reason a band-A learner does not get handed a writing activity.
  expect(received.writing_score).toBeNull();
  expect("writing_score" in received).toBe(true);   // present-and-null, not omitted
});

// --------------------------------------------------------------------------- //
// The error path — the bug this tier caught
// --------------------------------------------------------------------------- //
test("IT-1.12: a 422 validation detail reaches the therapist as readable text", async () => {
  const user = userEvent.setup();
  serveMetadata();
  server.use(
    http.post("*/assessments/preview", () =>
      // FastAPI's 422 shape: a LIST of objects, not a string. `new Error(data.detail)` on this
      // renders as "[object Object]", which is exactly what apiForm used to show.
      HttpResponse.json(
        { detail: [{ loc: ["body", "file"], msg: "No extractable text found in the document.", type: "value_error" }] },
        { status: 422 },
      )),
  );
  renderView();
  await fillAndParse(user);

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("No extractable text found in the document.");
  expect(alert).not.toHaveTextContent("[object Object]");
});

test("IT-1.13: a 400 from the wrong file type is shown and the preview is not reached", async () => {
  const user = userEvent.setup();
  serveMetadata();
  server.use(
    http.post("*/assessments/preview", () =>
      HttpResponse.json({ detail: "Only .pdf and .docx are accepted" }, { status: 400 })),
  );
  renderView();
  await fillAndParse(user);

  expect(await screen.findByRole("alert")).toHaveTextContent("Only .pdf and .docx are accepted");
  expect(screen.queryByRole("button", { name: "Confirm & save" })).not.toBeInTheDocument();
});

test("IT-1.14: a storage failure on confirm is surfaced, not swallowed", async () => {
  const user = userEvent.setup();
  serveMetadata();
  server.use(
    http.post("*/assessments/preview", () => HttpResponse.json(PREVIEW)),
    http.post("*/assessments/confirm", () =>
      HttpResponse.json({ detail: "supabase unreachable" }, { status: 500 })),
  );
  renderView();
  await fillAndParse(user);
  await user.click(await screen.findByRole("button", { name: "Confirm & save" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("supabase unreachable");
  // Still on the preview step — a failed save must not report success.
  expect(screen.queryByText("Data saved successfully.")).not.toBeInTheDocument();
});

// --------------------------------------------------------------------------- //
// The served rubric
// --------------------------------------------------------------------------- //
test("IT-1.16: before the rubric lands, the form renders a placeholder — not the ceiling", async () => {
  // WHAT THIS PINS, AND WHY IT IS NOT COSMETIC. The modal renders instantly but the rubric and
  // the semester list arrive from two calls behind one Promise.all, and /assessments/semesters
  // pages the whole learner_sittings table (~23 round trips). Until both land, the form is in a
  // DIFFERENT STATE: raw keys for labels, "0–…" for the range, "Loading…" for the semester.
  //
  // The Selenium tier (backend/tests/system/test_uc1_upload_assessment.py) waits for exactly
  // this placeholder to disappear before touching anything. Its first CI run did not, and all
  // four ST-1.x tests failed. Selenium cannot be run in this repo's hermetic CI, so THIS is the
  // test that holds the strings that wait depends on.
  server.use(
    http.get("*/assessments/metrics", async () => {
      await delay(50);
      return HttpResponse.json(METRICS);
    }),
    http.get("*/assessments/semesters", async () => {
      await delay(50);
      return HttpResponse.json(["2027 Sem 1", "2026 Sem 2", "2026 Sem 1"]);
    }),
  );
  renderView();

  // The pre-load state, character for character. The en dash and the ellipsis are U+2013 and
  // U+2026; the Selenium wait matches on this exact string, so changing it here breaks a test
  // in another language that no frontend run would catch.
  // All four metrics show it, because metricSpecs is [] rather than partially filled.
  expect(screen.getAllByText(/Valid range: 0–… · leave blank if not assessed/)).toHaveLength(4);
  expect(screen.getByText("phonics_score")).toBeInTheDocument();      // label falls back to key
  expect(screen.getByRole("option", { name: "Loading…" })).toBeInTheDocument();

  // ...and the post-load state, which is what every other test in this file assumes.
  expect(await screen.findByText(/Valid range: 0–50/)).toBeInTheDocument();
  expect(screen.getByText("Phonics")).toBeInTheDocument();
  expect(screen.queryByText("phonics_score")).not.toBeInTheDocument();
  expect(screen.queryByRole("option", { name: "Loading…" })).not.toBeInTheDocument();
});

test("IT-1.17: the newest offered semester is first, and it is a lookahead", async () => {
  // The Selenium tier picks option 0 rather than injecting a far-future option of its own: a
  // `<select>` rendered from state cannot keep a foreign option, so React strips it on the next
  // re-render and the selection goes with it. Picking index 0 only works if the API really does
  // serve newest-first AND include semesters beyond what is on record — both asserted here.
  serveMetadata();
  renderView();

  const select = await screen.findByLabelText("Semester");
  await waitFor(() => expect(select.options.length).toBeGreaterThan(0));
  expect([...select.options].map((o) => o.value)).toEqual(["2026 Sem 2", "2026 Sem 1", "2025 Sem 2"]);
  expect(select).toHaveValue("2026 Sem 2");   // defaults to index 0, which is what Selenium picks
});

test("IT-1.15: the form enforces the ceilings the API serves", async () => {
  const user = userEvent.setup();
  serveMetadata();
  let confirmCalls = 0;
  server.use(
    http.post("*/assessments/preview", () => { confirmCalls += 1; return HttpResponse.json(PREVIEW); }),
  );
  renderView();
  await screen.findByText(/Valid range: 0–50/);

  await user.type(screen.getByLabelText("Phonics"), "51");
  await user.upload(screen.getByLabelText(/Assessment file/), aFile());

  // Refused client-side against the SERVED ceiling, so the therapist is not sent on a round trip
  // to be told what the form already knew. The API enforces the same number from the same source.
  expect(screen.getByText("Must be between 0 and 50")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Parse report" })).toBeDisabled();
  expect(confirmCalls).toBe(0);
});
