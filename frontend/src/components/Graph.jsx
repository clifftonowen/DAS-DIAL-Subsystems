// Graph.jsx — Cohort skills scatter for the main dashboard.
//
// Every learner is one point in a rotatable 3D scatter: the three dropdowns pick
// which skill sits on X, Y and Z. No skill is named anywhere in this file — the
// dropdown options, the default axes and the row-building loop are all generated
// from constants.PLOT_SKILLS, so re-pointing that map at the six literacy-skill
// columns (once they exist in Supabase) changes this UI without touching it.
//
// Points are coloured by cluster, the
// legend lists those clusters, and clicking a legend chip opens the Table of that
// cluster's learners.
//
// The legend is derived from whatever distinct cluster labels the rows carry — it
// is never a fixed list. The backend picks k itself (best silhouette over k = 2..10),
// so the cluster count is not knowable here.
//
// TWO CONTROLS BESIDES THE AXES:
//   scope       which of the two stored clusterings colours the points — one cohort-wide
//               model, or one model per band group. Both ride in the same response.
//   bandFilter  restricts the plot to one band group, in EITHER scope. Filtering the
//               cohort view to a single band is what makes the phonics confound visible:
//               the high-phonics cluster is almost entirely band A3.
//
// Clustering is a property of the learner, not of the current view: changing an axis or the
// band filter re-projects or hides points and must NEVER change their colours. That is why
// `palette` below is built from the unfiltered rows. Changing scope is the one exception —
// it selects a different model, so different colours are correct.
//
// The labels arrive already assigned from GET /dashboard/clusters — nothing here recomputes
// them.
//
// WHY PLOTLY DIRECTLY, NOT react-plotly.js: the wrapper adds a dependency to
// re-render a chart we only ever redraw on three state changes. The gl3d partial
// bundle (1.7 MB unpacked, vs 4.9 MB for the full plotly build) carries scatter3d
// and nothing we don't use.
//
// NOTE: point hover is deliberately disabled (hoverinfo: "skip"). Per-learner
// readouts stop being useful once the cohort is large, and skipping them means
// Plotly does no per-point hit-testing on mouse move. Identity lives in the table.

import { useState, useEffect, useMemo, useRef } from "react";
import Card from "./Card";
import Table from "./Table";
import { getCohortClusters } from "../lib/api";
import {
  BAND_GROUPS, CLUSTER_SCOPES, PLOT_SKILLS, SKILL_KEYS, clusterColor,
} from "../lib/constants";

const AXES = [
  { key: "x", label: "X axis" },
  { key: "y", label: "Y axis" },
  { key: "z", label: "Z axis" },
];

const AXIS_FONT = { color: "#6B727D", size: 11, family: "Poppins, system-ui, sans-serif" };

const skillLabel = (key) => PLOT_SKILLS[key]?.label ?? key;

// Props:
//   onSelectLearner {function} called with a row when a name in the cluster table
//     is clicked. Graph does not open the profile itself — MainPage owns that, so
//     this component never imports a view.
export default function Graph({ onSelectLearner }) {
  // Derived from PLOT_SKILLS rather than named literally, so swapping that map for
  // the six literacy skills needs no edit here.
  const [axes, setAxes] = useState(() => ({
    x: SKILL_KEYS[0],
    y: SKILL_KEYS[1],
    z: SKILL_KEYS[2],
  }));
  const [rows, setRows] = useState([]);
  const [runs, setRuns] = useState([]);
  const [skipped, setSkipped] = useState({});
  const [activeCluster, setActiveCluster] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  // Cohort first: four colours is the readable first impression. See CLUSTER_SCOPES.
  const [scope, setScope] = useState(CLUSTER_SCOPES[0].key);
  const [bandFilter, setBandFilter] = useState(null);   // null = all bands

  useEffect(() => {
    async function loadCohort() {
      try {
        // One request for the whole cohort. This replaced a /learners call followed by one
        // /learners/{id}/profiles per learner — at cohort scale (5,783) that was 5,784
        // requests, and the clusters are precomputed columns anyway.
        const { learners = [], runs: runList = [], unclustered = {} } = await getCohortClusters();

        // Every learner is kept here, both labels and all. Which ones are plottable depends
        // on the scope and band filter, and those can change without another request — so the
        // filtering happens in `visible` below, not at load.
        const built = learners.map((learner) => {
          const row = {
            id: learner.id,
            name: learner.id,          // the cohort is anonymised — the id IS the name
            learnerId: learner.learner_id ?? null,
            bandLevel: learner.band || "—",
            bandGroup: learner.band_group ?? null,
            writingGenre: learner.writing_genre ?? null,
            clusterBand: learner.cluster_band ?? null,
            clusterCohort: learner.cluster_cohort ?? null,
          };
          // Raw marks, each on its own rubric — see PLOT_SKILLS. A skill the learner was
          // not assessed on stays null so Plotly leaves a gap instead of drawing a zero.
          SKILL_KEYS.forEach((key) => {
            const value = learner[PLOT_SKILLS[key].field];
            row[key] = value ?? null;
          });
          return row;
        });

        setRows(built);
        setRuns(runList);
        setSkipped(unclustered);
      } catch (err) {
        console.error("Failed to load cohort skills", err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    loadCohort();
  }, []);

  const clusterField = CLUSTER_SCOPES.find((s) => s.key === scope).field;

  // Label -> colour, built from EVERY row in the active scope rather than the visible ones.
  // Colour is therefore a property of the cluster, not of what happens to be on screen: band
  // A's points keep their colours when you filter to band B and back. Deriving this from the
  // filtered rows instead would renumber the palette on every filter change and recolour the
  // whole plot, which is exactly what the header comment forbids.
  const palette = useMemo(() => {
    const labels = [...new Set(rows.map((r) => r[clusterField]).filter(Boolean))].sort();
    return new Map(labels.map((label, i) => [label, clusterColor(i)]));
  }, [rows, clusterField]);

  // The rows actually plotted, with the active scope's label resolved onto `cluster` so
  // Scatter3D and Table stay unaware that there is more than one clustering.
  const visible = useMemo(
    () =>
      rows
        .filter((r) => r[clusterField] && (!bandFilter || r.bandGroup === bandFilter))
        .map((r) => ({ ...r, cluster: r[clusterField] })),
    [rows, clusterField, bandFilter]
  );

  // The legend, the plot's traces and the table filter all read off this one array,
  // so nothing below assumes how many clusters there are.
  const series = useMemo(() => {
    const labels = [...new Set(visible.map((r) => r.cluster))].sort();
    return labels.map((label) => ({
      label,
      color: palette.get(label),
      count: visible.filter((r) => r.cluster === label).length,
    }));
  }, [visible, palette]);

  // A selected chip can vanish under a scope switch (its label belongs to the other model) or
  // a band filter. Leaving it set would render a permanently empty table with no way back.
  useEffect(() => {
    if (activeCluster && !series.some((s) => s.label === activeCluster)) setActiveCluster(null);
  }, [series, activeCluster]);

  const selectAxis = (axis, skill) => setAxes((cur) => ({ ...cur, [axis]: skill }));

  // Which models are colouring the plot right now — the caption dims the rest.
  const isActiveRun = (run) =>
    run.scope === scope && (scope === "cohort" || !bandFilter || run.tier === bandFilter);

  const hidden = (skipped?.[scope] ?? 0);

  return (
    <Card className="flex flex-col gap-4">
      {/* ── Clustering scope + band filter ──
          Chip styling matches the cluster legend below rather than Button.jsx, whose
          min-h-11 is far too tall for a control strip sitting above the axis pickers. */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <Chips
          label="Clustering"
          options={CLUSTER_SCOPES.map((s) => ({ value: s.key, text: s.label }))}
          value={scope}
          onChange={setScope}
          disabled={loading || !!error}
        />
        <Chips
          label="Band"
          options={[
            { value: null, text: "All" },
            ...BAND_GROUPS.map((b) => ({ value: b, text: b })),
          ]}
          value={bandFilter}
          onChange={setBandFilter}
          disabled={loading || !!error}
        />
      </div>

      {/* ── Axis pickers — one skill per axis, kept distinct ── */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {AXES.map(({ key, label }) => (
          <label key={key} className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold text-brand-fg-muted">{label}</span>
            <select
              value={axes[key]}
              onChange={(e) => selectAxis(key, e.target.value)}
              disabled={loading || !!error}
              className="rounded-lg border border-brand-border bg-white px-3 py-2 text-sm font-medium text-brand-fg outline-none focus:border-brand-primary focus:ring-1 focus:ring-brand-primary disabled:opacity-50"
            >
              {SKILL_KEYS.map((skill) => (
                <option
                  key={skill}
                  value={skill}
                  // Already plotted on one of the other two axes.
                  disabled={skill !== axes[key] && Object.values(axes).includes(skill)}
                >
                  {PLOT_SKILLS[skill].label}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>

      {loading ? (
        <div className="flex h-[420px] items-center justify-center">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-brand-border border-t-brand-primary" />
        </div>
      ) : error ? (
        <p className="py-10 text-center text-sm text-red-600">
          Failed to load cohort skills: {error}
        </p>
      ) : visible.length === 0 ? (
        <div className="rounded-xl border border-dashed border-brand-border bg-brand-muted p-10 text-center">
          <h3 className="text-sm font-medium text-brand-fg">Nothing to plot yet</h3>
          <p className="mt-2 text-sm text-brand-fg-muted">
            {rows.length === 0
              ? "No learner has been clustered yet. Run the cohort ingest to see them here."
              : "No learner matches this combination of clustering scope and band."}
          </p>
        </div>
      ) : (
        <>
          <Scatter3D rows={visible} series={series} axes={axes} activeCluster={activeCluster} />

          <p className="text-center text-xs text-brand-fg-muted">
            Drag to rotate · scroll to zoom
            {` · ${visible.length.toLocaleString()} learner${visible.length === 1 ? "" : "s"} shown`}
            {hidden > 0 &&
              ` · ${hidden} hidden (not clustered in this scope)`}
          </p>

          {/* ── How k was chosen, for every model ──
              k is derived, not configured: each model picks its own k as the best silhouette
              over a 2..10 sweep. All four are listed rather than just the active one, because
              the comparison is the finding — the band models score better than the cohort fit
              precisely because the assessment paper differs by band. Inactive rows are dimmed
              rather than hidden so the toggle explains itself. */}
          {runs.length > 0 && (
            <ul className="mx-auto flex flex-col gap-0.5 text-xs text-brand-fg-muted">
              {runs.map((run) => {
                const active = isActiveRun(run);
                return (
                  <li
                    key={`${run.scope}-${run.tier}`}
                    className={`flex flex-wrap justify-center gap-x-2 tabular-nums ${
                      active ? "text-brand-fg" : "opacity-45"
                    }`}
                  >
                    <span className={active ? "font-semibold" : "font-medium"}>
                      {run.scope === "cohort" ? "Cohort" : `Band ${run.tier}`}
                    </span>
                    <span>{`k=${run.k} of ${Object.keys(run.silhouette_by_k || {}).length}`}</span>
                    <span>{`silhouette ${run.best_silhouette.toFixed(3)}`}</span>
                    <span>{`n=${run.n_learners.toLocaleString()}`}</span>
                  </li>
                );
              })}
            </ul>
          )}

          {/* ── Clickable cluster legend ──
              Plotly's own legend is suppressed below: clicking it toggles trace
              visibility, which would fight the click-to-open-table behaviour. */}
          <div className="flex flex-wrap justify-center gap-2">
            {series.map(({ label, color, count }) => {
              const isActive = activeCluster === label;
              return (
                <button
                  key={label}
                  type="button"
                  aria-pressed={isActive}
                  onClick={() => setActiveCluster((cur) => (cur === label ? null : label))}
                  className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors ${
                    isActive
                      ? "border-brand-primary bg-brand-muted text-brand-fg"
                      : "border-brand-border bg-white text-brand-fg-muted hover:bg-brand-muted"
                  }`}
                >
                  <span
                    className="h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ backgroundColor: color }}
                  />
                  {label}
                  <span className="font-medium opacity-70">({count})</span>
                </button>
              );
            })}
          </div>

          {/* `visible`, not `rows`: only those carry a resolved `cluster` for the active
              scope, and the table must agree with the plot about who is on screen. */}
          {activeCluster && (
            <Table
              rows={visible.filter((r) => r.cluster === activeCluster)}
              cluster={activeCluster}
              axes={axes}
              onSelect={onSelectLearner}
            />
          )}
        </>
      )}
    </Card>
  );
}

// ── A labelled row of mutually-exclusive chips ───────────────────────────────
// Used for both the clustering scope and the band filter. A radiogroup rather than a <select>
// because there are only two to four options and both are switched constantly while reading
// the plot — a dropdown would cost two clicks each time.
//
// `value` is compared with ===, so an option value of null (the band filter's "All") works
// without a sentinel string.
//
// Props:
//   label    {string}   the caption to the left of the row
//   options  {Array}    [{ value, text }]
//   value    {*}        the currently selected option's value
//   onChange {function} called with the newly selected value
function Chips({ label, options, value, onChange, disabled }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-semibold text-brand-fg-muted">{label}</span>
      <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-1.5">
        {options.map((option) => {
          const selected = option.value === value;
          return (
            <button
              key={String(option.value)}
              type="button"
              role="radio"
              aria-checked={selected}
              disabled={disabled}
              onClick={() => onChange(option.value)}
              className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors disabled:opacity-50 ${
                selected
                  ? "border-brand-primary bg-brand-muted text-brand-fg"
                  : "border-brand-border bg-white text-brand-fg-muted hover:bg-brand-muted"
              }`}
            >
              {option.text}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── The Plotly surface ───────────────────────────────────────────────────────
// Kept in its own component so the imperative plot lifecycle stays away from the
// declarative UI above. One trace per cluster; the camera is preserved across
// redraws via Plotly.react, so changing an axis does not reset the user's angle.

// Loaded on demand, not at module scope: the gl3d bundle is ~1.6 MB and Graph sits
// on the landing page, so a static import would block first paint for every visit.
// Cached in a module-level promise so remounting the dashboard does not refetch it.
let plotlyPromise = null;
const loadPlotly = () => {
  plotlyPromise ??= import("plotly.js-gl3d-dist-min").then((m) => m.default ?? m);
  return plotlyPromise;
};

function Scatter3D({ rows, series, axes, activeCluster }) {
  const nodeRef = useRef(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const node = nodeRef.current;
    if (!node) return;
    let cancelled = false;

    const data = series.map(({ label, color }) => {
      const points = rows.filter((r) => r.cluster === label);
      return {
        type: "scatter3d",
        mode: "markers",
        name: label,
        x: points.map((r) => r[axes.x]),
        y: points.map((r) => r[axes.y]),
        z: points.map((r) => r[axes.z]),
        // No per-point readout by design — see the note at the top of this file.
        hoverinfo: "skip",
        marker: {
          size: 5,
          color,
          opacity: activeCluster && activeCluster !== label ? 0.15 : 0.85,
          line: { width: 0 },
        },
      };
    });

    const axis = (key) => ({
      title: { text: skillLabel(key), font: AXIS_FONT },
      // Each skill is scored on its own rubric (phonics /46, word reading /10), so the range
      // comes from PLOT_SKILLS rather than a shared 0–100. Fixed rather than data-driven, so
      // switching axes cannot silently rescale the picture.
      range: [0, PLOT_SKILLS[key]?.max ?? 100],
      tickfont: AXIS_FONT,
      gridcolor: "#EAECEF",
      zerolinecolor: "#EAECEF",
      backgroundcolor: "#FFFFFF",
      showbackground: true,
    });

    const layout = {
      margin: { l: 0, r: 0, t: 0, b: 0 },
      showlegend: false,
      paper_bgcolor: "transparent",
      scene: {
        xaxis: axis(axes.x),
        yaxis: axis(axes.y),
        zaxis: axis(axes.z),
        aspectmode: "cube",
      },
    };

    loadPlotly().then((Plotly) => {
      // The chunk resolves asynchronously, so the component may already be gone.
      if (cancelled) return;
      // Plotly.react diffs against the existing figure rather than tearing it down,
      // which is what keeps the camera angle stable when a dropdown changes.
      Plotly.react(node, data, layout, { displayModeBar: false, responsive: true });
      setReady(true);
    });

    return () => {
      cancelled = true;
    };
  }, [rows, series, axes, activeCluster]);

  // Purge on unmount — Plotly attaches WebGL contexts and resize listeners that
  // React knows nothing about, so they leak if we let React just drop the node.
  // `node` is captured here because React nulls the ref before cleanup runs.
  useEffect(() => {
    const node = nodeRef.current;
    return () => {
      if (node && plotlyPromise) plotlyPromise.then((Plotly) => Plotly.purge(node));
    };
  }, []);

  return (
    <div className="relative h-[420px] w-full">
      <div ref={nodeRef} className="h-full w-full" />
      {!ready && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-brand-border border-t-brand-primary" />
        </div>
      )}
    </div>
  );
}
