-- Seed script to populate mock data into Supabase tables.
-- Run this in the Supabase SQL editor after schema.sql.
--
-- SAFE TO RE-RUN. Every insert is guarded, so pasting the whole file into an already-seeded
-- project adds what is missing and changes nothing else. Without the guards the three tables
-- with no natural key — assessment_records, tasks, calendar_events — would silently gain a
-- second copy of every row each time, which is the kind of thing you only notice when a count
-- on the dashboard looks wrong.

-- 1. Insert mock Learners — the therapist's caseload.
--
-- `on_caseload` is what tells these apart from the ~5,783 anonymised cohort rows that
-- `python -m scripts.ingest_dial_data` loads into the SAME table. Only caseload learners have a
-- pseudonym and a tier, and only they get assessment records and generated activities.
--
-- `band` is the fine band (A1..C9) where it is known. Chen, Emily, Grace and Jamal carry only a
-- band GROUP — the source data for them never recorded which paper they sat, and inventing one
-- would put them in a percentile population they do not belong to. `band_group` is what the
-- clustering and the radar chart's percentiles actually scope on, so those four still work.
INSERT INTO learners (id, pseudonym, band, band_group, tier, on_caseload) VALUES
('11111111-1111-1111-1111-111111111111', 'Aisha Binti Rahman', 'A2', 'A', 'Tier 2', true),
('22222222-2222-2222-2222-222222222222', 'Benjamin Lim Wei',   'A1', 'A', 'Tier 1', true),
('33333333-3333-3333-3333-333333333333', 'Chen Yu Xuan',       NULL, 'B', 'Tier 2', true),
('44444444-4444-4444-4444-444444444444', 'Darren Tan Kai',     'A3', 'A', 'Tier 3', true),
('55555555-5555-5555-5555-555555555555', 'Emily Ng Su Lin',    NULL, 'C', 'Tier 1', true),
('66666666-6666-6666-6666-666666666666', 'Farhan Bin Ismail',  'A1', 'A', 'Tier 2', true),
('77777777-7777-7777-7777-777777777777', 'Grace Wong Mei',     NULL, 'B', 'Tier 1', true),
('88888888-8888-8888-8888-888888888888', 'Hassan Ali Khan',    'A2', 'A', 'Tier 3', true),
('99999999-9999-9999-9999-999999999999', 'Isabelle Lau Xin',   'A1', 'A', 'Tier 1', true),
('00000000-0000-0000-0000-000000000000', 'Jamal Syed Ahmad',   NULL, 'C', 'Tier 2', true)
ON CONFLICT (id) DO NOTHING;

-- 2. Insert mock Assessment Records
-- `WHERE NOT EXISTS` rather than ON CONFLICT: there is no unique key to conflict on, and
-- "seed only into an empty table" is the right rule for mock data anyway — a project with real
-- uploaded assessments should not have these appear underneath them.
INSERT INTO assessment_records (learner_id, assessment_date, risk_score)
SELECT * FROM (VALUES
  ('11111111-1111-1111-1111-111111111111'::uuid, '2026-07-01'::date, 0.2),
  ('22222222-2222-2222-2222-222222222222', '2026-07-02', 0.1),
  ('33333333-3333-3333-3333-333333333333', '2026-07-03', 0.3),
  ('44444444-4444-4444-4444-444444444444', '2026-07-04', 0.4),
  ('55555555-5555-5555-5555-555555555555', '2026-07-05', 0.89)
) AS v(learner_id, assessment_date, risk_score)
WHERE NOT EXISTS (SELECT 1 FROM assessment_records);

-- 3. Score history — three sittings per learner.
--
-- WHY THIS IS SEEDED AT ALL. The DIAL workbook is gitignored source material, so a test project
-- cannot run the ingest: without these rows every seeded learner has no scores, the profile
-- page shows only its upload prompt, and UC2's e2e test gets the 409 that "no scores on record"
-- correctly returns. Every one of the ten is given a history so that whichever uuid is wired to
-- TEST_LEARNER_ID has data behind it.
--
-- THREE SEMESTERS, not one, because the profile page's chart plots progress over time — a
-- single sitting renders as a lone dot and demonstrates nothing.
--
-- THE MARKS RESPECT THE PAPER. Phonics tops out at 25 in band A1, 30 in A2 and 46 in A3, then
-- falls away through B and C as phonics stops being assessed; writing is never administered to
-- band A at all, so those rows are NULL rather than 0. Aisha moves A2 -> A3 in her last sitting,
-- which is why `band` lives on the sitting: her phonics ceiling changes with it, and comparing
-- 19/30 against 31/46 as raw marks would read as a bigger jump than it is.
--
-- These are invented numbers for a demo, like the names above them. The percentiles below are
-- not invented — they are computed from these rows by the same rule the ingest uses.
INSERT INTO learner_sittings
  (learner_id, semester, band, band_group, phonics, word_reading_accuracy, word_spelling,
   writing, writing_genre, source)
VALUES
  -- Band A — no writing paper
  ('11111111-1111-1111-1111-111111111111', '2024 Sem 1', 'A2', 'A', 14, 5, 3, NULL, NULL, 'seed'),
  ('11111111-1111-1111-1111-111111111111', '2025 Sem 1', 'A2', 'A', 19, 6, 4, NULL, NULL, 'seed'),
  ('11111111-1111-1111-1111-111111111111', '2026 Sem 1', 'A3', 'A', 31, 7, 5, NULL, NULL, 'seed'),

  ('22222222-2222-2222-2222-222222222222', '2024 Sem 1', 'A1', 'A',  8, 4, 2, NULL, NULL, 'seed'),
  ('22222222-2222-2222-2222-222222222222', '2025 Sem 1', 'A1', 'A', 12, 5, 3, NULL, NULL, 'seed'),
  ('22222222-2222-2222-2222-222222222222', '2026 Sem 1', 'A1', 'A', 16, 6, 4, NULL, NULL, 'seed'),

  ('44444444-4444-4444-4444-444444444444', '2024 Sem 1', 'A3', 'A', 22, 6, 4, NULL, NULL, 'seed'),
  ('44444444-4444-4444-4444-444444444444', '2025 Sem 1', 'A3', 'A', 28, 7, 5, NULL, NULL, 'seed'),
  ('44444444-4444-4444-4444-444444444444', '2026 Sem 1', 'A3', 'A', 33, 7, 6, NULL, NULL, 'seed'),

  ('66666666-6666-6666-6666-666666666666', '2024 Sem 1', 'A1', 'A', 11, 5, 3, NULL, NULL, 'seed'),
  ('66666666-6666-6666-6666-666666666666', '2025 Sem 1', 'A1', 'A', 15, 6, 4, NULL, NULL, 'seed'),
  ('66666666-6666-6666-6666-666666666666', '2026 Sem 1', 'A1', 'A', 18, 7, 5, NULL, NULL, 'seed'),

  ('88888888-8888-8888-8888-888888888888', '2024 Sem 1', 'A2', 'A',  9, 3, 2, NULL, NULL, 'seed'),
  ('88888888-8888-8888-8888-888888888888', '2025 Sem 1', 'A2', 'A', 13, 4, 3, NULL, NULL, 'seed'),
  ('88888888-8888-8888-8888-888888888888', '2026 Sem 1', 'A2', 'A', 17, 5, 3, NULL, NULL, 'seed'),

  ('99999999-9999-9999-9999-999999999999', '2024 Sem 1', 'A1', 'A', 15, 7, 5, NULL, NULL, 'seed'),
  ('99999999-9999-9999-9999-999999999999', '2025 Sem 1', 'A1', 'A', 19, 8, 6, NULL, NULL, 'seed'),
  ('99999999-9999-9999-9999-999999999999', '2026 Sem 1', 'A1', 'A', 22, 8, 7, NULL, NULL, 'seed'),

  -- Band B and C — writing is administered, phonics matters less
  ('33333333-3333-3333-3333-333333333333', '2024 Sem 1', 'B4', 'B', 12, 7, 5, 10, 'narrative_writing', 'seed'),
  ('33333333-3333-3333-3333-333333333333', '2025 Sem 1', 'B4', 'B', 15, 8, 6, 13, 'narrative_writing', 'seed'),
  ('33333333-3333-3333-3333-333333333333', '2026 Sem 1', 'B5', 'B', 17, 8, 7, 15, 'narrative_writing', 'seed'),

  ('77777777-7777-7777-7777-777777777777', '2024 Sem 1', 'B5', 'B', 14, 8, 6, 12, 'narrative_writing', 'seed'),
  ('77777777-7777-7777-7777-777777777777', '2025 Sem 1', 'B5', 'B', 16, 8, 7, 15, 'narrative_writing', 'seed'),
  ('77777777-7777-7777-7777-777777777777', '2026 Sem 1', 'B6', 'B', 19, 9, 8, 18, 'exposition_writing', 'seed'),

  ('55555555-5555-5555-5555-555555555555', '2024 Sem 1', 'C7', 'C',  8, 8, 6, 14, 'exposition_writing', 'seed'),
  ('55555555-5555-5555-5555-555555555555', '2025 Sem 1', 'C7', 'C', 10, 9, 7, 16, 'exposition_writing', 'seed'),
  ('55555555-5555-5555-5555-555555555555', '2026 Sem 1', 'C8', 'C', 12, 9, 8, 19, 'persuasive_writing', 'seed'),

  ('00000000-0000-0000-0000-000000000000', '2024 Sem 1', 'C7', 'C',  6, 7, 5, 11, 'narrative_writing', 'seed'),
  ('00000000-0000-0000-0000-000000000000', '2025 Sem 1', 'C8', 'C',  8, 8, 6, 13, 'exposition_writing', 'seed'),
  ('00000000-0000-0000-0000-000000000000', '2026 Sem 1', 'C8', 'C',  9, 8, 6, 16, 'persuasive_writing', 'seed')
ON CONFLICT (learner_id, semester) DO NOTHING;

-- Percentiles, by the SAME RULE the ingest uses: rank within (semester, band_group), so a mark
-- is compared against everyone who sat the same paper in the same semester rather than against
-- a cohort that changes underneath it.
--
-- `cume_dist()` is the SQL analogue of the pandas `rank(pct=True)` in dial_workbook.percentiles.
--
-- ⚠ THE POPULATION HERE IS TEN LEARNERS, so these come out coarse — 33rd, 67th, 100th — and are
-- NOT comparable to percentiles from the real 5,783-student cohort. They exist so the radar
-- chart and the percentile scale have something truthful to draw in a seeded project. Running
-- the ingest overwrites them with the real thing.
--
-- The CASE keeps an unassessed paper unranked: band A has no writing mark, and a 0th percentile
-- would say the learner came last on a paper they never sat. Exact here because writing is
-- either absent for the whole partition (band A) or present for all of it (B and C).
WITH ranked AS (
  SELECT
    id,
    round((cume_dist() OVER (PARTITION BY semester, band_group ORDER BY phonics))::numeric * 100, 1)               AS p_pct,
    round((cume_dist() OVER (PARTITION BY semester, band_group ORDER BY word_reading_accuracy))::numeric * 100, 1) AS w_pct,
    round((cume_dist() OVER (PARTITION BY semester, band_group ORDER BY word_spelling))::numeric * 100, 1)         AS s_pct,
    CASE WHEN writing IS NULL THEN NULL ELSE
      round((cume_dist() OVER (PARTITION BY semester, band_group ORDER BY writing))::numeric * 100, 1)
    END                                                                                                            AS wr_pct
  FROM learner_sittings
  WHERE source = 'seed'
)
UPDATE learner_sittings s SET
  phonics_pct               = r.p_pct,
  word_reading_accuracy_pct = r.w_pct,
  word_spelling_pct         = r.s_pct,
  writing_pct               = r.wr_pct
FROM ranked r
WHERE r.id = s.id;

-- Make the newest sitting each learner's CURRENT marks — the same promotion the "Generate
-- Profile" button performs, so the dashboard, the radar chart and activity generation all agree
-- with the chart without anyone having to press it first.
UPDATE learners l SET
  semester = s.semester, band = s.band, band_group = s.band_group,
  phonics = s.phonics, word_reading_accuracy = s.word_reading_accuracy,
  word_spelling = s.word_spelling, writing = s.writing, writing_genre = s.writing_genre,
  phonics_pct = s.phonics_pct, word_reading_accuracy_pct = s.word_reading_accuracy_pct,
  word_spelling_pct = s.word_spelling_pct, writing_pct = s.writing_pct
FROM (
  SELECT DISTINCT ON (learner_id) *
  FROM learner_sittings
  -- Seeded learners only. Unscoped, this would re-promote all ~5,783 cohort rows after an
  -- ingest — the same values they already carry, but thousands of pointless writes from a
  -- script whose job is the ten mock learners.
  WHERE learner_id IN (SELECT learner_id FROM learner_sittings WHERE source = 'seed')
  ORDER BY learner_id, semester DESC
) s
WHERE s.learner_id = l.id;

-- 4. Insert mock Tasks
INSERT INTO tasks (title, meta, status)
SELECT * FROM (VALUES
  ('Review flagged activity for Learner A', 'Due today · Subsystem 3', 'DONE'),
  ('Upload assessment for Learner D', 'Due today · Subsystem 2', 'PENDING'),
  ('Generate profile for Learner C', 'Due today · Subsystem 2', 'PENDING'),
  ('Generate activity for Learner B', 'Due today · Subsystem 3', 'PENDING'),
  ('Share Learner A''s progress report', 'Jul 22 · Email to parent', 'PENDING'),
  ('Re-assess Learner E (high risk)', 'Jul 28 · Scheduled', 'PENDING')
) AS v(title, meta, status)
WHERE NOT EXISTS (SELECT 1 FROM tasks);

-- 5. Insert mock Calendar Events
INSERT INTO calendar_events (event_date, description)
SELECT * FROM (VALUES
  ('2026-07-03'::date, 'Event 1'),
  ('2026-07-07', 'Event 2'),
  ('2026-07-14', 'Event 3'),
  ('2026-07-20', 'Event 4'),
  ('2026-07-22', 'Event 5'),
  ('2026-07-28', 'Event 6')
) AS v(event_date, description)
WHERE NOT EXISTS (SELECT 1 FROM calendar_events);
