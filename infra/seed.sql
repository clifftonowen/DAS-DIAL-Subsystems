-- Seed script to populate mock data into Supabase tables
-- Run this in the Supabase SQL editor after running schema.sql

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
INSERT INTO assessment_records (learner_id, assessment_date, risk_score) VALUES
('11111111-1111-1111-1111-111111111111', '2026-07-01', 0.2),
('22222222-2222-2222-2222-222222222222', '2026-07-02', 0.1),
('33333333-3333-3333-3333-333333333333', '2026-07-03', 0.3),
('44444444-4444-4444-4444-444444444444', '2026-07-04', 0.4),
('55555555-5555-5555-5555-555555555555', '2026-07-05', 0.89);

-- 3. Score history — deliberately NOT seeded.
--
-- The seven mock cognitive dimensions that used to live here are gone: the profile is now the
-- four marks DAS actually gives us, and those come from the workbook. Run
-- `python -m scripts.ingest_dial_data` to populate `learners` and `learner_sittings` with real
-- scores; a caseload learner with no sittings correctly shows the upload prompt on their page.

-- 4. Insert mock Tasks
INSERT INTO tasks (title, meta, status) VALUES
('Review flagged activity for Learner A', 'Due today · Subsystem 3', 'DONE'),
('Upload assessment for Learner D', 'Due today · Subsystem 2', 'PENDING'),
('Generate profile for Learner C', 'Due today · Subsystem 2', 'PENDING'),
('Generate activity for Learner B', 'Due today · Subsystem 3', 'PENDING'),
('Share Learner A''s progress report', 'Jul 22 · Email to parent', 'PENDING'),
('Re-assess Learner E (high risk)', 'Jul 28 · Scheduled', 'PENDING');

-- 5. Insert mock Calendar Events
INSERT INTO calendar_events (event_date, description) VALUES
('2026-07-03', 'Event 1'),
('2026-07-07', 'Event 2'),
('2026-07-14', 'Event 3'),
('2026-07-20', 'Event 4'),
('2026-07-22', 'Event 5'),
('2026-07-28', 'Event 6');
