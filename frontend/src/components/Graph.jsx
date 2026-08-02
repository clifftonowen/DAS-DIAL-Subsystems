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
// is never a fixed list. The backend will pick k automatically (silhouette score),
// so the cluster count is not knowable here. Until /dashboard/clusters exists,
// constants.clusterFor() stands in with the learner's band letter.
//
// Clustering is a property of the learner, not of the current view: changing a
// dropdown re-projects the same points and must never change their colours.
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
import { listLearners, getLearnerProfiles } from "../lib/api";
import { PLOT_SKILLS, SKILL_KEYS, clusterColor, clusterFor } from "../lib/constants";

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
  const [skipped, setSkipped] = useState(0);
  const [activeCluster, setActiveCluster] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function loadCohort() {
      try {
        const learners = await listLearners();

        // One request per learner. Fine at the current roster size; when the
        // clustering endpoint lands it should return the whole cohort — scores and
        // cluster labels — in a single call, and this fan-out goes away.
        const profileLists = await Promise.all(
          learners.map((l) => getLearnerProfiles(l.id))
        );

        const built = [];
        let withoutProfile = 0;

        learners.forEach((learner, i) => {
          // list_by_learner orders created_at desc, so [0] is the latest profile —
          // the same assumption LearnerDetailPage makes.
          const latest = profileLists[i]?.[0];
          if (!latest) {
            withoutProfile += 1;
            return;
          }

          const row = {
            id: learner.id,
            name: learner.pseudonym || learner.name || "Unnamed",
            bandLevel: learner.band_level || learner.band || "—",
            cluster: clusterFor(learner),
          };
          // Scores are stored 0–1; the axes run 0–100.
          SKILL_KEYS.forEach((key) => {
            row[key] = Math.round((latest[PLOT_SKILLS[key].field] || 0) * 100);
          });
          built.push(row);
        });

        setRows(built);
        setSkipped(withoutProfile);
      } catch (err) {
        console.error("Failed to load cohort skills", err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    loadCohort();
  }, []);

  // The legend, the plot's traces and the table filter all read off this one array,
  // so nothing below assumes how many clusters there are.
  const series = useMemo(() => {
    const labels = [...new Set(rows.map((r) => r.cluster))].sort();
    return labels.map((label, i) => ({
      label,
      color: clusterColor(i),
      count: rows.filter((r) => r.cluster === label).length,
    }));
  }, [rows]);

  const selectAxis = (axis, skill) => setAxes((cur) => ({ ...cur, [axis]: skill }));

  return (
    <Card className="flex flex-col gap-4">
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
      ) : rows.length === 0 ? (
        <div className="rounded-xl border border-dashed border-brand-border bg-brand-muted p-10 text-center">
          <h3 className="text-sm font-medium text-brand-fg">Nothing to plot yet</h3>
          <p className="mt-2 text-sm text-brand-fg-muted">
            No learner has a profile yet. Generate one from a learner's page to see them here.
          </p>
        </div>
      ) : (
        <>
          <Scatter3D rows={rows} series={series} axes={axes} activeCluster={activeCluster} />

          <p className="text-center text-xs text-brand-fg-muted">
            Drag to rotate · scroll to zoom
            {skipped > 0 &&
              ` · ${skipped} learner${skipped === 1 ? "" : "s"} hidden (no profile yet)`}
          </p>

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

          {activeCluster && (
            <Table
              rows={rows.filter((r) => r.cluster === activeCluster)}
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
      range: [0, 100],
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
