-- Subsystem 2 — percentile-within-band-group for each plottable mark (UC2).
-- Run in the Supabase SQL editor, then re-run `python -m scripts.ingest_dial_data` from backend/.
--
-- WHY STORED RATHER THAN COMPUTED PER REQUEST:
--   Same rule the cluster labels follow. Clustering runs once at ingest and /dashboard/clusters
--   is a plain SELECT; percentiles get the same treatment, so drawing one learner's radar chart
--   never has to read the other 5,782 rows to rank them.
--
-- WHY PERCENTILE, NOT PERCENT-OF-MAX:
--   LearnerDetailPage's radar chart shares one radius across all four axes. Raw marks cannot go
--   on it — phonics is out of 46, word reading out of 10. Percent-of-max cannot either, because
--   the rubric differs BY BAND: phonics tops out at 25 in A1, 30 in A2 and 46 in A3. 67% of an
--   A1 paper and 67% of an A3 paper are not the same achievement, and one radius for both would
--   assert that they were.
--
--   Ranking within `band_group` compares each learner against the population that sat their
--   paper — the same correction, for the same reason, as scoping the k-means fit to a band
--   group (see 2026-08-05_learner_scores.sql).
--
-- NULL means NOT ASSESSED, never "bottom of the cohort". Writing is never administered to band
-- A, so writing_pct is null for those 2,084 learners and the radar drops that axis rather than
-- drawing them at zero.

alter table learner_scores add column if not exists phonics_pct               real;
alter table learner_scores add column if not exists word_reading_accuracy_pct real;
alter table learner_scores add column if not exists word_spelling_pct         real;
alter table learner_scores add column if not exists writing_pct               real;

-- No index: these are only ever read for a single learner already located by learner_id.
