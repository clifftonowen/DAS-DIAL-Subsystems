// UNIT (frontend) — the DIAL radar's contract with /learners/{id}/overview (UC2).
//
//     AB2.19  ProfileRadarChart.jsx (React)   UT-2.48 .. UT-2.52
//
// The React counterpart to the backend bar AB2.15 (LearnerOverviewService._metrics), which
// decides what `assessed` means; this bar checks that the chart honours it.
//
// WHAT IS ACTUALLY UNDER TEST. Recharts renders to SVG, which jsdom will not lay out (its
// ResponsiveContainer measures a parent that has no size here), so the polygon itself is not
// assertable and is not asserted. What IS the component's own logic, and is asserted:
//
//   * which axes exist — an unassessed paper must be DROPPED, not drawn at zero
//   * that the raw mark survives alongside the percentile, since the percentile is what the
//     radius can carry but the mark is what a therapist reads
//   * that the caption names the comparison population, so "68th percentile" is never read as
//     a cohort-wide claim when it is a rank within one band
//
// Three axes is the COMMON shape, not an edge case: writing is never administered to band A,
// so most band A learners have exactly three assessed marks.

import { render, screen } from "@testing-library/react";
import ProfileRadarChart from "../ProfileRadarChart";

// Recharts is stubbed wholesale. ResponsiveContainer measures a parent that is 0x0 in jsdom, so
// the real chart renders nothing useful anyway — and the axis names, which ARE the interesting
// output, are recorded here as data attributes rather than left to an SVG that never lays out.
// Everything else asserted below (the legend, the caption, the empty states) is the component's
// own markup and is untouched by this.
jest.mock("recharts", () => ({
  __esModule: true,
  ResponsiveContainer: ({ children }) => <div data-testid="chart">{children}</div>,
  RadarChart: ({ data, children }) => (
    <div data-testid="radar" data-axes={(data || []).map((d) => d.subject).join(",")}>
      {children}
    </div>
  ),
  PolarGrid: () => null,
  PolarAngleAxis: () => null,
  PolarRadiusAxis: () => null,
  Radar: () => null,
}));

// The axis labels the polygon was built from, in order.
const axes = () =>
  (screen.getByTestId("radar").getAttribute("data-axes") || "")
    .split(",")
    .filter(Boolean);

const metric = (key, label, raw, max, percentile) => ({
  key, label, raw, max, percentile, assessed: raw !== null && percentile !== null,
});

// A band B learner: every paper sat, including writing.
const ALL_FOUR = [
  metric("phonics", "Phonics", 31, 46, 68.4),
  metric("word_reading_accuracy", "Word Reading", 7, 10, 41),
  metric("word_spelling", "Word Spelling", 5, 10, 33.2),
  metric("writing", "Writing", 12, 24, 55),
];

// A band A learner: writing is never administered to band A.
const NO_WRITING = [
  ...ALL_FOUR.slice(0, 3),
  metric("writing", "Writing", null, 24, null),
];

describe("assessed axes", () => {
  test("UT-2.48: plots every mark the learner actually sat", () => {
    render(<ProfileRadarChart metrics={ALL_FOUR} band="B" />);

    expect(axes()).toEqual(["Phonics", "Word Reading", "Word Spelling", "Writing"]);
  });

  test("UT-2.49: a paper the learner never sat is omitted, not drawn at zero", () => {
    // The clinical claim this component must not make. A zero on the writing axis says the
    // learner scored nothing on a paper band A is never given.
    render(<ProfileRadarChart metrics={NO_WRITING} band="A" />);

    expect(axes()).toEqual(["Phonics", "Word Reading", "Word Spelling"]);
    expect(axes()).not.toContain("Writing");
    expect(screen.getByText(/Writing not assessed/)).toBeInTheDocument();
    expect(screen.getByText(/omitted rather than drawn at zero/)).toBeInTheDocument();
  });

  test("UT-2.49: three assessed marks still render a chart", () => {
    // Band A is most of the cohort, so this path must not fall through to the empty state.
    render(<ProfileRadarChart metrics={NO_WRITING} band="A" />);

    expect(screen.getByTestId("radar")).toBeInTheDocument();
    expect(screen.queryByText(/Not enough assessed skills/)).not.toBeInTheDocument();
  });
});

describe("the numbers on screen", () => {
  test("UT-2.50: the awarded mark is shown next to its rank", () => {
    // The percentile is what the radius can carry, but "31/46" is what the therapist reads.
    // Showing only the rank would hide the mark the learner was actually given.
    render(<ProfileRadarChart metrics={ALL_FOUR} band="B" />);

    expect(screen.getByText("31/46")).toBeInTheDocument();
    expect(screen.getByText(/68th percentile/)).toBeInTheDocument();
  });

  test("UT-2.50: percentiles are rounded to a whole rank", () => {
    // 68.4 -> "68th". A decimal place on a rank against a few thousand people implies a
    // precision that coarse rubric marks do not carry.
    render(<ProfileRadarChart metrics={ALL_FOUR} band="B" />);

    expect(screen.queryByText(/68\.4/)).not.toBeInTheDocument();
  });

  test("UT-2.51: the caption names the population the rank is against", () => {
    // Without this the reader takes "68th percentile" for a cohort-wide claim. It is not: the
    // bands sit different papers, which is the entire reason the rank is band-scoped.
    render(<ProfileRadarChart metrics={ALL_FOUR} band="B" />);

    expect(screen.getByText(/Ranked against band B/)).toBeInTheDocument();
    expect(screen.getByText(/same paper/)).toBeInTheDocument();
  });
});

describe("empty and near-empty", () => {
  test("UT-2.52: an unlinked learner gets a message, not a broken chart", () => {
    render(<ProfileRadarChart metrics={[]} />);

    expect(screen.getByText(/No DIAL assessment marks/)).toBeInTheDocument();
  });

  test("UT-2.52: fewer than three axes lists the numbers instead of drawing a polygon", () => {
    // Two points is a line and one is a dot. Rendering either as a "radar" would present a
    // shape that reads as a profile but is not one.
    const two = [
      metric("phonics", "Phonics", 31, 46, 68.4),
      metric("word_reading_accuracy", "Word Reading", 7, 10, 41),
      metric("word_spelling", "Word Spelling", null, 10, null),
      metric("writing", "Writing", null, 24, null),
    ];

    render(<ProfileRadarChart metrics={two} band="A" />);

    expect(screen.getByText(/Not enough assessed skills/)).toBeInTheDocument();
    expect(screen.getByText(/Phonics: 31\/46/)).toBeInTheDocument();
  });

  test("UT-2.52: an unknown band group still reads sensibly", () => {
    // band_group is null for the handful of learners whose band is missing.
    render(<ProfileRadarChart metrics={ALL_FOUR} />);

    expect(screen.getByText(/Ranked against their band/)).toBeInTheDocument();
  });
});
