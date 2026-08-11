// INTEGRATION level 4 (frontend) — UC9 View Learner List.
//
// The LearnersPage -> LearnerController message across the real HTTP boundary. MSW intercepts
// the network rather than the module, so `lib/api.js` is REAL code under test — which is where
// the paging/search query string is actually built. Levels 1-3 are in
// backend/tests/integration/test_uc_view_learners.py.
//
// What this adds over the unit tests (views/__tests__/LearnersPage.test.jsx, UT-2.56 - UT-2.60):
// those mock `listLearners` and assert the ARGUMENTS it was handed. Nothing there proves those
// arguments survive being turned into `?page=&per_page=&caseload=&q=` and read back off a real
// response envelope. That translation is what breaks silently when either side changes shape.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";

// createClient runs at import time, so the Supabase module is still mocked; it is the token
// *store*, not the thing under test.
jest.mock("../../lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: async () => ({ data: { session: { access_token: "jwt.test" } } }),
    },
  },
}));

import LearnersPage from "../LearnersPage";
import { server } from "../../test-utils/server";
import { learnerPage } from "../../test-utils/handlers";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const learner = (id, pseudonym, overrides = {}) => ({
  id, student_id: `S-${id}`, pseudonym, tier: "Tier 2",
  on_caseload: true, band: "A2", band_group: "A", ...overrides,
});

/** Serve GET /learners, recording the query string of every request so a test can assert what
 *  api.js actually put on the wire. `respond` receives the parsed URL. */
function serveLearners(respond) {
  const urls = [];
  server.use(
    http.get("*/learners", ({ request }) => {
      const url = new URL(request.url);
      urls.push(url);
      return HttpResponse.json(respond(url));
    }),
  );
  return urls;
}

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={["/learners"]}>
      <Routes>
        <Route path="/learners" element={<LearnersPage />} />
        {/* A stand-in for the detail page: the navigation target matters, its contents do not,
            and mounting the real one would drag in its whole handler set. */}
        <Route path="/learners/:id" element={<h1>Learner detail stub</h1>} />
      </Routes>
    </MemoryRouter>
  );

test("renders the learners fetched from the API", async () => {
  const urls = serveLearners(() =>
    learnerPage([learner("l1", "Aisha Binti Rahman"), learner("l2", "Ben Tan")], { total: 2 }));
  renderPage();

  expect(await screen.findByText("Aisha Binti Rahman")).toBeInTheDocument();
  expect(screen.getByText("Ben Tan")).toBeInTheDocument();
  expect(screen.getByText(/Showing 1–2 of 2/)).toBeInTheDocument();

  // The paging contract, as it reaches the wire. PostgREST caps a select at 1,000 rows and
  // truncates WITHOUT erroring, so an unpaged read would serve a fraction of the table while
  // looking healthy — these params are the thing standing between that and the therapist.
  expect(urls[0].searchParams.get("page")).toBe("1");
  expect(urls[0].searchParams.get("per_page")).toBe("24");
  expect(urls[0].searchParams.get("caseload")).toBe("true");   // defaults to the caseload
});

test("filters the visible list as the user types in the search box", async () => {
  const user = userEvent.setup();
  // The match must NOT be present before the search, or "it appeared" proves nothing — a name
  // already on the first page resolves `findByText` against the pre-search render and the test
  // passes without the query ever being sent.
  const urls = serveLearners((url) => {
    const q = url.searchParams.get("q");
    const rows = q ? [learner("l3", "Cara Lim")]
                   : [learner("l1", "Aisha"), learner("l2", "Ben Tan")];
    return learnerPage(rows, { total: rows.length });
  });
  renderPage();
  await screen.findByText("Aisha");

  await user.type(screen.getByLabelText("Search learners"), "Cara");

  // Server-side search, not a client-side filter of an already-fetched page — so the assertion
  // that matters is that `q` reached the backend and the page re-rendered from its answer.
  //
  // WAIT FOR THE ARRIVAL, THEN CHECK THE DEPARTURE, not the other way round. Typing swaps the
  // grid for loading skeletons, so "Aisha is gone" becomes true the moment the request starts —
  // waiting on that first lets the next assertion run before the response has rendered.
  expect(await screen.findByText("Cara Lim")).toBeInTheDocument();
  expect(screen.queryByText("Aisha")).not.toBeInTheDocument();
  // Debounced 300ms: typing four characters must not send four requests.
  expect(urls.filter((u) => u.searchParams.get("q") === "Cara")).toHaveLength(1);
});

test("navigates to the learner detail page when a card is clicked", async () => {
  const user = userEvent.setup();
  serveLearners(() => learnerPage([learner("l1", "Aisha Binti Rahman")], { total: 1 }));
  renderPage();

  await user.click(await screen.findByText("Aisha Binti Rahman"));

  expect(await screen.findByRole("heading", { name: "Learner detail stub" })).toBeInTheDocument();
});

test("shows an error state when the learners request fails", async () => {
  server.use(
    http.get("*/learners", () =>
      HttpResponse.json({ detail: "Could not load learners" }, { status: 500 })),
  );
  renderPage();

  // The controller's `detail` has to survive api.js's unwrapping and reach the screen — a bare
  // "500 Internal Server Error" would tell the therapist nothing about whether to retry.
  expect(await screen.findByText(/Failed to load learners/)).toBeInTheDocument();
  expect(screen.getByText(/Could not load learners/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
});

test("the caseload toggle re-queries and reveals the research cohort", async () => {
  const user = userEvent.setup();
  const urls = serveLearners((url) => {
    const caseload = url.searchParams.get("caseload") === "true";
    return caseload
      ? learnerPage([learner("l1", "Aisha")], { total: 1 })
      : learnerPage([learner("l1", "Aisha"), learner("c1", null, { on_caseload: false })],
                    { total: 5783 });
  });
  renderPage();
  await screen.findByText("Aisha");

  await user.click(screen.getByRole("button", { name: "My caseload only" }));

  // `learners` holds the therapist's caseload AND ~5,773 anonymised cohort rows; the toggle is
  // what decides which population is being read, so it must reach the query, not filter locally.
  await waitFor(() =>
    expect(urls.at(-1).searchParams.get("caseload")).toBe("false"));
  expect(await screen.findByText(/of 5,783/)).toBeInTheDocument();   // toLocaleString, so a comma
  expect(screen.getByText(/includes the anonymised DAS research cohort/)).toBeInTheDocument();
});
