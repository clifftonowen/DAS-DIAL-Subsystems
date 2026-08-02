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

// ── Literacy skills — the cohort scatter in Graph.jsx ────────────────────────
// A different taxonomy from SKILL_LABELS above: those are the seven cognitive
// constructs shown for one learner, these are the six literacy skills compared
// across the whole cohort.
//
// `field` is the learner_profiles column each skill currently reads from. It is a
// PLACEHOLDER — Supabase has no phonics/reading/*_writing columns yet, so each skill
// borrows a cognitive construct to have real data to plot. When the six real columns
// land, change `field` here and nothing else moves.
//
// No colour per skill on purpose: skills are continuous, so they live on the axes and
// are named by the dropdown labels. Colour is reserved for clusters, below.
export const LITERACY_SKILLS = {
  phonics:            { label: 'Phonics',             field: 'decoding' },
  reading:            { label: 'Reading',             field: 'comprehension' },
  spelling:           { label: 'Spelling',            field: 'spelling' },
  narrative_writing:  { label: 'Narrative Writing',   field: 'visualisation' },
  exposition_writing: { label: 'Exposition Writing',  field: 'executive_functioning' },
  persuasive_writing: { label: 'Persuasive Writing',  field: 'working_memory' },
};

export const SKILL_KEYS = Object.keys(LITERACY_SKILLS);

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
