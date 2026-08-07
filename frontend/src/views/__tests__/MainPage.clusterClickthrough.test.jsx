// UNIT (frontend) — the cohort scatter's click-through to LearnerDetailPage (UC2).
//
//     AB2.20  MainPage.jsx (React)   UT-2.53 .. UT-2.55
//
// The one path no other test covers END TO END: legend chip -> cluster table -> a learner's
// name -> the profile overlay. Graph.test.jsx stops at "the name is a button and
// onSelectLearner fires"; this carries on into MainPage, which owns the Modal, and proves the
// overlay mounts LearnerDetailPage against the uuid rather than the anonymised student id.
//
// WHY IT IS WORTH ITS OWN FILE. The chain crosses four components and carries two identifiers
// for the same person: the cluster table LABELS a research learner by `student_id`
// ("Student 0142"), but the profile is FETCHED by `id` (a uuid). Passing the wrong one opens an
// overlay stuck on "Learner not found", which reads as a backend fault rather than a wiring
// one. Every link in the chain is individually tested; the handover between them was not.

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import MainPage from "../MainPage";
import * as api from "../../lib/api";

// A factory, not an automock: lib/api imports lib/supabase, which calls createClient() at
// module scope and throws without VITE_SUPABASE_URL. An automock would still load the real
// module to read its shape, so the suite would die before the first test.
jest.mock("../../lib/api", () => ({
  getDashboardStats: jest.fn(),
  getDashboardTasks: jest.fn(),
  getDashboardEvents: jest.fn(),
  getCohortClusters: jest.fn(),
  getLearner: jest.fn(),
  getLearnerOverview: jest.fn(),
  getLearnerActivities: jest.fn(),
  generateProfile: jest.fn(),
  // Not exercised here, but LearnerDetailPage imports it — an absent key makes the factory
  // return undefined and the overlay dies on "generateActivity is not a function".
  generateActivity: jest.fn(),
}));

// Plotly needs WebGL, which jsdom has no implementation of. See Graph.test.jsx.
jest.mock(
  "plotly.js-gl3d-dist-min",
  () => ({ __esModule: true, default: { react: jest.fn(), purge: jest.fn() } }),
  { virtual: true }
);

const CASELOAD_UUID = "11111111-1111-1111-1111-111111111111";

const cohortStudent = (studentId, over = {}) => ({
  id: `uuid-${studentId}`, student_id: studentId, pseudonym: "", on_caseload: false,
  cluster_band: "B 2", cluster_cohort: "Cohort 2",
  band: "B4", band_group: "B", writing_genre: "narrative_writing",
  phonics: 20, word_reading_accuracy: 8, word_spelling: 5, writing: 12, ...over,
});

beforeEach(() => {
  jest.clearAllMocks();

  api.getDashboardStats.mockResolvedValue({ total_learners: 10, needs_profiling: 3, flagged: 2 });
  api.getDashboardTasks.mockResolvedValue([]);
  api.getDashboardEvents.mockResolvedValue([]);
  api.getCohortClusters.mockResolvedValue({
    learners: [
      cohortStudent("Student 0142", { id: CASELOAD_UUID,
                                      pseudonym: "Aisha Binti Rahman", on_caseload: true }),
      cohortStudent("Student 0001"),
    ],
    runs: [],
    unclustered: { cohort: 0, band: 0 },
  });

  // What LearnerDetailPage loads once the overlay mounts.
  api.getLearner.mockResolvedValue({
    id: CASELOAD_UUID, pseudonym: "Aisha Binti Rahman", band: "A2", band_group: "A",
    tier: "Tier 2", on_caseload: true,
  });
  api.getLearnerActivities.mockResolvedValue([]);
  api.getLearnerOverview.mockResolvedValue({
    learner_id: CASELOAD_UUID, pseudonym: "Aisha Binti Rahman", on_caseload: true,
    metrics: [], history: [], band_group: "A",
  });
});

const openCluster = async (user) => {
  await user.click(await screen.findByRole("button", { name: /Cohort 2/ }));
  return screen.getByRole("table");
};

const renderPage = () =>
  render(
    <MemoryRouter>
      <MainPage />
    </MemoryRouter>
  );

test("UT-2.53: clicking a caseload learner opens the profile overlay", async () => {
  const user = userEvent.setup();
  renderPage();

  const table = await openCluster(user);
  await user.click(within(table).getByRole("button", { name: "Aisha Binti Rahman" }));

  // Scoped to the dialog: the name is also still on screen in the table underneath, so an
  // unscoped query matches twice and proves nothing about the overlay.
  const dialog = await screen.findByRole("dialog");
  expect(await within(dialog).findByRole("heading", { name: "Aisha Binti Rahman" }))
    .toBeInTheDocument();
});

test("UT-2.54: the overlay is fetched by the caseload uuid, not the cohort student id", async () => {
  // THE MISMATCH THIS GUARDS. The graph plots anonymised ids ("Student 0142"); GET
  // /learners/{id} takes a uuid and would 404 on one. Passing the row's own `id` here would
  // open an overlay stuck on "Learner not found" — which reads as a backend fault, not a
  // wiring one.
  const user = userEvent.setup();
  renderPage();

  const table = await openCluster(user);
  await user.click(within(table).getByRole("button", { name: "Aisha Binti Rahman" }));

  await screen.findByRole("dialog");
  expect(api.getLearner).toHaveBeenCalledWith(CASELOAD_UUID);
  expect(api.getLearner).not.toHaveBeenCalledWith("Student 0142");
});

test("UT-2.55: a research-cohort learner opens too, by their uuid", async () => {
  // They are a row in `learners` like anyone else, with the same four marks, so their page
  // offers everything a caseload learner's does. Asserted from MainPage because it owns the
  // Modal: if it still guarded on a caseload flag, the row would be a link that opens nothing.
  const user = userEvent.setup();
  api.getLearner.mockResolvedValue({
    id: "uuid-Student 0001", student_id: "Student 0001", pseudonym: "",
    band: "B4", band_group: "B", on_caseload: false,
  });
  api.getLearnerOverview.mockResolvedValue({
    learner_id: "uuid-Student 0001", pseudonym: "", on_caseload: false,
    metrics: [], history: [], band_group: "B",
  });
  renderPage();

  const table = await openCluster(user);
  await user.click(within(table).getByRole("button", { name: "Student 0001" }));

  expect(await screen.findByRole("dialog")).toBeInTheDocument();
  expect(api.getLearner).toHaveBeenCalledWith("uuid-Student 0001");
});
