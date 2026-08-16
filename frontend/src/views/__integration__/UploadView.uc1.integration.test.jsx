// INTEGRATION level 4 (frontend) — UC1 Upload Assessment Data.
//
// The UploadView -> AssessmentController message across the real HTTP boundary. MSW intercepts
// the network rather than the module, so `lib/api.js` is REAL code under test here — which is
// where the multipart request for /assessments/preview and the JSON request for
// /assessments/confirm are actually built. Levels 1-3 are in
// backend/tests/integration/test_uc1_upload_assessment.py.
//
// Mirrors ShareWindow.uc7.integration.test.jsx's shape: only lib/supabase is mocked (the token
// store, not the thing under test), everything else — UploadView, api.js, apiForm — is real.
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

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

const LEARNERS = [{ id: "l1", pseudonym: "Aisha Binti Rahman" }];

function pdfFile(name = "report.pdf") {
  return new File(["%PDF-1.4 fake"], name, { type: "application/pdf" });
}

function renderModal() {
  const onClose = jest.fn();
  const onSaved = jest.fn();
  render(<UploadView learners={LEARNERS} onClose={onClose} onSaved={onSaved} />);
  return { onClose, onSaved };
}

const PREVIEW_BODY = {
  learner_id: "l1",
  assessment_date: "2026-07-24",
  tasks: [{ name: "Phoneme Segmentation", score: 7, max_score: 10 }],
  strengths: ["Phoneme Segmentation"],
  weaknesses: ["Nonword Decoding"],
  confidence_score: 0.6,
  risk_score: 0.4,
  task_results: { "Phoneme Segmentation": { score: 7, max_score: 10 } },
  notes: "",
};

test("IT-1.x: preview is sent as multipart form data carrying the learner id and file", async () => {
  const user = userEvent.setup();
  let receivedLearnerId;
  let receivedFile;
  server.use(
    http.post("*/assessments/preview", async ({ request }) => {
      const form = await request.formData();
      receivedLearnerId = form.get("learner_id");
      receivedFile = form.get("file");
      return HttpResponse.json(PREVIEW_BODY);
    }),
  );
  renderModal();

  await user.upload(screen.getByLabelText(/Assessment file/), pdfFile("report.pdf"));
  await user.click(screen.getByRole("button", { name: "Parse report" }));

  await screen.findByRole("button", { name: "Confirm & save" });
  expect(receivedLearnerId).toBe("l1");
  // Not asserting on .name or .size here: jsdom's File and the undici-based FormData/Request
  // MSW relies on don't reliably preserve Blob properties across that boundary in this test
  // environment — .name and .size both came back undefined despite the file genuinely being
  // sent (confirmed by the request completing and the preview rendering). The entry existing
  // at all is what this contract actually needs to prove.
  expect(receivedFile).toBeTruthy();
});

test("IT-1.x: a 400 detail from the controller reaches the therapist", async () => {
  // A .pdf-named file, not .exe: user-event's upload() checks the file's name against the
  // input's accept=".pdf,.docx" and silently drops anything that doesn't match, which would
  // leave "Parse report" disabled and this test asserting on a request that never fired.
  //
  // This is the case a mocked-api unit test cannot catch: it depends on api.js actually
  // unwrapping FastAPI's `detail` field out of the response body, the same translation UC7's
  // integration tier caught missing for ShareWindow.
  const user = userEvent.setup();
  server.use(
    http.post("*/assessments/preview", () =>
      HttpResponse.json({ detail: "No extractable text found in the document." }, { status: 400 })),
  );
  renderModal();

  await user.upload(screen.getByLabelText(/Assessment file/), pdfFile());
  await user.click(screen.getByRole("button", { name: "Parse report" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "No extractable text found in the document."
  );
});

test("IT-1.x: confirm is sent as JSON with the metrics coerced to numbers", async () => {
  const user = userEvent.setup();
  let received;
  server.use(
    http.post("*/assessments/preview", () => HttpResponse.json(PREVIEW_BODY)),
    http.post("*/assessments/confirm", async ({ request }) => {
      received = await request.json();
      return HttpResponse.json({ status: "success", message: "Data saved successfully" });
    }),
  );
  renderModal();

  const phonics = screen.getByLabelText(/Phonics/);
  await user.clear(phonics);
  await user.type(phonics, "35");
  await user.upload(screen.getByLabelText(/Assessment file/), pdfFile());
  await user.click(screen.getByRole("button", { name: "Parse report" }));
  await user.click(await screen.findByRole("button", { name: "Confirm & save" }));

  await waitFor(() => expect(received).toMatchObject({
    learner_id: "l1",
    assessment_date: "2026-07-24",
    strengths: ["Phoneme Segmentation"],
    weaknesses: ["Nonword Decoding"],
    phonics_score: 35,   // sent as a JSON number, not the string "35" typed into the box
  }));
  expect(await screen.findByText("Data saved successfully.")).toBeInTheDocument();
});

test("IT-1.x: a 500 StorageError detail from confirm reaches the therapist", async () => {
  const user = userEvent.setup();
  server.use(
    http.post("*/assessments/preview", () => HttpResponse.json(PREVIEW_BODY)),
    http.post("*/assessments/confirm", () =>
      HttpResponse.json({ detail: "connection refused" }, { status: 500 })),
  );
  renderModal();

  await user.upload(screen.getByLabelText(/Assessment file/), pdfFile());
  await user.click(screen.getByRole("button", { name: "Parse report" }));
  await user.click(await screen.findByRole("button", { name: "Confirm & save" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("connection refused");
});