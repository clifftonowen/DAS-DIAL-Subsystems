// ScoreHistoryChart.jsx — one learner's DIAL marks across semesters.
//
// The temporal half of the profile page, replacing the bar chart that could only ever show the
// current state. X is the semester; the two controls above the chart decide what Y means.
//
// METRIC — which of the four marks is plotted. Mirrors the axis pickers on the dashboard
//   scatter, and for the same reason: nothing here names a skill, so the four come from
//   PLOT_SKILLS and change with it.
//
// SCALE — raw mark or percentile, and they answer different questions:
//   Raw         the mark that was awarded, against that metric's own rubric (phonics /46).
//               What a therapist reads. Meaningless to compare ACROSS metrics.
//   Percentile  where the learner sat among everyone who took the same paper that semester.
//               The only figure comparable across the four, and the only one that survives a
//               learner changing band mid-history — phonics is out of 30 in A2 and 46 in A3, so
//               a raw line through a band change has a step in it that is not progress.
//
// A metric the learner was never assessed on renders the empty state rather than a flat line at
// zero — the same rule the radar chart applies when it omits an axis. Writing is absent for
// every band A learner, so this is the common case, not an edge one.
//
// Props:
//   history {Array}  [{ semester, band, phonics, ..., phonics_pct, ... }] oldest first
//   metric  {string} optional controlled value; uncontrolled if omitted
//   onMetricChange {function} optional

import { useMemo, useState } from "react";
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { DIAL_METRIC_COLORS, PLOT_SKILLS, SKILL_KEYS } from "../lib/constants";

const SCALES = [
  { key: "raw", label: "Raw mark" },
  { key: "percentile", label: "Percentile" },
];

const SELECT =
  "rounded-lg border border-brand-border bg-white px-2.5 py-1.5 text-xs font-medium " +
  "text-brand-fg outline-none focus:border-brand-primary focus:ring-1 focus:ring-brand-primary";

export default function ScoreHistoryChart({ history = [] }) {
  const [metric, setMetric] = useState(SKILL_KEYS[0]);
  const [scale, setScale] = useState("raw");

  const field = scale === "percentile" ? `${metric}_pct` : metric;
  const colour = DIAL_METRIC_COLORS[metric];
  const label = PLOT_SKILLS[metric]?.label ?? metric;

  // Only the sittings where this metric was actually assessed. A gap is not a zero, and
  // Recharts would otherwise join straight through a null as if the score had dropped.
  const points = useMemo(
    () =>
      history
        .filter((row) => row[field] !== null && row[field] !== undefined)
        .map((row) => ({ semester: row.semester, value: row[field], band: row.band })),
    [history, field]
  );

  // Raw marks sit on the metric's own rubric; percentiles are always 0-100. Fixed either way,
  // never data-driven — letting Recharts scale to the data would make a learner who moved from
  // 30 to 32 out of 46 look like they had transformed.
  const domain = scale === "percentile" ? [0, 100] : [0, PLOT_SKILLS[metric]?.max ?? 100];

  const controls = (
    <div className="mb-4 flex flex-wrap items-center gap-3">
      <label className="flex items-center gap-1.5">
        <span className="text-xs font-semibold text-brand-fg-muted">Metric</span>
        <select
          className={SELECT}
          value={metric}
          onChange={(e) => setMetric(e.target.value)}
          aria-label="Metric"
        >
          {SKILL_KEYS.map((key) => (
            <option key={key} value={key}>{PLOT_SKILLS[key].label}</option>
          ))}
        </select>
      </label>

      <label className="flex items-center gap-1.5">
        <span className="text-xs font-semibold text-brand-fg-muted">Scale</span>
        <select
          className={SELECT}
          value={scale}
          onChange={(e) => setScale(e.target.value)}
          aria-label="Scale"
        >
          {SCALES.map((s) => (
            <option key={s.key} value={s.key}>{s.label}</option>
          ))}
        </select>
      </label>
    </div>
  );

  if (points.length === 0) {
    return (
      <div className="flex flex-col">
        {controls}
        <div className="rounded-lg border border-dashed border-brand-border bg-brand-muted p-6 text-center">
          <p className="text-sm text-brand-fg">
            {history.length === 0
              ? "No assessment scores on record"
              : `${label} was never assessed`}
          </p>
          <p className="mt-2 text-xs text-brand-fg-muted">
            {history.length === 0
              ? "Scores arrive from the DAS workbook or an uploaded assessment."
              : "Writing is not administered to band A, so it is absent for many learners. Pick another metric."}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      {controls}

      <div className="h-[260px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 5, right: 12, bottom: 5, left: -18 }}>
            <CartesianGrid stroke="#EAECEF" vertical={false} />
            <XAxis
              dataKey="semester"
              tick={{ fill: "#6B727D", fontSize: 10 }}
              tickLine={false}
              axisLine={{ stroke: "#EAECEF" }}
            />
            <YAxis
              domain={domain}
              tick={{ fill: "#6B727D", fontSize: 10 }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              contentStyle={{ fontSize: 12, borderRadius: 8, borderColor: "#EAECEF" }}
              formatter={(value) => [
                scale === "percentile"
                  ? `${Math.round(value)}th percentile`
                  : `${value}/${PLOT_SKILLS[metric].max}`,
                label,
              ]}
              labelFormatter={(semester) => {
                const point = points.find((p) => p.semester === semester);
                return point?.band ? `${semester} · Band ${point.band}` : semester;
              }}
            />
            <Line
              type="monotone"
              dataKey="value"
              name={label}
              stroke={colour}
              strokeWidth={2}
              dot={{ r: 3, fill: colour }}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-brand-fg-muted">
        {points.length === 1
          ? `One sitting on record, so there is no trend to read yet — ${label} in ${points[0].semester}.`
          : scale === "percentile"
          ? "Ranked against everyone who sat the same paper that semester, so the line moves as the learner does rather than as the cohort around them changes."
          : `The mark awarded, out of ${PLOT_SKILLS[metric].max}. The rubric changes with the band, so compare across bands on the percentile scale instead.`}
      </p>
    </div>
  );
}
