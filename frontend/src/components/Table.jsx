// Table.jsx — the learner list for the cluster selected in Graph's legend.
//
// Rendered only while a legend chip is active; Graph owns that state and passes
// the already-filtered rows. Names are buttons: clicking one asks Graph to open
// the learner's profile overlay.
//
// Columns follow the three axes currently on the plot, so the table always
// explains the picture above it. Nothing here names a skill — labels come from
// PLOT_SKILLS, so this survives the swap to the six literacy-skill columns.
//
// Props:
//   rows     {Array}    learner rows for one cluster (see Graph.jsx for the shape)
//   cluster  {string}   the cluster label, shown as the caption
//   axes     {Object}   { x, y, z } — PLOT_SKILLS keys, used as the score columns
//   onSelect {function} called with a row when its name is clicked

import { PLOT_SKILLS } from "../lib/constants";

const HEAD = "px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-brand-fg-muted";

export default function Table({ rows, cluster, axes, onSelect }) {
  if (!rows.length) {
    return (
      <p className="rounded-xl border border-dashed border-brand-border py-8 text-center text-sm text-brand-fg-muted">
        No learners in this cluster.
      </p>
    );
  }

  const columns = [axes.x, axes.y, axes.z];
  // Sorted by the X-axis skill so the table reads as a ranking rather than an
  // arbitrary list. Copied first — rows belongs to Graph.
  const sorted = [...rows].sort((a, b) => b[axes.x] - a[axes.x]);

  return (
    <div className="overflow-hidden rounded-xl border border-brand-border">
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-4 py-3">
        <h3 className="text-sm font-semibold text-brand-fg">{cluster}</h3>
        <p className="text-xs text-brand-fg-muted">
          {rows.length} learner{rows.length === 1 ? "" : "s"} · sorted by{" "}
          {PLOT_SKILLS[axes.x].label} · click a name for their profile
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] border-collapse text-sm">
          <thead>
            <tr className="border-y border-brand-border bg-brand-muted">
              <th scope="col" className={`${HEAD} w-12 text-left`}>#</th>
              <th scope="col" className={`${HEAD} text-left`}>Learner</th>
              <th scope="col" className={`${HEAD} text-left`}>Band</th>
              {columns.map((key) => (
                <th key={key} scope="col" className={`${HEAD} text-right`}>
                  {PLOT_SKILLS[key].label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, i) => (
              <tr
                key={row.id}
                className="border-b border-brand-border last:border-b-0 hover:bg-brand-muted"
              >
                <td className="px-4 py-2.5 text-brand-fg-muted tabular-nums">{i + 1}</td>
                <td className="px-4 py-2.5">
                  <button
                    type="button"
                    onClick={() => onSelect(row)}
                    className="rounded font-medium text-brand-fg underline decoration-brand-border underline-offset-4 transition-colors hover:text-brand-primary hover:decoration-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-ring/40"
                  >
                    {row.name}
                  </button>
                </td>
                <td className="px-4 py-2.5 text-brand-fg-muted">{row.bandLevel}</td>
                {columns.map((key) => (
                  <td key={key} className="px-4 py-2.5 text-right font-medium text-brand-fg tabular-nums">
                    {row[key]}
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
