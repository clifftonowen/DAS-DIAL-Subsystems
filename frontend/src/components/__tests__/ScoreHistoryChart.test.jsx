// UNIT (frontend) — the profile page's progress chart (UC2).
//
//     AB2.25  ScoreHistoryChart.jsx (React)   UT-2.66 .. UT-2.70
//
// Replaced SkillBars, which could only ever show the current state. Recharts is stubbed for the
// same reason it is in ProfileRadarChart.test.jsx: ResponsiveContainer measures a parent that is
// 0x0 in jsdom, so the real SVG never lays out. The stub records what the component asked to be
// plotted, which is the interesting half — everything the component decides is in those props.

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ScoreHistoryChart from "../ScoreHistoryChart";

jest.mock("recharts", () => ({
  __esModule: true,
  ResponsiveContainer: ({ children }) => <div data-testid="chart">{children}</div>,
  LineChart: ({ data, children }) => (
    <div
      data-testid="line"
      data-x={(data || []).map((d) => d.semester).join(",")}
      data-y={(data || []).map((d) => d.value).join(",")}
    >
      {children}
    </div>
  ),
  Line: () => null,
  XAxis: () => null,
  YAxis: ({ domain }) => <div data-testid="ydomain" data-domain={(domain || []).join(",")} />,
  CartesianGrid: () => null,
  Tooltip: () => null,
}));

// What the chart actually plotted.
const plotted = () => ({
  x: (screen.getByTestId("line").getAttribute("data-x") || "").split(",").filter(Boolean),
  y: (screen.getByTestId("line").getAttribute("data-y") || "").split(",").filter(Boolean),
});
const yDomain = () => screen.getByTestId("ydomain").getAttribute("data-domain");

const sitting = (semester, over = {}) => ({
  semester, band: "A2", band_group: "A",
  phonics: 20, word_reading_accuracy: 6, word_spelling: 5, writing: null,
  phonics_pct: 40, word_reading_accuracy_pct: 55, word_spelling_pct: 33, writing_pct: null,
  ...over,
});

const HISTORY = [
  sitting("2024 Sem 1", { phonics: 12, phonics_pct: 20 }),
  sitting("2025 Sem 1", { phonics: 20, phonics_pct: 40 }),
  sitting("2026 Sem 1", { phonics: 31, phonics_pct: 68 }),
];

describe("what gets plotted", () => {
  test("UT-2.66: opens on the first metric, raw, across every semester", async () => {
    render(<ScoreHistoryChart history={HISTORY} />);

    expect(plotted()).toEqual({
      x: ["2024 Sem 1", "2025 Sem 1", "2026 Sem 1"],
      y: ["12", "20", "31"],
    });
  });

  test("UT-2.67: the metric dropdown changes which mark is plotted", async () => {
    const user = userEvent.setup();
    render(<ScoreHistoryChart history={HISTORY} />);

    await user.selectOptions(screen.getByLabelText("Metric"), "word_reading_accuracy");

    expect(plotted().y).toEqual(["6", "6", "6"]);
  });

  test("UT-2.67: the scale dropdown switches raw marks for percentiles", async () => {
    // The two answer different questions — the awarded mark versus where it ranks — and only
    // the percentile survives a learner changing band mid-history.
    const user = userEvent.setup();
    render(<ScoreHistoryChart history={HISTORY} />);

    await user.selectOptions(screen.getByLabelText("Scale"), "percentile");

    expect(plotted().y).toEqual(["20", "40", "68"]);
  });
});

describe("the Y axis", () => {
  test("UT-2.68: raw marks use the metric's own rubric ceiling", async () => {
    // Fixed, never data-driven. Letting Recharts scale to the data would make a learner who
    // went from 30 to 32 out of 46 look like they had transformed.
    render(<ScoreHistoryChart history={HISTORY} />);

    expect(yDomain()).toBe("0,46");
  });

  test("UT-2.68: the ceiling follows the metric", async () => {
    const user = userEvent.setup();
    render(<ScoreHistoryChart history={HISTORY} />);

    await user.selectOptions(screen.getByLabelText("Metric"), "word_reading_accuracy");

    expect(yDomain()).toBe("0,10");
  });

  test("UT-2.68: percentiles are always 0-100 whatever the metric", async () => {
    const user = userEvent.setup();
    render(<ScoreHistoryChart history={HISTORY} />);

    await user.selectOptions(screen.getByLabelText("Scale"), "percentile");

    expect(yDomain()).toBe("0,100");
  });
});

describe("gaps and edges", () => {
  test("UT-2.69: a metric the learner never sat shows the empty state, not a zero line", async () => {
    // Writing is not administered to band A, so this is the common case. A flat line at zero
    // would claim they scored nothing on a paper they were never given.
    const user = userEvent.setup();
    render(<ScoreHistoryChart history={HISTORY} />);

    await user.selectOptions(screen.getByLabelText("Metric"), "writing");

    expect(screen.queryByTestId("line")).not.toBeInTheDocument();
    expect(screen.getByText(/Writing was never assessed/)).toBeInTheDocument();
  });

  test("UT-2.69: a semester with no mark is skipped, not joined through", async () => {
    // Recharts would otherwise draw straight through a null as if the score had dropped.
    render(
      <ScoreHistoryChart
        history={[
          sitting("2024 Sem 1", { phonics: 12 }),
          sitting("2025 Sem 1", { phonics: null }),
          sitting("2026 Sem 1", { phonics: 31 }),
        ]}
      />
    );

    expect(plotted().x).toEqual(["2024 Sem 1", "2026 Sem 1"]);
  });

  test("UT-2.70: one sitting renders a point and says there is no trend yet", async () => {
    render(<ScoreHistoryChart history={[sitting("2026 Sem 1", { phonics: 31 })]} />);

    expect(plotted().y).toEqual(["31"]);
    expect(screen.getByText(/One sitting on record/)).toBeInTheDocument();
  });

  test("UT-2.70: no history at all is an empty state, and the controls still work", async () => {
    render(<ScoreHistoryChart history={[]} />);

    expect(screen.getByText(/No assessment scores on record/)).toBeInTheDocument();
    // The dropdowns stay usable so the empty state does not trap the user on one metric.
    expect(screen.getByLabelText("Metric")).toBeEnabled();
  });
});
