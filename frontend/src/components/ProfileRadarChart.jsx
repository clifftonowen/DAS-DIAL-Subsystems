// ProfileRadarChart.jsx — the DIAL assessment radar on LearnerDetailPage.
//
// Plots the learner's four DIAL marks as PERCENTILES WITHIN THEIR BAND GROUP, served ready by
// GET /learners/{id}/overview.
//
// WHY PERCENTILES AND NOT THE MARKS. A radar shares one radius across every axis, so whatever
// it plots has to mean the same thing on all four. The raw marks do not: phonics is out of 46
// and word reading out of 10. Percent-of-max does not either, because the paper itself differs
// by band — phonics tops out at 25 in band A1, 30 in A2 and 46 in A3 — so 67% of an A1 paper
// and 67% of an A3 paper are different achievements that one radius would draw identically.
// Ranking within the learner's own band group compares them against the population that sat
// their paper. The legend below still carries the mark that was actually awarded, because that
// is the number a therapist reads.
//
// UNASSESSED AXES ARE DROPPED, NOT ZEROED. Writing is never administered to band A, so most
// band A learners have no writing mark at all. Plotting them at zero would state that they
// scored nothing on a paper they never sat; Recharts also cannot draw a sensible polygon
// through a null. The axis is removed and the caption says which one and why. Three axes is
// therefore the COMMON shape here, not an edge case.
//
// Props:
//   metrics {Array}  [{ key, label, raw, max, percentile, assessed }] from the overview endpoint
//   band    {string} the band group the percentiles are ranked against, for the caption

import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer } from "recharts";
import { DIAL_METRIC_COLORS } from "../lib/constants";

// A radar needs a polygon; two axes is a line and one is a point. Below this we show the
// numbers instead of drawing something that reads as a chart but is not one.
const MIN_AXES = 3;

// "68.4" -> "68th". The percentile is the headline number, and a decimal place on a rank
// against a few thousand people implies precision the coarse rubric marks do not carry.
function ordinal(value) {
  const n = Math.round(value);
  const suffix = n % 100 >= 11 && n % 100 <= 13
    ? "th"
    : { 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th";
  return `${n}${suffix}`;
}

// "31/46" — trailing .0 stripped, since every DIAL mark is a whole-number rubric score.
const mark = ({ raw, max }) => `${Number(raw)}/${Number(max)}`;

export default function ProfileRadarChart({ metrics = [], band }) {
  const plotted = metrics.filter((m) => m.assessed);
  const omitted = metrics.filter((m) => !m.assessed);
  const against = band ? `band ${band}` : "their band";

  if (plotted.length < MIN_AXES) {
    return (
      <div className="rounded-lg border border-dashed border-brand-border bg-brand-muted p-6 text-center">
        <p className="text-sm text-brand-fg">
          {plotted.length === 0
            ? "No DIAL assessment marks for this learner."
            : "Not enough assessed skills to plot a profile."}
        </p>
        {plotted.length > 0 && (
          <ul className="mt-3 flex flex-col gap-1 text-xs text-brand-fg-muted">
            {plotted.map((m) => (
              <li key={m.key}>
                {m.label}: {mark(m)} · {ordinal(m.percentile)} percentile in {against}
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  const data = plotted.map((m) => ({
    subject: m.label,
    percentile: m.percentile,
    color: DIAL_METRIC_COLORS[m.key],
  }));

  return (
    <div className="flex flex-col h-full">
      {/* ── Chart ── */}
      <div className="h-[300px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart cx="50%" cy="50%" outerRadius="70%" data={data}>
            <PolarGrid stroke="#EAECEF" />
            <PolarAngleAxis
              dataKey="subject"
              tick={{ fill: "#6B727D", fontSize: 10, fontWeight: 500 }}
            />
            {/* Fixed 0-100 with no tick labels: a percentile axis is always 0-100, and letting
                Recharts scale it to the data would make a learner at the 40th-45th percentile
                on everything look like a wildly uneven profile. */}
            <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
            <Radar
              name="Percentile"
              dataKey="percentile"
              stroke="#FF2E45"
              strokeWidth={2}
              fill="#FF2E45"
              fillOpacity={0.12}
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>

      {/* ── Legend — the mark that was actually awarded, next to its rank ── */}
      <div className="mt-4 flex flex-col gap-1.5 text-[11px] font-medium text-brand-fg-muted">
        {plotted.map((m) => (
          <div key={m.key} className="flex items-center gap-1.5">
            <div
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ backgroundColor: DIAL_METRIC_COLORS[m.key] }}
            />
            <span>
              {m.label}: <span className="text-brand-fg">{mark(m)}</span> ·{" "}
              {ordinal(m.percentile)} percentile
            </span>
          </div>
        ))}
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-brand-fg-muted">
        Ranked against {against}, which is the population that sat the same paper.
        {omitted.length > 0 && (
          <>
            {" "}
            {omitted.map((m) => m.label).join(", ")} not assessed — that axis is omitted rather
            than drawn at zero.
          </>
        )}
      </p>
    </div>
  );
}
