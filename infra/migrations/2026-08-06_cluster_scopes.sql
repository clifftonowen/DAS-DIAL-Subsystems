-- Subsystem 2 — store BOTH clustering scopes side by side (UC2).
-- Run in the Supabase SQL editor, then re-run `python -m scripts.ingest_dial_data` from backend/.
--
-- WHY TWO SCOPES:
--   cohort  one k-means fit over all 5,783 learners            -> k=4, silhouette 0.365
--   band    one fit per band group (A / B / C), each own k     -> k=5/4/2, s=0.429/0.419/0.341
--
--   The band models score better and are not confounded by phonics being a different paper per
--   band (max 25 in A1, 30 in A2, 46 in A3), which is why the cohort fit's high-phonics cluster
--   comes out 56.8% band A3. But the cohort model is a real, interpretable partition, and the
--   COMPARISON between the two is the most useful thing the analysis produced. Storing both
--   lets the dashboard toggle between them and show the comparison on screen.
--
--   The two label different populations: every learner gets a cluster_cohort, but the 3 learners
--   whose band is missing or unrecognised fall below MIN_GROUP and get no cluster_band.

-- `cluster_label` only ever held the band-scoped label; the rename makes that explicit and
-- keeps the two columns parallel. Values are preserved — the re-ingest refills both anyway.
alter table learner_scores rename column cluster_label to cluster_band;
alter table learner_scores add column if not exists cluster_cohort text;

-- 'cohort' | 'band'. Defaulted so the three existing band rows are correctly labelled without
-- a backfill; the cohort row the next ingest writes sets it explicitly.
alter table clustering_runs add column if not exists scope text not null default 'band';

-- The dashboard filters by whichever label the active scope selects.
drop index if exists idx_learner_scores_cluster;
create index if not exists idx_learner_scores_cluster_band   on learner_scores (cluster_band);
create index if not exists idx_learner_scores_cluster_cohort on learner_scores (cluster_cohort);

-- The service reads the newest run per (scope, tier), so both columns lead the index.
drop index if exists idx_clustering_runs_tier;
create index if not exists idx_clustering_runs_scope
  on clustering_runs (scope, tier, created_at desc);
