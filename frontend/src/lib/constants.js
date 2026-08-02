// constants.js — Shared constants for the dashboard prototype

export const SKILL_LABELS = {
  phonological: 'Phonological Processing',
  decoding: 'Decoding',
  spelling: 'Spelling',
  comprehension: 'Comprehension',
  workingMemory: 'Working Memory',
  executive: 'Executive Functioning',
  visualisation: 'Visualisation',
};

// Maps to the Tailwind brand.chart-* colours in tailwind.config.js
export const SKILL_COLORS = {
  phonological: '#FF2E45',   // chart-1
  decoding: '#FFCA28',       // chart-2
  spelling: '#2563EB',       // chart-3
  comprehension: '#22A06B',  // chart-4
  workingMemory: '#7C3AED',  // chart-5
  executive: '#EC4899',      // chart-6
  visualisation: '#F97316',  // chart-7
};

// ── Plottable axes — the cohort scatter in Graph.jsx ─────────────────────────
// THE SINGLE SWAP POINT. Graph.jsx hardcodes no skill names at all: the dropdowns,
// the default axes and the row-building loop are all generated from this map, so
// changing it changes the whole UI.
//
// TODAY these are the seven cognitive constructs that actually exist as columns on
// learner_profiles, labelled as what they are. The target taxonomy is the six
// literacy skills (phonics, reading, spelling, narrative / exposition / persuasive
// writing), but those columns do not exist in Supabase yet, and mapping them onto
// the constructs would mean inventing three relationships that have no basis —
// "Persuasive Writing" would really be plotting working_memory. That is the trap
// backend/app/ingestion/constants.py warns about at CONCEPT_TO_CONSTRUCTS:
// "Do NOT invent mappings — an empty array is more honest than a wrong one."
//
// WHEN THE REAL COLUMNS LAND: replace the seven entries below with the six skills,
// each `field` naming its new column. Nothing else in the codebase changes.
//
// `label` overlaps with SKILL_LABELS above for now, deliberately duplicated rather
// than shared — the two diverge completely at the swap, and SKILL_LABELS is keyed by
// the frontend's camelCase names (`workingMemory`) while these are keyed by the DB
// column names.
//
// No colour per entry, on purpose: these are continuous, so they live on the axes
// and are named by the dropdown labels. Colour is reserved for clusters, below.
export const PLOT_SKILLS = {
  phonological_processing: { label: 'Phonological Processing', field: 'phonological_processing' },
  decoding:                { label: 'Decoding',                field: 'decoding' },
  spelling:                { label: 'Spelling',                field: 'spelling' },
  comprehension:           { label: 'Comprehension',           field: 'comprehension' },
  working_memory:          { label: 'Working Memory',          field: 'working_memory' },
  executive_functioning:   { label: 'Executive Functioning',   field: 'executive_functioning' },
  visualisation:           { label: 'Visualisation',           field: 'visualisation' },
};

// Dropdown order, and the source of Graph.jsx's default X/Y/Z (the first three).
export const SKILL_KEYS = Object.keys(PLOT_SKILLS);

// ── Clusters — the scatter's legend ──────────────────────────────────────────
// Indexed by position rather than keyed by name: the backend picks k automatically
// (silhouette score), so the number of clusters is unknown until the data arrives.
// Cycles if k ever exceeds the palette.
export const CLUSTER_COLORS = ['#FF2E45', '#2563EB', '#22A06B', '#7C3AED', '#F97316', '#EC4899'];

export const clusterColor = (i) => CLUSTER_COLORS[i % CLUSTER_COLORS.length];

// PLACEHOLDER cluster assignment. ProfilingAlgorithm.cluster() will eventually k-means
// learners over all six skills and expose the labels via /dashboard/clusters; until then
// a learner's band letter stands in, so the legend and table work end to end. The seeded
// band_level values are finer than the letter ('Band A1', 'Band A2', 'Band B' — see
// infra/seed.sql), hence the parse rather than a plain read.
//
// The 'Band ' prefix is stripped before matching: a bare /[ABC]/ would hit the B in
// "Band" and file every learner under B.
//
// Graph.jsx derives its legend from whatever distinct labels this yields, so replacing
// this one function with the real cluster labels needs no component changes.
export const clusterFor = (learner) => {
  const raw = String(learner.band_level || learner.band || '').replace(/^\s*band\s*/i, '');
  const letter = raw.match(/^([ABC])/i)?.[1];
  return letter ? `Band ${letter.toUpperCase()}` : 'Unbanded';
};
