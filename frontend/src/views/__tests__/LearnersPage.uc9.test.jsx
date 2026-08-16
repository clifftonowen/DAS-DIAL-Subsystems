// UNIT (frontend) — UC9 View Learner List: the assigned-vs-all moves on the Learners tab.
//
//     AB9.1   LearnersPage.jsx (React)   UT-9.8 .. UT-9.11
//
// UC2's file (LearnersPage.test.jsx, UT-2.56 .. UT-2.60) pins the paged/searchable list
// contract; UC9 is the therapist's ability to move between their OWN learners and the whole
// table, and to recover when the list cannot load. Following the PM3 convention that a use
// case's tests live in its own file, these carry the UC in the filename (as
// AuthView.uc6/uc8.test.jsx do) and cover the plan's UT-9.8 .. UT-9.11.
//
// The mock/fixture block is duplicated from LearnersPage.test.jsx on purpose — the two files
// are independent, and a shared helper would couple a UC9 test to UC2's setup.
import { render, screen, waitFor } from "@testing-library/react";
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

// ── UT-9.8 / UT-9.9 — the populated and empty list states ────────────────────
test("UT-9.8: a populated list renders each learner's pseudonym, band and tier", async () => {
  // The UC9 postcondition: the therapist sees who is assigned to them, with the card's
  // band and tier. StudentCard renders them as "A2 · Tier 2" (band · tier).
  listLearners.mockResolvedValue(page([caseload("l1", "Aisha Binti Rahman")]));
  renderPage();

  expect(await screen.findByText("Aisha Binti Rahman")).toBeInTheDocument();
  expect(screen.getByText("A2 · Tier 2")).toBeInTheDocument();
});

test("UT-9.9: an empty result renders the 'No learners found.' empty state", async () => {
  // total === 0 drives the count line to "No learners found." rather than a bare grid.
  listLearners.mockResolvedValue(page([], 0));
  renderPage();

  expect(await screen.findByText("No learners found.")).toBeInTheDocument();
});

// ── UT-9.10 / UT-9.11a / UT-9.11b — the retry, toggle and back ───────────────
test("UT-9.11a: toggling off surfaces the whole cohort alongside the caseload", async () => {
  // The move this use case exists for: the therapist can step out of their own ten and see
  // everyone. Flipping the toggle must actually RENDER the all-learners response — a cohort
  // row has no pseudonym, so it appears by student id, and the count note says what happened.
  const user = userEvent.setup();
  listLearners
    .mockResolvedValueOnce(page([caseload("l1", "Aisha Binti Rahman")]))
    .mockResolvedValueOnce(page([caseload("l1", "Aisha Binti Rahman"), cohort("c1", "Student 0142")], 2));
  renderPage();
  await screen.findByText("Aisha Binti Rahman");

  await user.click(screen.getByRole("button", { name: /My caseload only/ }));

  expect(await screen.findByText("Student 0142")).toBeInTheDocument();
  expect(screen.getByText(/includes the anonymised DAS research cohort/)).toBeInTheDocument();
});

test("UT-9.11b: toggling back on returns to the assigned learners only", async () => {
  // The reverse move. If the button only ever narrowed the query and never widened the render
  // back, a therapist could not get home from the cohort.
  const user = userEvent.setup();
  listLearners
    .mockResolvedValueOnce(page([caseload("l1", "Aisha Binti Rahman")]))
    .mockResolvedValueOnce(page([caseload("l1", "Aisha Binti Rahman"), cohort("c1", "Student 0142")], 2))
    .mockResolvedValueOnce(page([caseload("l1", "Aisha Binti Rahman")], 1));
  renderPage();
  await screen.findByText("Aisha Binti Rahman");

  await user.click(screen.getByRole("button", { name: /My caseload only/ }));
  await screen.findByText("Student 0142");

  await user.click(screen.getByRole("button", { name: /My caseload only/ }));

  await waitFor(() => expect(lastQuery().caseload).toBe(true));
  await waitFor(() => expect(screen.queryByText("Student 0142")).not.toBeInTheDocument());
});

test("UT-9.10: a failed request can be retried into a recovery", async () => {
  // The error state offers a way out — without it, a transient failure strands the therapist
  // on a dead tab until they navigate away and back.
  const user = userEvent.setup();
  listLearners
    .mockRejectedValueOnce(new Error("boom"))
    .mockResolvedValueOnce(page([caseload("l1", "Aisha Binti Rahman")]));
  renderPage();
  await screen.findByText(/Failed to load learners: boom/);

  await user.click(screen.getByRole("button", { name: /Retry/ }));

  expect(await screen.findByText("Aisha Binti Rahman")).toBeInTheDocument();
  expect(screen.queryByText(/Failed to load learners/)).not.toBeInTheDocument();
});
