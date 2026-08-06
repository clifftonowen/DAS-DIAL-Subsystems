// constants.js — Shared constants for the dashboard prototype

// The seven cognitive dimensions that used to live here are gone. They were mock scaffolding
// derived by keyword-matching subtest names; the system standardises on the four marks DAS
// actually measures, which are PLOT_SKILLS below. See
// infra/migrations/2026-08-08_dial_dimensions.sql.

// ── Plottable axes — the cohort scatter in Graph.jsx ─────────────────────────
// THE SINGLE SWAP POINT. Graph.jsx hardcodes no skill names at all: the dropdowns,
// the default axes and the row-building loop are all generated from this map, so
// changing it changes the whole UI.
//
// These are the four DIAL marks on `learners`, served by GET /dashboard/clusters and
// GET /learners/{id}/overview. `field` names the column in those responses.
//
// `max` is the top of the rubric, and the axis range comes from it. Scores are plotted
// RAW rather than normalised to 0–100, because the marks are what a therapist reads: a
// phonics score is out of 46 and a spelling score out of 10, and rescaling both to a
// percentage would put two different things on the same footing while hiding the mark
// that was actually awarded. The cluster Table shows the same raw numbers.
//
// WHY WRITING IS ONE ENTRY, NOT THREE. The workbook has Narrative, Exposition and
// Persuasive Writing columns, but they are mutually exclusive — each student sits
// exactly one genre and the other two are recorded as 0 (measured: of 3,769 students
// with writing data, 3,699 have exactly one non-zero genre and nobody has two). The
// backend collapses them into the single 0–24 mark the student received and keeps the
// genre as `writing_genre`, which the Table shows as a column. Plotting the three
// separately would pile most of the cohort onto zero on two of the three axes.
//
// Writing is also plottable but NOT clustered — it is never administered to band A, so
// it is absent for 2,084 of 5,783 students. See backend/app/ingestion/dial_workbook.py.
//
// No colour per entry, on purpose: these are continuous, so they live on the axes
// and are named by the dropdown labels. Colour is reserved for clusters, below.
export const PLOT_SKILLS = {
  phonics:               { label: 'Phonics',       field: 'phonics',               max: 46 },
  word_reading_accuracy: { label: 'Word Reading',  field: 'word_reading_accuracy', max: 10 },
  word_spelling:         { label: 'Word Spelling', field: 'word_spelling',         max: 10 },
  writing:               { label: 'Writing',       field: 'writing',               max: 24 },
};

// Dropdown order, and the source of Graph.jsx's default X/Y/Z (the first three).
export const SKILL_KEYS = Object.keys(PLOT_SKILLS);

// ── DIAL radar chart — LearnerDetailPage's "DIAL Assessment" card ────────────
// The same four features as PLOT_SKILLS, on the profile page instead of the cohort scatter.
// ONLY the colours live here: the label, the rubric max and the percentile all arrive from
// GET /learners/{id}/overview, so the rubric is not written down twice (see
// backend/app/ingestion/dial_features.py, which is where those come from).
//
// The radar plots the PERCENTILE WITHIN THE LEARNER'S BAND GROUP, not the raw mark. A radar
// shares one radius across every axis, and the four marks are neither on the same rubric
// (phonics /46, word reading /10) nor on the same rubric across bands (phonics tops out at 25
// in A1 and 46 in A3) — so raw marks and percent-of-max are both uncomparable between axes.
// The legend still shows the mark that was actually awarded.
export const DIAL_METRIC_COLORS = {
  phonics: '#FF2E45',
  word_reading_accuracy: '#2563EB',
  word_spelling: '#22A06B',
  writing: '#F97316',
};

// ── Clustering scopes — the scatter's first control ──────────────────────────
// Two independent k-means models are stored per learner and both arrive in one response, so
// switching between them costs no round trip.
//
//   cohort  one fit over all 5,783 learners        -> k=4, silhouette 0.36
//   band    one fit per band group, each own k     -> k=5/4/2, silhouette 0.43/0.42/0.34
//
// The band models score better because the assessment papers differ by band — phonics tops
// out at 25 in A1, 30 in A2, 46 in A3 — so a single cohort fit partly recovers which paper
// the learner sat rather than how they are doing (its high-phonics cluster is 56.8% band A3).
// Cohort is nonetheless the default: one legend of four colours is the readable first
// impression, and switching to By band is how you interrogate it.
//
// `field` names the property on a Graph row, NOT the API field — Graph camel-cases on load.
export const CLUSTER_SCOPES = [
  { key: 'cohort', label: 'Cohort',  field: 'clusterCohort' },
  { key: 'band',   label: 'By band', field: 'clusterBand' },
];

// The band filter's options, in order. `null` (All) is added by the control itself rather
// than living here, so this stays a list of real band groups.
export const BAND_GROUPS = ['A', 'B', 'C'];

// ── Clusters — the scatter's legend ──────────────────────────────────────────
// Indexed by position rather than keyed by name: the backend picks k itself (best
// silhouette over k = 2..10), so the number of clusters is not knowable here.
//
// TWELVE colours, not six. Clustering is fitted per band group — A, B and C each get
// their own model and their own k — because the assessment papers differ by band
// (phonics tops out at 25 in A1, 30 in A2, 46 in A3), so a single cohort-wide fit
// largely recovers which paper a student sat. That currently yields 11 clusters
// (A 1–5, B 1–4, C 1–2). A palette that cycled would give two clusters the same
// colour, and a legend that reuses a colour is a legend that lies.
export const CLUSTER_COLORS = [
  '#FF2E45', '#2563EB', '#22A06B', '#7C3AED', '#F97316', '#EC4899',
  '#0891B2', '#CA8A04', '#7C2D12', '#4338CA', '#059669', '#BE123C',
];

export const clusterColor = (i) => CLUSTER_COLORS[i % CLUSTER_COLORS.length];
