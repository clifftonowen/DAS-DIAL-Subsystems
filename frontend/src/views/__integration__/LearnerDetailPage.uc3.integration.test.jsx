// INTEGRATION level 4 (frontend) — UC3 Generate Adaptive Learning Activity.
//
// The LearnerDetailPage -> ActivityController message across the real HTTP boundary. MSW
// intercepts the network rather than the module, so `lib/api.js` is REAL code under test.
// Levels 1-3 are in backend/tests/integration/test_uc3_generate_activity.py.
//
// WHY THIS TIER EARNS ITS KEEP HERE. When UC3 gained its generate/validate loop the backend
// stopped returning `status: "GENERATED"` and started returning VALIDATED or FLAGGED. The page
// gated its re-fetch on the old string, so a successful generation wrote a row and then showed
// the therapist nothing at all — no activity, no error. Every existing test stayed green: the
// unit tests mock `lib/api` and assert the page's contract against mocks that were updated to
// say GENERATED at the same time as the page, and no backend test crosses the HTTP boundary into
// the UI. A test that puts a REAL response shape through the REAL client is the only tier that
// could have caught it, which is what these are.
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";

// createClient runs at import time, so the Supabase module is still mocked; it is the token
// *store*, not the thing under test. api.js reads the access token off it for every request.
jest.mock("../../lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: async () => ({ data: { session: { access_token: "jwt.test" } } }),
    },
  },
}));

import LearnerDetailPage from "../LearnerDetailPage";
import { server } from "../../test-utils/server";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const LEARNER_ID = "11111111-1111-4111-8111-111111111111";

const ACTIVITY = {
  id: "activity-1",
  learner_id: LEARNER_ID,
  status: "VALIDATED",
  retry_count: 0,
  literacy_objective: "",
  grounded_on: ["Rhyme Time (a.pdf p.4)"],
  content: {
    text: "# Rhyme Time\n\n1. Clap the onset, then blend the rime.",
    query: "literacy activity targeting phonics 2.4/10",
    grounding: [
      { title: "Rhyme Time", source: "a.pdf", page: 4, concept: "onset_rime",
        stage: "practice", similarity: 0.712 },
    ],
  },
};

/** The page's mount-time reads, plus ReviewSection's — `onUnhandledRequest: "error"` means the
 *  TRANSITIVE set has to be served, not just the endpoint under test. ReviewSection mounts
 *  itself as soon as an activity exists, so its GET is part of the success path.
 *
 *  `activities` is a QUEUE, one entry per call: generation deliberately does not render its own
 *  response (it carries no activity id and its `content` is a bare string), it re-reads the list
 *  and takes the newest row. Serving the same body twice would make the re-read invisible. */
function serveLearner({ activities = [[]] } = {}) {
  const queue = [...activities];
  server.use(
    http.get(`*/learners/${LEARNER_ID}`, () =>
      HttpResponse.json({ id: LEARNER_ID, pseudonym: "Aisha", band: "A2",
                          band_group: "A", tier: "Tier 2", on_caseload: true })),
    http.get(`*/learners/${LEARNER_ID}/overview`, () =>
      HttpResponse.json({ learner_id: LEARNER_ID, metrics: [], history: [], band_group: "A" })),
    http.get(`*/profiles/${LEARNER_ID}/activities`, () =>
      HttpResponse.json(queue.length > 1 ? queue.shift() : queue[0])),
    http.get("*/reviews/*", () => HttpResponse.json([])),
  );
}

const renderPage = () =>
  render(
    <MemoryRouter>
      <LearnerDetailPage learnerId={LEARNER_ID} onBack={() => {}} />
    </MemoryRouter>
  );

const generate = async (user) =>
  user.click(await screen.findByRole("button", { name: "Generate Activity" }));

// --------------------------------------------------------------------------- //
// The success path — the regression these exist for
// --------------------------------------------------------------------------- //
test("IT-3.11: a VALIDATED response puts the new activity on screen", async () => {
  const user = userEvent.setup();
  let received;
  serveLearner({ activities: [[], [ACTIVITY]] });   // empty on mount, then the new row
  server.use(
    http.post(`*/activities/${LEARNER_ID}/generate`, async ({ request }) => {
      received = await request.json();
      return HttpResponse.json({
        status: "VALIDATED", content: ACTIVITY.content.text, query: ACTIVITY.content.query,
        grounding: ACTIVITY.content.grounding, learner_id: LEARNER_ID,
        retry_count: 0, review_notes: "",
      });
    }),
  );
  renderPage();
  await generate(user);

  // The assertion that fails on the pre-fix page: it re-read the list and rendered the row.
  expect(await screen.findByText(/Clap the onset/)).toBeInTheDocument();
  expect(received).toEqual({ notes: "" });
});

test("IT-3.12: a FLAGGED response still renders the activity, badged for review", async () => {
  const user = userEvent.setup();
  const flagged = { ...ACTIVITY, status: "FLAGGED", retry_count: 2 };
  serveLearner({ activities: [[], [flagged]] });
  server.use(
    http.post(`*/activities/${LEARNER_ID}/generate`, () =>
      HttpResponse.json({
        status: "FLAGGED", content: flagged.content.text, query: flagged.content.query,
        grounding: flagged.content.grounding, learner_id: LEARNER_ID, retry_count: 2,
        review_notes: "step 2 cites a rime that is in none of the grounding pages",
      })),
  );
  renderPage();
  await generate(user);

  // FLAGGED means the reviewer never passed it, but the row IS written — alt flow 6b surfaces
  // the best attempt rather than discarding the work, so the therapist must still see it.
  expect(await screen.findByText(/Clap the onset/)).toBeInTheDocument();
  expect(screen.getByText("Flagged for review")).toBeInTheDocument();
});

test("the focus field is sent as notes", async () => {
  const user = userEvent.setup();
  let received;
  serveLearner({ activities: [[], [ACTIVITY]] });
  server.use(
    http.post(`*/activities/${LEARNER_ID}/generate`, async ({ request }) => {
      received = await request.json();
      return HttpResponse.json({ status: "VALIDATED", content: "x", query: "q",
                                 grounding: [], learner_id: LEARNER_ID, retry_count: 0 });
    }),
  );
  renderPage();
  await user.type(await screen.findByLabelText("Optional focus"), "rhyming games");
  await generate(user);

  await waitFor(() => expect(received).toEqual({ notes: "rhyming games" }));
});

// --------------------------------------------------------------------------- //
// The two ways it can not produce an activity
// --------------------------------------------------------------------------- //
test("IT-3.13: a refusal renders its reason and keeps the previous activity on screen", async () => {
  const user = userEvent.setup();
  serveLearner({ activities: [[ACTIVITY]] });       // one already on screen before we start
  server.use(
    http.post(`*/activities/${LEARNER_ID}/generate`, () =>
      HttpResponse.json({
        status: "INSUFFICIENT_CONTEXT", content: "",
        reason: "Retrieved 1 curriculum chunk(s) within Band A; best similarity 0.310 is below "
              + "the 0.67 gate.",
        query: "literacy activity targeting phonics 2.4/10",
        grounding: [], learner_id: LEARNER_ID,
      })),
  );
  renderPage();
  expect(await screen.findByText(/Clap the onset/)).toBeInTheDocument();
  await generate(user);

  // A refusal is a 200 with a reason, not an error: the corpus genuinely does not cover this
  // learner. Replacing the activity with a banner would lose work the therapist is still using.
  expect(await screen.findByText("Not enough curriculum grounding")).toBeInTheDocument();
  expect(screen.getByText(/below the 0.67 gate/)).toBeInTheDocument();
  expect(screen.getByText(/Clap the onset/)).toBeInTheDocument();
});

test("IT-3.14: a 502 from the controller reaches the user as an error", async () => {
  const user = userEvent.setup();
  serveLearner({ activities: [[]] });
  server.use(
    http.post(`*/activities/${LEARNER_ID}/generate`, () =>
      HttpResponse.json({ detail: "the model could not be reached" }, { status: 502 })),
  );
  renderPage();
  await generate(user);

  // api.js unwraps FastAPI's `detail`; a thrown error is a different banner from a refusal
  // because they are different problems — one is retryable infrastructure, one is the corpus.
  expect(await screen.findByText("Could not generate activity")).toBeInTheDocument();
  expect(screen.getByText("the model could not be reached")).toBeInTheDocument();
  expect(screen.queryByText("Not enough curriculum grounding")).not.toBeInTheDocument();
});
