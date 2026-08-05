-- Subsystem 2 — the DAS cohort and its k-means clusters (UC2).
-- Run in the Supabase SQL editor, then `python -m scripts.ingest_dial_data` from backend/.
--
-- WHY THIS IS NOT `learners`:
--   `learners` holds the therapist's own caseload — ten seeded rows, rendered one card each by
--   LearnersPage and counted by /dashboard/stats. This is the 5,783-student anonymised research
--   cohort behind the analytics scatter. Putting it in `learners` would report 5,783 learners on
--   the dashboard and render 5,783 cards in a list with no pagination. Where a cohort student IS
--   also on the caseload, `learner_id` links the two.

create table if not exists learner_scores (
  student_id   text primary key,          -- anonymised, e.g. 'Student 0001'
  learner_id   uuid references learners(id) on delete set null,

  -- provenance: which sitting these scores come from
  semester     text not null,             -- '2026 Sem 1' — the most recent on record
  band         text,                      -- NewBand: A1..C9
  band_group   text,                      -- 'A' | 'B' | 'C' — the clustering scope, see below
  school_level text,
  age          int,

  -- clustering features (complete for every student)
  phonics               real,
  word_reading_accuracy real,
  word_spelling         real,

  -- plottable but NOT clustered: writing is never administered to band A, so it is absent for
  -- 2,084 students. `writing` is the one mark the student actually received; the three genre
  -- columns are mutually exclusive (nobody has two) and kept only for provenance.
  writing            real,
  writing_genre      text,                -- 'narrative_writing' | 'exposition_writing' | ...
  narrative_writing  real,
  exposition_writing real,
  persuasive_writing real,

  -- stored for therapists, never clustered: FluencyMark is exactly 2 x word_reading_accuracy
  -- (r = 1.00 across all 22,892 sittings), so it carries no independent information.
  fluency_mark real,

  -- '<band_group> <rank>', e.g. 'B 2'. Null for the handful of students whose band group is too
  -- small to fit — the dashboard reports those as unclustered rather than hiding them.
  cluster_label text,

  updated_at timestamptz default now()
);

-- The dashboard filters by cluster when a legend chip is clicked.
create index if not exists idx_learner_scores_cluster on learner_scores (cluster_label);
create index if not exists idx_learner_scores_band    on learner_scores (band_group);

-- One row per k-means fit, so the dashboard can show HOW k was chosen rather than just asserting
-- it. WHY ONE ROW PER BAND GROUP: the assessment papers differ by band — phonics tops out at 25
-- in A1, 30 in A2 and 46 in A3, and phonics is the only feature with real spread — so a single
-- cohort-wide fit largely recovers which paper a student sat (its high-phonics cluster was 56.8%
-- band A3). Fitting within A / B / C compares like with like and scores better for it:
-- silhouette 0.43 / 0.42 / 0.34 against 0.36 cohort-wide. See notebooks/subsystem2_clustering.ipynb.
create table if not exists clustering_runs (
  id              uuid primary key default gen_random_uuid(),
  tier            text not null,          -- the band group this model was fitted on
  features        text[] not null,
  k               int not null,           -- chosen by best silhouette, not configured
  best_silhouette real not null,
  silhouette_by_k jsonb not null,         -- {"2": 0.3367, "3": 0.3688, ...} — the whole sweep
  n_learners      int not null,
  created_at      timestamptz default now()
);

-- The service reads only the newest run per tier; re-ingesting appends rather than overwriting,
-- so the history of previous fits stays inspectable.
create index if not exists idx_clustering_runs_tier on clustering_runs (tier, created_at desc);
