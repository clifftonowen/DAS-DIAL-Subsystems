// Table.jsx — the learner list for the cluster selected in Graph's legend.
//
// Rendered only while a legend chip is active; Graph owns that state and passes
// the already-filtered rows. Names are buttons: clicking one asks Graph to open
// the learner's profile overlay.
//
// Columns follow the three axes currently on the plot, so the table always
// explains the picture above it. Nothing here names a skill — labels come from
// PLOT_SKILLS.
//
// A cluster can hold well over a thousand learners, so the body is capped at LIMIT
// rows and the caption says so. Rendering 1,300 <tr>s to a panel nobody scrolls to
// the bottom of costs a visible pause on every legend click.
//
// EVERY name is a link. Since the 2026-08-07 merge every learner — caseload or research cohort —
// is a row in `learners` with a uuid, so every one of them has a detail page. Cohort learners
// open read-only: they have no assessment records, so there is no profile to generate.
//
// Caseload learners are still listed FIRST and badged. They are a handful out of thousands,
// nothing about being on the caseload correlates with how they scored, and the LIMIT cap would
// otherwise bury the therapist's own learners in the truncated remainder.
//
// Props:
//   rows     {Array}    learner rows for one cluster (see Graph.jsx for the shape)
//   cluster  {string}   the cluster label, shown as the caption
//   axes     {Object}   { x, y, z } — PLOT_SKILLS keys, used as the score columns
//   onSelect {function} called with a row when its name is clicked

import { PLOT_SKILLS } from "../lib/constants";

const HEAD = "px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-brand-fg-muted";

const LIMIT = 100;

// "narrative_writing" -> "Narrative". Which genre a learner sat is only meaningful while
// Writing is on an axis, so the column appears with it.
const genreLabel = (genre) =>
  genre ? genre.replace(/_writing$/, "").replace(/^./, (c) => c.toUpperCase()) : "—";

export default function Table({ rows, cluster, axes, onSelect }) {
  if (!rows.length) {
    return (
      <p className="rounded-xl border border-dashed border-brand-border py-8 text-center text-sm text-brand-fg-muted">
        No learners in this cluster.
      </p>
    );
  }

  const columns = [axes.x, axes.y, axes.z];
  const showGenre = columns.includes("writing");

  // Sorted by the X-axis skill so the table reads as a ranking rather than an arbitrary list.
  // A learner not assessed on that skill sorts last: `null - 5` is NaN, and a comparator
  // returning NaN leaves the order undefined.
  const byScore = (a, b) => {
    const [x, y] = [a[axes.x], b[axes.x]];
    if (x == null) return y == null ? 0 : 1;
    if (y == null) return -1;
    return y - x;
  };

  // CASELOAD LEARNERS COME FIRST, and are never truncated away.
  //
  // A cluster holds well over a thousand learners and the body is capped at LIMIT. Being on the
  // caseload has nothing to do with how a learner scored, so under a plain score sort the
  // therapist's own learners land in the truncated 90% — the rows they most need to see are the
  // ones most likely to be missing.
  //
  // Copied first — `rows` belongs to Graph. Each group stays score-sorted internally, so the
  // ranking still reads correctly within it.
  const caseload = rows.filter((r) => r.onCaseload).sort(byScore);
  const cohortOnly = rows.filter((r) => !r.onCaseload).sort(byScore);
  const sorted = [...caseload, ...cohortOnly];
  const shown = sorted.slice(0, LIMIT);

  return (
    <div className="overflow-hidden rounded-xl border border-brand-border">
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-4 py-3">
        <h3 className="text-sm font-semibold text-brand-fg">{cluster}</h3>
        <p className="text-xs text-brand-fg-muted">
          {rows.length.toLocaleString()} learner{rows.length === 1 ? "" : "s"}
          {caseload.length > 0 && ` · ${caseload.length} on your caseload, listed first`}
          {shown.length < sorted.length && ` · ${LIMIT} shown`} · sorted by{" "}
          {PLOT_SKILLS[axes.x].label}
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] border-collapse text-sm">
          <thead>
            <tr className="border-y border-brand-border bg-brand-muted">
              <th scope="col" className={`${HEAD} w-12 text-left`}>#</th>
              <th scope="col" className={`${HEAD} text-left`}>Learner</th>
              <th scope="col" className={`${HEAD} text-left`}>Band</th>
              {showGenre && <th scope="col" className={`${HEAD} text-left`}>Genre</th>}
              {columns.map((key) => (
                <th key={key} scope="col" className={`${HEAD} text-right`}>
                  {PLOT_SKILLS[key].label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((row, i) => (
              <tr
                key={row.id}
                className="border-b border-brand-border last:border-b-0 hover:bg-brand-muted"
              >
                <td className="px-4 py-2.5 text-brand-fg-muted tabular-nums">{i + 1}</td>
                <td className="px-4 py-2.5">
                  {/* Every learner has a detail page — they all have a row in `learners` now.
                      A cohort learner's opens read-only, since they have no assessment records
                      and so nothing to generate a profile from. */}
                  <span className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => onSelect(row)}
                      className="rounded font-medium text-brand-fg underline decoration-brand-border underline-offset-4 transition-colors hover:text-brand-primary hover:decoration-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-ring/40"
                    >
                      {row.name}
                    </button>
                    {/* Marks the rows that carry a profile and the actions that go with it —
                        still the useful distinction now that everything is clickable. */}
                    {row.onCaseload && (
                      <span className="rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-semibold text-blue-700">
                        Caseload
                      </span>
                    )}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-brand-fg-muted">{row.bandLevel}</td>
                {showGenre && (
                  <td className="px-4 py-2.5 text-brand-fg-muted">{genreLabel(row.writingGenre)}</td>
                )}
                {columns.map((key) => (
                  <td key={key} className="px-4 py-2.5 text-right font-medium text-brand-fg tabular-nums">
                    {/* Null means not assessed on this skill, which is not the same as zero. */}
                    {row[key] ?? <span className="text-brand-fg-muted">—</span>}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
