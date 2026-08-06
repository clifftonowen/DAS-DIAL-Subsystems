-- Subsystem 2 — standardise on the four DIAL metrics, and keep their history (UC2).
--
-- ⚠ THE LAST STEP DROPS `learner_profiles`, and is commented out. Back up first, read the
--   verification SELECT above it, and only then uncomment.
--
-- IDEMPOTENT, like 2026-08-07. Every step checks the state it expects, so re-running is a no-op
-- rather than an error.
--
-- WHY
--   The seven cognitive dimensions on `learner_profiles` — phonological_processing, decoding,
--   spelling, comprehension, working_memory, executive_functioning, visualisation — were mock
--   scaffolding. They came out of ProfilingAlgorithm.analyse() keyword-matching subtest names in
--   assessment_records.task_results, a mapping whose own docstring called itself "an engineering
--   approximation [that] wants a clinician's sign-off", over seeded data.
--
--   DAS gives us four real measurements: phonics, word reading accuracy, word spelling, writing.
--   Those already sit on `learners` after the 2026-08-07 merge. So the profile stops being
--   derived and starts being the marks.
--
-- WHY A SECOND TABLE, HAVING JUST MERGED TWO INTO ONE
--   Different GRAIN, which is not the same thing as redundancy. `learners` is one row per
--   person; `learner_sittings` is one row per person per semester. The earlier merge collapsed
--   two tables that were both one-row-per-person and gave one human two identities — this adds
--   a dimension `learners` cannot express without either ten sets of score columns or losing
--   the history entirely.
--
--   The workbook has ~22,892 sittings across 5,783 students and nine semesters (2022 Sem 1 ->
--   2026 Sem 1). The ingest was throwing ~17,000 of them away. That history is what the profile
--   page's line chart plots.
--
--   `learners` keeps the newest sitting's marks as the CURRENT values. That is a deliberate
--   duplication: the cohort scatter reads 5,783 rows in one request and a latest-per-learner
--   lateral join through PostgREST on every dashboard load is painful, and k-means needs a
--   stable snapshot to fit against.

-- ── 1. The history table ─────────────────────────────────────────────────────
create table if not exists learner_sittings (
  id uuid primary key default gen_random_uuid(),
  learner_id uuid not null references learners(id) on delete cascade,

  -- '2024 Sem 1'. Sorts chronologically as plain text for every value in the workbook, which is
  -- what the chart's X axis and `latest_for_learner` both rely on — see dial_workbook.
  semester text not null,

  -- The paper they sat THAT semester. Stored per sitting because it changes: a learner moves
  -- from A2 to A3, and phonics is out of 30 in one and 46 in the other.
  band       text,
  band_group text,

  phonics               real,
  word_reading_accuracy real,
  word_spelling         real,
  writing               real,
  writing_genre         text,

  -- Percentile WITHIN (semester, band_group) — not against the current cohort. Ranking a 2022
  -- mark against the 2026 population would make the line move as the cohort changes rather than
  -- as the learner does, which is the opposite of what a progress chart is for.
  phonics_pct               real,
  word_reading_accuracy_pct real,
  word_spelling_pct         real,
  writing_pct               real,

  -- 'workbook' | 'upload'. UC1's confirm step writes 'upload' rows; the ingest writes
  -- 'workbook'. Generate Profile promotes whichever is newest, so the two paths converge here.
  source text not null default 'workbook',
  created_at timestamptz default now(),

  -- The ingest's upsert key. Re-running must update a sitting, never append a second copy.
  unique (learner_id, semester)
);

-- The chart reads one learner's whole history, newest-first for `latest_for_learner`.
create index if not exists idx_sittings_learner on learner_sittings (learner_id, semester desc);

-- ── 2. Re-point learning_activities at the learner ───────────────────────────
-- MUST HAPPEN BEFORE THE DROP. `profiled` references learner_profiles(id), and the only thing
-- mapping an activity back to a person is learner_profiles.learner_id. Drop that table first
-- and every existing activity is orphaned with no way to recover the link.
do $$
begin
  if exists (select 1 from information_schema.columns
             where table_schema = 'public' and table_name = 'learning_activities'
               and column_name = 'learner_id') then
    raise notice 'step 2: skipped — learning_activities.learner_id already exists';
    return;
  end if;

  alter table learning_activities add column learner_id uuid references learners(id);

  if to_regclass('public.learner_profiles') is not null then
    update learning_activities a
    set learner_id = p.learner_id
    from learner_profiles p
    where a.profiled = p.id;
    raise notice 'step 2: carried % activity row(s) over to learner_id',
      (select count(*) from learning_activities where learner_id is not null);
  end if;

  alter table learning_activities drop column if exists profiled;
end $$;

create index if not exists idx_activities_learner on learning_activities (learner_id);

-- ── 3. Verify BEFORE dropping ────────────────────────────────────────────────
--   sittings        0 until you re-run the ingest; ~22,892 after.
--   activities      total rows in learning_activities.
--   orphaned        activities with no learner. Anything above 0 means step 2 could not map
--                   them — usually a profile row that was already deleted. Investigate before
--                   dropping, because after the drop there is nothing left to map from.
--   profiles_left   -1 once learner_profiles is gone.
select
  (select count(*) from learner_sittings)                                as sittings,
  (select count(*) from learning_activities)                             as activities,
  (select count(*) from learning_activities where learner_id is null)    as orphaned,
  (select case when to_regclass('public.learner_profiles') is null then -1
               else (select count(*) from learner_profiles) end)         as profiles_left;

-- ── 4. The drop ──────────────────────────────────────────────────────────────
-- Uncomment ONLY once `orphaned` above is 0. Irreversible without a backup.
-- drop table learner_profiles;
