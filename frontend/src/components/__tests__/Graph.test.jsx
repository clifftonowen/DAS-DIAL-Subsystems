// UNIT (frontend) — the cohort scatter's contract with /dashboard/clusters (UC2).
//
//     AB2.13  Graph.jsx (React)   UT-2.27 .. UT-2.36
//
// The React activation bar of the cohort-clustering flow, the counterpart to the backend
// bars AB2.7–AB2.12. Extends the PM3 UC2 test plan, whose UT-2.1 .. UT-2.11 cover only the
// generate-profile path — see backend/tests/unit/test_profiling_algorithm_cluster.py.
//
// The API module is mocked and Plotly is stubbed, so what is asserted here is the part
// Graph actually owns: that it builds its legend from whatever labels the backend sent,
// that its two controls project and filter without recolouring, and that the traces it
// hands Plotly carry the raw marks on ranges taken from PLOT_SKILLS.
//
// WHY PLOTLY IS MOCKED: it needs WebGL, which jsdom has no implementation of, and the
// gl3d bundle is ~1.6 MB to parse per test file. The mock captures the (data, layout)
// Graph passes to Plotly.react, which is the interesting half anyway — everything the
// component decides is in those arguments.

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Graph from "../Graph";
import { getCohortClusters } from "../../lib/api";

jest.mock("../../lib/api", () => ({ getCohortClusters: jest.fn() }));

// `mock`-prefixed so jest's hoisting of jest.mock() above the const still lets the factory
// close over it — any other name is rejected as an out-of-scope variable.
const mockPlotlyReact = jest.fn();
jest.mock(
  "plotly.js-gl3d-dist-min",
  () => ({ __esModule: true, default: { react: mockPlotlyReact, purge: jest.fn() } }),
  { virtual: true }
);

// The last figure Graph pushed to Plotly: [node, data, layout, config].
const lastFigure = () => mockPlotlyReact.mock.calls.at(-1);
const traceFor = (label) => lastFigure()[1].find((t) => t.name === label);
const colours = () =>
  Object.fromEntries(lastFigure()[1].map((t) => [t.name, t.marker.color]));
const plottedIds = () => lastFigure()[1].flatMap((t) => t.x);

const chip = (name) => screen.getByRole("radio", { name });

// The model-comparison caption. Scoped by role because "Cohort" is also the text of the scope
// chip, and an unscoped getByText would match both.
const models = async () => (await screen.findAllByRole("listitem"))[0].closest("ul");
const modelRow = (name) => within(document.querySelector("ul")).getByText(name).closest("li");

const learner = (id, band, cohort, over = {}) => ({
  id, cluster_band: band, cluster_cohort: cohort,
  band: "B4", band_group: "B", learner_id: null,
  writing_genre: "narrative_writing",
  phonics: 20, word_reading_accuracy: 8, word_spelling: 5, writing: 12, ...over,
});

const run = (scope, tier, over = {}) => ({
  scope, tier,
  features: ["phonics", "word_reading_accuracy", "word_spelling"],
  k: 4, best_silhouette: 0.4188,
  silhouette_by_k: { 2: 0.3663, 3: 0.3999, 4: 0.4188 },
  n_learners: 2858, ...over,
});

const RESPONSE = {
  learners: [
    learner("Student 0001", "B 2", "Cohort 2", { phonics: 12, word_spelling: 2, writing: 7 }),
    learner("Student 0002", "B 2", "Cohort 2", { phonics: 14, word_spelling: 1, writing: 9 }),
    learner("Student 0003", "B 3", "Cohort 3", { phonics: 41, word_spelling: 8, writing: 21 }),
  ],
  runs: [run("cohort", "Cohort", { k: 4, best_silhouette: 0.3645, n_learners: 5783 }),
         run("band", "B")],
  unclustered: { cohort: 0, band: 0 },
};

// Three bands, so the band filter has something to narrow. The cohort labels deliberately cut
// ACROSS bands — that is what the cohort model does, and it makes the two scopes tell apart.
const MIXED = {
  learners: [
    learner("S-A1", "A 1", "Cohort 1", { band: "A3", band_group: "A", phonics: 40 }),
    learner("S-A2", "A 2", "Cohort 2", { band: "A3", band_group: "A", phonics: 42 }),
    learner("S-B1", "B 1", "Cohort 1", { band: "B4", band_group: "B", phonics: 12 }),
    learner("S-B2", "B 2", "Cohort 3", { band: "B5", band_group: "B", phonics: 14 }),
    learner("S-C1", "C 1", "Cohort 3", { band: "C7", band_group: "C", phonics: 9 }),
  ],
  runs: [
    run("cohort", "Cohort", { k: 4, best_silhouette: 0.3645, n_learners: 5783 }),
    run("band", "A", { k: 5, best_silhouette: 0.4292, n_learners: 1717 }),
    run("band", "B", { k: 4, best_silhouette: 0.4188, n_learners: 2858 }),
    run("band", "C", { k: 2, best_silhouette: 0.341, n_learners: 1205 }),
  ],
  unclustered: { cohort: 0, band: 3 },
};

async function ready() {
  await waitFor(() => expect(mockPlotlyReact).toHaveBeenCalled());
}

beforeEach(() => {
  jest.clearAllMocks();
  getCohortClusters.mockResolvedValue(RESPONSE);
});

// ── loading ───────────────────────────────────────────────────────────────────
test("UT-2.27: loads the whole cohort in a single request", async () => {
  // The fan-out this replaced was one /learners call plus one profile call per learner —
  // 5,784 requests at cohort scale. Both clustering scopes ride in that one response, so
  // the toggle below never refetches either.
  render(<Graph onSelectLearner={jest.fn()} />);
  await ready();

  expect(getCohortClusters).toHaveBeenCalledTimes(1);
});

// ── legend ────────────────────────────────────────────────────────────────────
test("UT-2.27: builds the legend from the labels the backend sent, with counts", async () => {
  render(<Graph onSelectLearner={jest.fn()} />);

  expect(await screen.findByRole("button", { name: /Cohort 2/ })).toHaveTextContent("(2)");
  expect(screen.getByRole("button", { name: /Cohort 3/ })).toHaveTextContent("(1)");
});

test("UT-2.27: legend adapts to a different k without any code change", async () => {
  // k is chosen by the backend per model, so the component cannot assume a count.
  getCohortClusters.mockResolvedValue({
    ...RESPONSE,
    learners: [1, 2, 3, 4, 5].map((n) => learner(`S${n}`, "B 1", `Cohort ${n}`)),
  });
  render(<Graph onSelectLearner={jest.fn()} />);

  for (const n of [1, 2, 3, 4, 5]) {
    expect(await screen.findByRole("button", { name: new RegExp(`Cohort ${n}`) }))
      .toBeInTheDocument();
  }
});

// ── the scope toggle ──────────────────────────────────────────────────────────
test("UT-2.34: opens on the cohort model", async () => {
  // Four colours is the readable first impression; By band is what you opt into.
  render(<Graph onSelectLearner={jest.fn()} />);
  await ready();

  expect(chip("Cohort")).toBeChecked();
  expect(chip("By band")).not.toBeChecked();
  expect(lastFigure()[1].map((t) => t.name).sort()).toEqual(["Cohort 2", "Cohort 3"]);
});

test("UT-2.34: switching scope re-colours by the other model", async () => {
  const user = userEvent.setup();
  render(<Graph onSelectLearner={jest.fn()} />);
  await ready();

  await user.click(chip("By band"));

  await waitFor(() =>
    expect(lastFigure()[1].map((t) => t.name).sort()).toEqual(["B 2", "B 3"]));
  expect(chip("By band")).toBeChecked();
  // Same three learners, partitioned by a different model.
  expect(plottedIds()).toHaveLength(3);
});

test("UT-2.34: a selected cluster chip is cleared when the scope changes", async () => {
  // Its label belongs to the other model, so leaving it set would render a permanently
  // empty table with no visible way back.
  const user = userEvent.setup();
  render(<Graph onSelectLearner={jest.fn()} />);

  await user.click(await screen.findByRole("button", { name: /Cohort 2/ }));
  expect(screen.getByRole("table")).toBeInTheDocument();

  await user.click(chip("By band"));

  await waitFor(() => expect(screen.queryByRole("table")).not.toBeInTheDocument());
});

// ── the band filter ───────────────────────────────────────────────────────────
test("UT-2.35: filtering by band narrows the points and the legend", async () => {
  const user = userEvent.setup();
  getCohortClusters.mockResolvedValue(MIXED);
  render(<Graph onSelectLearner={jest.fn()} />);
  await ready();

  expect(plottedIds()).toHaveLength(5);

  await user.click(chip("A"));

  await waitFor(() => expect(plottedIds()).toHaveLength(2));
  // Band A holds Cohort 1 and Cohort 2; Cohort 3 is band B/C only and drops out.
  expect(lastFigure()[1].map((t) => t.name).sort()).toEqual(["Cohort 1", "Cohort 2"]);
});

test("UT-2.35: filtering by band NEVER changes a surviving point's colour", async () => {
  // The regression guard for the whole design. Colours are assigned by index into the sorted
  // label list, so deriving them from the FILTERED rows would renumber the palette on every
  // filter change and recolour the plot — which the header comment forbids. `palette` is
  // built from the unfiltered rows precisely to stop that.
  const user = userEvent.setup();
  getCohortClusters.mockResolvedValue(MIXED);
  render(<Graph onSelectLearner={jest.fn()} />);
  await ready();

  const before = colours();

  for (const band of ["A", "B", "C", "All"]) {
    await user.click(chip(band));
    await waitFor(() => expect(chip(band)).toBeChecked());
    for (const [label, colour] of Object.entries(colours())) {
      expect(colour).toBe(before[label]);
    }
  }

  expect(colours()).toEqual(before);   // back to All, nothing lost
});

test("UT-2.35: the band filter applies in the band scope too", async () => {
  const user = userEvent.setup();
  getCohortClusters.mockResolvedValue(MIXED);
  render(<Graph onSelectLearner={jest.fn()} />);
  await ready();

  await user.click(chip("By band"));
  await user.click(chip("B"));

  await waitFor(() =>
    expect(lastFigure()[1].map((t) => t.name).sort()).toEqual(["B 1", "B 2"]));
});

test("UT-2.35: a combination matching nobody says so instead of rendering an empty plot", async () => {
  const user = userEvent.setup();
  getCohortClusters.mockResolvedValue({
    ...MIXED,
    learners: MIXED.learners.filter((l) => l.band_group !== "C"),
  });
  render(<Graph onSelectLearner={jest.fn()} />);
  await ready();

  await user.click(chip("C"));

  expect(await screen.findByText(/No learner matches/)).toBeInTheDocument();
});

// ── the model comparison caption ──────────────────────────────────────────────
test("UT-2.28: lists every model's k and silhouette, not just the active one", async () => {
  // The comparison is the finding: the band models score better than the cohort fit because
  // the assessment paper differs by band. Showing all four is what makes the toggle
  // self-explanatory.
  getCohortClusters.mockResolvedValue(MIXED);
  render(<Graph onSelectLearner={jest.fn()} />);

  const caption = await models();
  for (const model of ["Cohort", "Band A", "Band B", "Band C"]) {
    expect(within(caption).getByText(model)).toBeInTheDocument();
  }
  // 0.3645 renders as "0.364" — toFixed rounds on the float, not the decimal literal. The
  // real cohort value is 0.3645, so this is what production shows.
  expect(within(caption).getByText("silhouette 0.364")).toBeInTheDocument();
  expect(within(caption).getByText("silhouette 0.429")).toBeInTheDocument();
  expect(within(caption).getByText("silhouette 0.341")).toBeInTheDocument();
});

test("UT-2.28: the caption marks the models that are actually colouring the plot", async () => {
  const user = userEvent.setup();
  getCohortClusters.mockResolvedValue(MIXED);
  render(<Graph onSelectLearner={jest.fn()} />);

  await models();   // wait for the caption to render

  // Cohort scope: the cohort model is active, the three band models are dimmed.
  expect(modelRow("Cohort")).not.toHaveClass("opacity-45");
  expect(modelRow("Band A")).toHaveClass("opacity-45");

  await user.click(chip("By band"));
  await waitFor(() => expect(modelRow("Band A")).not.toHaveClass("opacity-45"));
  expect(modelRow("Cohort")).toHaveClass("opacity-45");

  // Filtering to one band narrows which band models are active.
  await user.click(chip("A"));
  await waitFor(() => expect(modelRow("Band B")).toHaveClass("opacity-45"));
  expect(modelRow("Band A")).not.toHaveClass("opacity-45");
});

test("UT-2.28: reports k as chosen from a sweep, not configured", async () => {
  render(<Graph onSelectLearner={jest.fn()} />);

  const caption = await models();
  expect(within(caption).getAllByText("k=4 of 3").length).toBeGreaterThan(0);
});

// ── axes: projection only, never re-clustering ────────────────────────────────
test("UT-2.29: changing an axis re-projects the points but never recolours them", async () => {
  // Clustering is a property of the learner, fitted once in the backend. If a dropdown could
  // change a colour, the picture would be lying about what the clusters are.
  const user = userEvent.setup();
  render(<Graph onSelectLearner={jest.fn()} />);
  await ready();

  const before = colours();
  const xBefore = traceFor("Cohort 2").x;

  // "writing" is the one skill not already on an axis — the other three are disabled for X
  // precisely so a skill cannot be plotted twice.
  await user.selectOptions(screen.getByLabelText("X axis"), "writing");
  await waitFor(() => expect(traceFor("Cohort 2").x).not.toEqual(xBefore));

  expect(colours()).toEqual(before);
  expect(traceFor("Cohort 2").x).toEqual([7, 9]);   // now the writing marks
});

test("UT-2.30: axis ranges come from each skill's own rubric, not a shared 0-100", async () => {
  const user = userEvent.setup();
  render(<Graph onSelectLearner={jest.fn()} />);
  await ready();

  // Defaults are the first three PLOT_SKILLS: phonics /46, word reading /10, spelling /10.
  const { scene } = lastFigure()[2];
  expect(scene.xaxis.range).toEqual([0, 46]);
  expect(scene.yaxis.range).toEqual([0, 10]);

  await user.selectOptions(screen.getByLabelText("Y axis"), "writing");
  await waitFor(() => expect(lastFigure()[2].scene.yaxis.range).toEqual([0, 24]));
});

test("UT-2.30: plots the raw marks rather than rescaling them to a percentage", async () => {
  render(<Graph onSelectLearner={jest.fn()} />);
  await ready();

  expect(traceFor("Cohort 2").x).toEqual([12, 14]);   // phonics, as awarded
  expect(traceFor("Cohort 3").x).toEqual([41]);
});

test("UT-2.29: an axis cannot be selected on two axes at once", async () => {
  render(<Graph onSelectLearner={jest.fn()} />);
  const yAxis = await screen.findByLabelText("Y axis");

  // Phonics is on X, so it must be unpickable for Y.
  expect(within(yAxis).getByRole("option", { name: "Phonics" })).toBeDisabled();
  expect(within(yAxis).getByRole("option", { name: "Writing" })).not.toBeDisabled();
});

// ── unclustered learners ──────────────────────────────────────────────────────
test("UT-2.31: drops unclustered learners from the plot but says how many, per scope", async () => {
  // A learner with no band group has no band label but still has a cohort one, so the count
  // differs between the two views and a single number would be wrong for one of them.
  const user = userEvent.setup();
  getCohortClusters.mockResolvedValue({
    ...RESPONSE,
    learners: [...RESPONSE.learners,
               learner("Student 9999", null, "Cohort 2", { band_group: null })],
    unclustered: { cohort: 0, band: 1 },
  });
  render(<Graph onSelectLearner={jest.fn()} />);
  await ready();

  expect(plottedIds()).toHaveLength(4);          // cohort scope labels everyone
  expect(screen.queryByText(/hidden/)).not.toBeInTheDocument();

  await user.click(chip("By band"));

  expect(await screen.findByText(/1 hidden \(not clustered in this scope\)/)).toBeInTheDocument();
  await waitFor(() => expect(plottedIds()).toHaveLength(3));
});

// ── empty + error states ──────────────────────────────────────────────────────
test("UT-2.32: an empty cohort is an empty state, not a crash", async () => {
  getCohortClusters.mockResolvedValue({ learners: [], runs: [], unclustered: {} });
  render(<Graph onSelectLearner={jest.fn()} />);

  expect(await screen.findByText("Nothing to plot yet")).toBeInTheDocument();
  expect(await screen.findByText(/Run the cohort ingest/)).toBeInTheDocument();
  expect(mockPlotlyReact).not.toHaveBeenCalled();
});

test("UT-2.32: a failed request surfaces the reason", async () => {
  jest.spyOn(console, "error").mockImplementation(() => {});
  getCohortClusters.mockRejectedValue(new Error("503 Service Unavailable"));
  render(<Graph onSelectLearner={jest.fn()} />);

  expect(await screen.findByText(/503 Service Unavailable/)).toBeInTheDocument();
  console.error.mockRestore();
});

// ── the cluster table ─────────────────────────────────────────────────────────
test("UT-2.33: clicking a legend chip opens that cluster's table only", async () => {
  const user = userEvent.setup();
  render(<Graph onSelectLearner={jest.fn()} />);

  await user.click(await screen.findByRole("button", { name: /Cohort 2/ }));

  const table = screen.getByRole("table");
  expect(within(table).getByText("Student 0001")).toBeInTheDocument();
  expect(within(table).queryByText("Student 0003")).not.toBeInTheDocument();
});

test("UT-2.33: only a learner linked to the caseload is clickable", async () => {
  // GET /learners/{id} would 404 for a cohort-only student, so those names are plain text.
  const user = userEvent.setup();
  const onSelect = jest.fn();
  getCohortClusters.mockResolvedValue({
    ...RESPONSE,
    learners: [
      learner("Student 0001", "B 2", "Cohort 2", { learner_id: "uuid-1" }),
      learner("Student 0002", "B 2", "Cohort 2"),
    ],
  });
  render(<Graph onSelectLearner={onSelect} />);

  await user.click(await screen.findByRole("button", { name: /Cohort 2/ }));
  const table = screen.getByRole("table");

  expect(within(table).getByRole("button", { name: "Student 0001" })).toBeInTheDocument();
  expect(within(table).queryByRole("button", { name: "Student 0002" })).not.toBeInTheDocument();

  await user.click(within(table).getByRole("button", { name: "Student 0001" }));
  expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ learnerId: "uuid-1" }));
});
