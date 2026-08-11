// UNIT (frontend) — generating a learning activity on the learner's own page (UC3).
//
// Generation used to be a page of its own at /generate, reached from the sidebar, where the
// therapist searched for a learner all over again. It now happens here, against the learner
// already on screen, next to the marks the activity is built from and the review it will get.
// These cases are the ones that lived in GeneratePage.test.jsx, re-pointed at the new host,
// plus the two behaviours that only exist because of the move: a fresh activity REPLACES the
// one on screen, and the grounding is read from the stored row rather than the response, so
// it is there for anyone who opens the learner later.
//
// The api module is mocked, so what this asserts is the page's contract with the backend.

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import LearnerDetailPage from "../LearnerDetailPage";
import * as api from "../../lib/api";

// A factory, not an automock: lib/api imports lib/supabase, which calls createClient() at
// module scope and throws without VITE_SUPABASE_URL. See MainPage.clusterClickthrough.test.jsx.
jest.mock("../../lib/api", () => ({
  getLearner: jest.fn(),
  getLearnerOverview: jest.fn(),
  getLearnerActivities: jest.fn(),
  generateProfile: jest.fn(),
  generateActivity: jest.fn(),
  // ReviewSection renders under the activity and loads its own verdicts on mount.
  getReviews: jest.fn(),
  submitReview: jest.fn(),
}));

const LEARNER_ID = "11111111-1111-1111-1111-111111111111";

/** A stored learning_activities row — content is an OBJECT here, unlike the generate response. */
const activityRow = (overrides = {}) => ({
  id: "act-1",
  learner_id: LEARNER_ID,
  content: {
    text: "Title: Rhyme Time\n1. Clap the rhyme.",
    query: "literacy activity targeting phonics 2.4/10",
    grounding: [
      { title: "Rhyme Time", source: "a.pdf", page: 4, concept: "onset_rime",
        stage: "practice", similarity: 0.712 },
    ],
  },
  literacy_objective: "",
  // A STORED ROW, so GENERATED is still a real value here — it is the column default and what
  // every row written before UC3's validate loop carries. Not to be confused with the generate
  // RESPONSE, which now says VALIDATED or FLAGGED and never GENERATED.
  status: "GENERATED",
  grounded_on: ["Rhyme Time (a.pdf p.4)"],
  ...overrides,
});

beforeEach(() => {
  jest.clearAllMocks();
  api.getLearner.mockResolvedValue({
    id: LEARNER_ID, pseudonym: "Aisha", band: "A2", band_group: "A",
    tier: "Tier 2", on_caseload: true,
  });
  api.getLearnerOverview.mockResolvedValue({
    learner_id: LEARNER_ID, metrics: [], history: [], band_group: "A",
  });
  api.getLearnerActivities.mockResolvedValue([]);
  api.getReviews.mockResolvedValue([]);
});

const renderPage = () =>
  render(
    <MemoryRouter>
      <LearnerDetailPage learnerId={LEARNER_ID} onBack={() => {}} />
    </MemoryRouter>
  );

const generate = async (user) =>
  user.click(await screen.findByRole("button", { name: "Generate Activity" }));

// ── the request ───────────────────────────────────────────────────────────────
test("generates for the learner already on screen, with no band", async () => {
  const user = userEvent.setup();
  api.generateActivity.mockResolvedValue({ status: "VALIDATED", content: "x", query: "q",
                                           learner_id: LEARNER_ID, grounding: [] });
  renderPage();
  await generate(user);

  // No learner search and no band: the id comes from the page, and retrieval scope is read from
  // the learner's band_group server-side. A band from here would be a way around that.
  await waitFor(() => expect(api.generateActivity).toHaveBeenCalledWith(LEARNER_ID, { notes: "" }));
  expect(api.generateActivity.mock.calls[0][1]).not.toHaveProperty("band");
});

test("sends the focus field as notes", async () => {
  const user = userEvent.setup();
  api.generateActivity.mockResolvedValue({ status: "VALIDATED", content: "x", query: "q",
                                           learner_id: LEARNER_ID, grounding: [] });
  renderPage();
  await user.type(await screen.findByLabelText("Optional focus"), "rhyming games");
  await generate(user);

  await waitFor(() =>
    expect(api.generateActivity).toHaveBeenCalledWith(LEARNER_ID, { notes: "rhyming games" })
  );
});

// ── a fresh activity replaces the old one ─────────────────────────────────────
test("re-reads the activity list so the panel shows the new activity", async () => {
  const user = userEvent.setup();
  api.getLearnerActivities.mockResolvedValue([activityRow()]);
  api.generateActivity.mockResolvedValue({ status: "VALIDATED", content: "ignored", query: "q",
                                           learner_id: LEARNER_ID, grounding: [] });
  renderPage();
  expect(await screen.findByText(/Clap the rhyme/)).toBeInTheDocument();

  // The response carries no activity id and its `content` is a bare string, so the page cannot
  // render it directly — ReviewSection and ShareWindow both need a real row.
  api.getLearnerActivities.mockResolvedValue([
    activityRow({ id: "act-2", content: { text: "Title: Sound Sort\n1. Sort the sounds." } }),
  ]);
  await generate(user);

  expect(await screen.findByText(/Sort the sounds/)).toBeInTheDocument();
  expect(screen.queryByText(/Clap the rhyme/)).not.toBeInTheDocument();
  expect(api.getLearnerActivities).toHaveBeenCalledTimes(2);
});

// ── grounding is stored, not ephemeral ────────────────────────────────────────
test("shows grounding from the stored row without generating anything", async () => {
  api.getLearnerActivities.mockResolvedValue([activityRow()]);
  renderPage();

  // The point of persisting it: a therapist who never ran the generation still sees what the
  // activity was built from.
  expect(await screen.findByText("Rhyme Time")).toBeInTheDocument();
  expect(screen.getByText("a.pdf p.4 · onset_rime · practice")).toBeInTheDocument();
  expect(screen.getByText("0.71")).toBeInTheDocument();
  expect(api.generateActivity).not.toHaveBeenCalled();
});

test("falls back to grounded_on for rows generated before grounding was stored", async () => {
  api.getLearnerActivities.mockResolvedValue([
    activityRow({ content: { text: "Older activity body." } }),
  ]);
  renderPage();

  expect(await screen.findByText("Rhyme Time (a.pdf p.4)")).toBeInTheDocument();
  // Nothing to show a score against — the old text[] never carried one.
  expect(screen.queryByText("0.71")).not.toBeInTheDocument();
});

test("renders no grounding card when the activity has no provenance at all", async () => {
  api.getLearnerActivities.mockResolvedValue([
    activityRow({ content: { text: "Body." }, grounded_on: [] }),
  ]);
  renderPage();

  expect(await screen.findByText("Body.")).toBeInTheDocument();
  expect(screen.queryByText("Grounding sources")).not.toBeInTheDocument();
});

// ── the two ways it can fail ──────────────────────────────────────────────────
test("shows the refusal reason and keeps the previous activity on screen", async () => {
  const user = userEvent.setup();
  api.getLearnerActivities.mockResolvedValue([activityRow()]);
  api.generateActivity.mockResolvedValue({
    status: "INSUFFICIENT_CONTEXT", content: "",
    reason: "best similarity 0.310 is below the 0.67 gate.",
    query: "literacy activity targeting phonics 2.4/10", learner_id: LEARNER_ID, grounding: [],
  });
  renderPage();
  await generate(user);

  expect(await screen.findByText("Not enough curriculum grounding")).toBeInTheDocument();
  // The page renders the backend's reason verbatim; the gate value is the backend's business,
  // so match the shape of the sentence rather than pinning the calibrated number here.
  expect(screen.getByText(/below the [\d.]+ gate/)).toBeInTheDocument();
  // A refusal must not destroy work the therapist may still be using.
  expect(screen.getByText(/Clap the rhyme/)).toBeInTheDocument();
});

test("tells the therapist to upload scores when the learner has none", async () => {
  const user = userEvent.setup();
  api.generateActivity.mockResolvedValue({
    status: "INSUFFICIENT_CONTEXT", content: "", reason: "…",
    query: "", learner_id: LEARNER_ID, grounding: [],
  });
  renderPage();
  await generate(user);

  // An EMPTY query is the signal: build_query returns "" when the learner has no marks at all.
  expect(await screen.findByText("This learner has no assessment scores yet")).toBeInTheDocument();
  expect(screen.getByText(/there are none on record/)).toBeInTheDocument();
});

test("surfaces a failed request separately from a refusal", async () => {
  const user = userEvent.setup();
  jest.spyOn(console, "error").mockImplementation(() => {});
  api.generateActivity.mockRejectedValue(new Error("500 Internal Server Error"));
  renderPage();
  await generate(user);

  expect(await screen.findByText("Could not generate activity")).toBeInTheDocument();
  expect(screen.getByText("500 Internal Server Error")).toBeInTheDocument();
  expect(screen.queryByText("Not enough curriculum grounding")).not.toBeInTheDocument();
});
