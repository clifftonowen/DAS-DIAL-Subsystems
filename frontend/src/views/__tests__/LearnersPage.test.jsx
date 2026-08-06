// UNIT (frontend) — the Learners tab's contract with GET /learners (UC2).
//
//     AB2.21  LearnersPage.jsx (React)   UT-2.56 .. UT-2.60
//
// WHAT THIS EXISTS TO PIN. `learners` holds the ~5,783-row anonymised DAS research cohort
// alongside the therapist's ten, so this page cannot do what it used to: fetch everything and
// filter in the browser. Two things break at that scale, and neither announces itself —
// PostgREST truncates an unpaged select at 1,000 rows WITHOUT erroring, and thousands of cards
// freeze the grid on every keystroke.
//
// So the assertions here are mostly about WHERE the work happens: that paging and search are
// parameters on the request rather than operations on the response.

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import LearnersPage from "../LearnersPage";
import { listLearners } from "../../lib/api";

// A factory, not an automock: lib/api imports lib/supabase, which calls createClient() at
// module scope and throws without VITE_SUPABASE_URL.
jest.mock("../../lib/api", () => ({ listLearners: jest.fn() }));

const caseload = (id, pseudonym, over = {}) => ({
  id, student_id: null, pseudonym, tier: "Tier 2", on_caseload: true,
  band: "A2", band_group: "A", cluster_cohort: "Cohort 2", ...over,
});

const cohort = (id, studentId, over = {}) => ({
  id, student_id: studentId, pseudonym: "", tier: "", on_caseload: false,
  band: "B4", band_group: "B", cluster_cohort: "Cohort 3", ...over,
});

const page = (items, total = items.length, over = {}) => ({
  items, total, page: 1, per_page: 24, ...over,
});

const renderPage = () =>
  render(
    <MemoryRouter>
      <LearnersPage />
    </MemoryRouter>
  );

// The last query LearnersPage sent.
const lastQuery = () => listLearners.mock.calls.at(-1)[0];

beforeEach(() => {
  jest.clearAllMocks();
  listLearners.mockResolvedValue(page([caseload("l1", "Aisha Binti Rahman")]));
});

// ── the request ───────────────────────────────────────────────────────────────
test("UT-2.56: opens on the therapist's own learners", async () => {
  // Not the whole table. Defaulting to everything would open this tab on thousands of
  // anonymised research rows with the ten that matter somewhere on page 200.
  renderPage();

  await waitFor(() => expect(listLearners).toHaveBeenCalled());
  expect(lastQuery()).toEqual(expect.objectContaining({ page: 1, caseload: true }));
});

test("UT-2.57: search is a request parameter, not a filter on the response", async () => {
  // THE POINT OF THE REWRITE. Filtering client-side can only ever search the page it already
  // has, so a name on page 40 would be unfindable — and at 5,783 rows the page it has is a
  // PostgREST-truncated fraction of the table anyway.
  const user = userEvent.setup();
  renderPage();
  await waitFor(() => expect(listLearners).toHaveBeenCalled());

  await user.type(screen.getByRole("textbox", { name: /search/i }), "aisha");

  await waitFor(() => expect(lastQuery().q).toBe("aisha"));
});

test("UT-2.57: typing is debounced into one request", async () => {
  // Five keystrokes must not be five round trips against a table of thousands.
  const user = userEvent.setup();
  renderPage();
  await waitFor(() => expect(listLearners).toHaveBeenCalled());
  const before = listLearners.mock.calls.length;

  await user.type(screen.getByRole("textbox", { name: /search/i }), "aisha");
  await waitFor(() => expect(lastQuery().q).toBe("aisha"));

  expect(listLearners.mock.calls.length - before).toBeLessThanOrEqual(2);
});

test("UT-2.58: a new search returns to page 1", async () => {
  // Staying on page 7 of the previous results would show an empty grid for a search with
  // fewer than 7 pages of hits — which reads as "no matches" when there are plenty.
  const user = userEvent.setup();
  listLearners.mockResolvedValue(page(
    Array.from({ length: 24 }, (_, i) => cohort(`c${i}`, `Student ${i}`)),
    500,
  ));
  renderPage();
  await waitFor(() => expect(listLearners).toHaveBeenCalled());

  await user.click(screen.getByRole("button", { name: /Next/ }));
  await waitFor(() => expect(lastQuery().page).toBe(2));

  await user.type(screen.getByRole("textbox", { name: /search/i }), "x");

  await waitFor(() => expect(lastQuery().page).toBe(1));
});

test("UT-2.58: the caseload toggle flips the scope and resets the page", async () => {
  const user = userEvent.setup();
  renderPage();
  await waitFor(() => expect(listLearners).toHaveBeenCalled());

  await user.click(screen.getByRole("button", { name: /My caseload only/ }));

  await waitFor(() => expect(lastQuery().caseload).toBe(false));
  expect(lastQuery().page).toBe(1);
});

// ── what is rendered ──────────────────────────────────────────────────────────
test("UT-2.59: an anonymised learner falls back to their student id", async () => {
  // The research cohort has no pseudonym — their workbook id is the only identity they have,
  // and a card reading "Unknown" would be useless for finding them again.
  listLearners.mockResolvedValue(page([cohort("c1", "Student 0142")]));
  renderPage();

  expect(await screen.findByText("Student 0142")).toBeInTheDocument();
});

test("UT-2.59: the count reflects the server's total, not the page length", async () => {
  // 24 cards out of 5,783 is the normal case; showing "24" would misreport the table by two
  // orders of magnitude.
  listLearners.mockResolvedValue(page(
    Array.from({ length: 24 }, (_, i) => cohort(`c${i}`, `Student ${i}`)), 5783));
  renderPage();

  expect(await screen.findByText(/of 5,783/)).toBeInTheDocument();
});

test("UT-2.60: the pager appears only when there is more than one page", async () => {
  listLearners.mockResolvedValue(page([caseload("l1", "Aisha Binti Rahman")], 1));
  renderPage();
  await screen.findByText(/Showing/);

  expect(screen.queryByRole("navigation", { name: /pagination/i })).not.toBeInTheDocument();
});

test("UT-2.60: Previous is disabled on the first page", async () => {
  listLearners.mockResolvedValue(page(
    Array.from({ length: 24 }, (_, i) => cohort(`c${i}`, `Student ${i}`)), 500));
  renderPage();

  expect(await screen.findByRole("button", { name: /Previous/ })).toBeDisabled();
  expect(screen.getByRole("button", { name: /Next/ })).toBeEnabled();
});

test("UT-2.60: an empty result says so rather than rendering a bare grid", async () => {
  const user = userEvent.setup();
  renderPage();
  await waitFor(() => expect(listLearners).toHaveBeenCalled());

  listLearners.mockResolvedValue(page([], 0));
  await user.type(screen.getByRole("textbox", { name: /search/i }), "zzz");

  expect(await screen.findByText(/No learners match/)).toBeInTheDocument();
});

test("UT-2.60: a failed request surfaces the reason", async () => {
  listLearners.mockRejectedValue(new Error("boom"));
  renderPage();

  expect(await screen.findByText(/Failed to load learners: boom/)).toBeInTheDocument();
});
