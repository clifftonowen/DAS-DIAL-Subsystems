-- Subsystem 2 — merge `learner_scores` into `learners`. ONE table for every learner (UC2).
--
-- ⚠ THE LAST STATEMENT DROPS A TABLE, and is commented out. Take a Supabase backup, read the
--   verification SELECT above it, and only then uncomment. Everything else is re-runnable.
--
-- IDEMPOTENT. Every step checks the state it expects before acting, so running this twice —
-- or running it against a project that is already merged, or one built from the current
-- schema.sql — is a no-op rather than an error or, worse, a silent corruption. The step that
-- makes this non-negotiable is step 2: an unqualified `set on_caseload = true` is correct while
-- the table still holds only the caseload, and catastrophic once the cohort is in it, because it
-- would promote all ~5,783 research rows to the therapist's caseload.
--
-- Step 8 at the bottom reports where you are. It is safe to run on its own, at any time.
--
-- WHY
--   The two tables described the same kind of thing and cost us for it:
--     * one person had two identities — a uuid with a pseudonym in `learners`, and
--       'Student 0142' with marks in `learner_scores` — joined only by a nullable self-FK that
--       nothing populated automatically;
--     * band was stored twice in two spellings that did not agree (`band_level` = 'Band B' has
--       no fine band; `band` = 'B4' does), so the frontend wrote `l.band_level || l.band`;
--     * a whole apparatus existed purely to maintain the link — seed_cohort_links.sql, the
--       ingest's --links flag, and a read-back to stop re-ingest nulling the column;
--     * only ~10 of 5,783 rows had the link set, which is why almost no name in the dashboard's
--       cluster table could be clicked through to a profile.
--
--   The original split (2026-08-05_learner_scores.sql) was argued on the grounds that 5,783 rows
--   in `learners` would report 5,783 on the dashboard and render 5,783 cards in an unpaginated
--   list. Both of those are unpaged reads, not facts about the data model, and both are fixed in
--   the application: LearnerRepository pages every full read and counts with count(), and the
--   Learners tab paginates server-side.
--
-- AFTER THIS
--   `on_caseload` tells the two populations apart. Every learner has a uuid, so every name in
--   the cluster table opens a detail page — read-only for cohort rows, which have no assessment
--   records to profile.

-- ── 1. The new columns ───────────────────────────────────────────────────────
alter table learners add column if not exists student_id   text;
alter table learners add column if not exists on_caseload  boolean not null default false;
alter table learners add column if not exists band         text;
alter table learners add column if not exists band_group   text;
alter table learners add column if not exists semester     text;
alter table learners add column if not exists school_level text;
alter table learners add column if not exists age          int;

alter table learners add column if not exists phonics               real;
alter table learners add column if not exists word_reading_accuracy real;
alter table learners add column if not exists word_spelling         real;
alter table learners add column if not exists writing               real;
alter table learners add column if not exists writing_genre         text;
alter table learners add column if not exists narrative_writing     real;
alter table learners add column if not exists exposition_writing    real;
alter table learners add column if not exists persuasive_writing    real;
alter table learners add column if not exists fluency_mark          real;

alter table learners add column if not exists phonics_pct               real;
alter table learners add column if not exists word_reading_accuracy_pct real;
alter table learners add column if not exists word_spelling_pct         real;
alter table learners add column if not exists writing_pct               real;

alter table learners add column if not exists cluster_band   text;
alter table learners add column if not exists cluster_cohort text;
alter table learners add column if not exists updated_at timestamptz default now();

-- `pseudonym` was NOT NULL, which a cohort row cannot satisfy — the cohort is anonymised.
alter table learners alter column pseudonym drop not null;
alter table learners alter column pseudonym set default '';

-- ── 2. Everything already here is the caseload ───────────────────────────────
-- GUARDED ON `band_level`, which is the reliable signal that this table has not been merged
-- yet: it exists only in the pre-merge schema and step 6 drops it. While it is present, every
-- row in `learners` is by definition one of the therapist's, so the unqualified update is
-- right. Once it is gone, this must never run again — see the header.
do $$
begin
  if exists (select 1 from information_schema.columns
             where table_schema = 'public' and table_name = 'learners'
               and column_name = 'band_level') then

    alter table learners alter column band_level drop not null;
    update learners set on_caseload = true;
    raise notice 'step 2: marked % pre-existing learners as caseload',
      (select count(*) from learners where on_caseload);
  else
    raise notice 'step 2: skipped — band_level is gone, so this table is already merged';
  end if;
end $$;

-- ── 3 & 4. Fold the linked pairs, then bring in the rest ─────────────────────
-- Skipped entirely once `learner_scores` has been dropped.
do $$
declare
  folded int := 0;
  added  int := 0;
begin
  if to_regclass('public.learner_scores') is null then
    raise notice 'steps 3-4: skipped — learner_scores does not exist, nothing to fold';
    return;
  end if;

  -- THE DELICATE STEP. The learners that seed_cohort_links.sql linked already carry
  -- assessment_records and learner_profiles pointing at their uuids. Updating IN PLACE keeps
  -- every one of those foreign keys valid; inserting them as new rows instead would orphan
  -- every profile and assessment the therapist has generated.
  update learners l set
    student_id            = s.student_id,
    band                  = s.band,
    band_group            = s.band_group,
    semester              = s.semester,
    school_level          = s.school_level,
    age                   = s.age,
    phonics               = s.phonics,
    word_reading_accuracy = s.word_reading_accuracy,
    word_spelling         = s.word_spelling,
    writing               = s.writing,
    writing_genre         = s.writing_genre,
    narrative_writing     = s.narrative_writing,
    exposition_writing    = s.exposition_writing,
    persuasive_writing    = s.persuasive_writing,
    fluency_mark          = s.fluency_mark,
    phonics_pct               = s.phonics_pct,
    word_reading_accuracy_pct = s.word_reading_accuracy_pct,
    word_spelling_pct         = s.word_spelling_pct,
    writing_pct               = s.writing_pct,
    cluster_band   = s.cluster_band,
    cluster_cohort = s.cluster_cohort
  from learner_scores s
  where s.learner_id = l.id;
  get diagnostics folded = row_count;

  -- The rest of the cohort arrives as new rows. `not exists` rather than a bare insert, so a
  -- re-run cannot duplicate anyone: student_id is the workbook's stable key.
  insert into learners (
    student_id, on_caseload, band, band_group, semester, school_level, age,
    phonics, word_reading_accuracy, word_spelling, writing, writing_genre,
    narrative_writing, exposition_writing, persuasive_writing, fluency_mark,
    phonics_pct, word_reading_accuracy_pct, word_spelling_pct, writing_pct,
    cluster_band, cluster_cohort
  )
  select
    s.student_id, false, s.band, s.band_group, s.semester, s.school_level, s.age,
    s.phonics, s.word_reading_accuracy, s.word_spelling, s.writing, s.writing_genre,
    s.narrative_writing, s.exposition_writing, s.persuasive_writing, s.fluency_mark,
    s.phonics_pct, s.word_reading_accuracy_pct, s.word_spelling_pct, s.writing_pct,
    s.cluster_band, s.cluster_cohort
  from learner_scores s
  where s.learner_id is null
    and not exists (select 1 from learners l where l.student_id = s.student_id);
  get diagnostics added = row_count;

  raise notice 'steps 3-4: folded % linked learner(s), inserted % cohort row(s)', folded, added;
end $$;

-- ── 5 & 6. Derive band from the old band_level, then drop it ─────────────────
do $$
begin
  if not exists (select 1 from information_schema.columns
                 where table_schema = 'public' and table_name = 'learners'
                   and column_name = 'band_level') then
    raise notice 'steps 5-6: skipped — band_level already dropped';
    return;
  end if;

  -- An unlinked caseload learner has only the old `band_level` ('Band A2', or just 'Band B').
  -- Strip the prefix BEFORE taking the first letter: 'BAND' itself starts with a B, so a naive
  -- first-[ABC] match reads every learner as band B.
  --
  -- 'Band A2' yields band 'A2'; 'Band B' yields band NULL, because there is no fine band in it —
  -- guessing one would invent an assessment paper the learner never sat.
  update learners set
    band = nullif(regexp_replace(upper(trim(band_level)), '^BAND\s*', ''), ''),
    band_group = nullif(left(regexp_replace(upper(trim(band_level)), '^BAND\s*', ''), 1), '')
  where on_caseload and band_group is null and band_level is not null;

  update learners set band = null
  where band is not null and band !~ '^[ABC][1-9]$';   -- 'B' is a group, not a band

  update learners set band_group = null
  where band_group is not null and band_group not in ('A', 'B', 'C');

  alter table learners drop column band_level;
  raise notice 'steps 5-6: derived band/band_group and dropped band_level';
end $$;

-- ── 7. Constraints and indexes ───────────────────────────────────────────────
-- Unique, not primary: an app-created learner has no workbook id, and Postgres treats NULLs as
-- distinct, so any number of them coexist. This is what the ingest upserts on_conflict against.
create unique index if not exists idx_learners_student_id on learners (student_id);

create index if not exists idx_learners_cluster_band   on learners (cluster_band);
create index if not exists idx_learners_cluster_cohort on learners (cluster_cohort);
create index if not exists idx_learners_band_group     on learners (band_group);
create index if not exists idx_learners_on_caseload    on learners (on_caseload);

-- ── 8. Where am I? ───────────────────────────────────────────────────────────
-- Safe to run at any time, before or after the migration, however many times.
--
--   total          ~5,783 — the cohort size, NOT cohort + 10. A larger number means the fold
--                  failed and the insert added duplicates of the linked learners.
--   caseload       however many were in `learners` before the merge (10 with infra/seed.sql).
--                  IF THIS IS IN THE THOUSANDS, step 2 ran after the cohort landed and the whole
--                  research cohort has been promoted to the caseload — restore from backup.
--   profiles       unchanged from before the migration. This is the FK-preservation check.
--   unlinked       caseload learners with no workbook row. Expected if you never linked all 10.
--   merged         whether band_level is gone, i.e. whether this migration has run.
select
  (select count(*) from learners)                    as total,
  (select count(*) from learners where on_caseload)  as caseload,
  (select count(*) from learner_profiles p
     join learners l on l.id = p.learner_id)         as profiles,
  (select count(*) from learners
     where on_caseload and student_id is null)       as unlinked,
  not exists (select 1 from information_schema.columns
              where table_schema = 'public' and table_name = 'learners'
                and column_name = 'band_level')      as merged;

-- How many rows are still in the old table. SEPARATE from the query above on purpose: a plain
-- SELECT resolves table names when it is parsed, not when a CASE branch is taken, so naming
-- `learner_scores` up there would make the whole status query fail once it has been dropped —
-- exactly when you most want to be able to check where you are.
--
-- Run this one only while the table still exists; an "does not exist" error IS the answer.
select count(*) as scores_left from learner_scores;

-- ── 9. The drop ──────────────────────────────────────────────────────────────
-- Uncomment ONLY once the numbers above check out. Irreversible without a backup.
-- drop table learner_scores;
