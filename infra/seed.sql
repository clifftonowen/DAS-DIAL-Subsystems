-- Seed script to populate mock data into Supabase tables
-- Run this in the Supabase SQL editor after running schema.sql

-- 1. Insert mock Learners
INSERT INTO learners (id, pseudonym, band_level, tier) VALUES
('11111111-1111-1111-1111-111111111111', 'Aisha Binti Rahman', 'Band A2', 'Tier 2'),
('22222222-2222-2222-2222-222222222222', 'Benjamin Lim Wei', 'Band A1', 'Tier 1'),
('33333333-3333-3333-3333-333333333333', 'Chen Yu Xuan', 'Band B', 'Tier 2'),
('44444444-4444-4444-4444-444444444444', 'Darren Tan Kai', 'Band A3', 'Tier 3'),
('55555555-5555-5555-5555-555555555555', 'Emily Ng Su Lin', 'Band C', 'Tier 1'),
('66666666-6666-6666-6666-666666666666', 'Farhan Bin Ismail', 'Band A1', 'Tier 2'),
('77777777-7777-7777-7777-777777777777', 'Grace Wong Mei', 'Band B', 'Tier 1'),
('88888888-8888-8888-8888-888888888888', 'Hassan Ali Khan', 'Band A2', 'Tier 3'),
('99999999-9999-9999-9999-999999999999', 'Isabelle Lau Xin', 'Band A1', 'Tier 1'),
('00000000-0000-0000-0000-000000000000', 'Jamal Syed Ahmad', 'Band C', 'Tier 2')
ON CONFLICT (id) DO NOTHING;

-- 2. Insert mock Assessment Records
INSERT INTO assessment_records (learner_id, assessment_date, risk_score) VALUES
('11111111-1111-1111-1111-111111111111', '2026-07-01', 0.2),
('22222222-2222-2222-2222-222222222222', '2026-07-02', 0.1),
('33333333-3333-3333-3333-333333333333', '2026-07-03', 0.3),
('44444444-4444-4444-4444-444444444444', '2026-07-04', 0.4),
('55555555-5555-5555-5555-555555555555', '2026-07-05', 0.89);

-- 3. Insert mock Learner Profiles
-- Profile for Aisha
INSERT INTO learner_profiles (learner_id, phonological_processing, decoding, spelling, comprehension, working_memory, executive_functioning, visualisation) VALUES
('11111111-1111-1111-1111-111111111111', 0.35, 0.55, 0.40, 0.72, 0.28, 0.60, 0.65),
('22222222-2222-2222-2222-222222222222', 0.60, 0.45, 0.52, 0.38, 0.70, 0.55, 0.48),
('33333333-3333-3333-3333-333333333333', 0.78, 0.70, 0.65, 0.80, 0.45, 0.72, 0.58),
('44444444-4444-4444-4444-444444444444', 0.20, 0.30, 0.25, 0.45, 0.35, 0.40, 0.50),
('55555555-5555-5555-5555-555555555555', 0.42, 0.38, 0.30, 0.55, 0.60, 0.50, 0.72),
('66666666-6666-6666-6666-666666666666', 0.55, 0.62, 0.58, 0.70, 0.40, 0.65, 0.45),
('77777777-7777-7777-7777-777777777777', 0.85, 0.78, 0.72, 0.90, 0.65, 0.80, 0.70),
('88888888-8888-8888-8888-888888888888', 0.30, 0.25, 0.20, 0.35, 0.22, 0.28, 0.40),
('99999999-9999-9999-9999-999999999999', 0.68, 0.75, 0.70, 0.82, 0.58, 0.74, 0.62),
('00000000-0000-0000-0000-000000000000', 0.50, 0.48, 0.55, 0.60, 0.42, 0.52, 0.58);

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
