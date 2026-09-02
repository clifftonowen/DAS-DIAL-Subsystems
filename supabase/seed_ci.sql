-- CI-only fixtures. Loaded AFTER ../infra/seed.sql (see db.seed.sql_paths in config.toml), which
-- provides the ten caseload learners and their sittings.
--
-- Everything here used to be a hosted test project set up by hand, and the three GitHub secrets
-- that pointed at it — TEST_THERAPIST_*, TEST_UNSCORED_LEARNER_ID, TEST_SHARE_LEARNER_ID — were
-- the only record of what that setup was. Two of them were never set, which is why the browser
-- tiers could not run. Fixed UUIDs here make those ids literals in the workflow instead: the
-- database is rebuilt from scratch each run, so they cannot drift and cannot go missing.
--
-- Safe to re-run, same as infra/seed.sql.

-- 1. The test therapist. Written straight into auth.users because there is no dashboard to click
-- locally, and GoTrue will not issue a session for a user it cannot find an identity for — the
-- auth.identities row below is not optional, and omitting it fails at sign-in, not at insert.
--
-- crypt()/gen_salt('bf') is how GoTrue hashes passwords, so a row written this way is
-- indistinguishable from one created through the API.
-- The four empty-string token columns are NOT padding. They are nullable in Postgres but GoTrue
-- scans them into non-nullable Go strings, so a NULL makes every sign-in fail with
-- "Database error querying schema" — a 401 that names neither the column nor the row, and reads
-- like bad credentials. Leave them out and the fixture looks fine until login is attempted.
insert into auth.users (
  instance_id, id, aud, role, email, encrypted_password,
  email_confirmed_at, created_at, updated_at,
  raw_app_meta_data, raw_user_meta_data,
  confirmation_token, recovery_token, email_change_token_new, email_change
) values (
  '00000000-0000-0000-0000-000000000000',
  'aaaaaaaa-0000-4000-8000-000000000001',
  'authenticated', 'authenticated',
  'ci-therapist@example.com',
  crypt('ci-test-password-123', gen_salt('bf')),
  -- Confirmed at creation. [auth.email] enable_confirmations is false locally, but stamping this
  -- makes the row correct regardless of that setting rather than dependent on it.
  now(), now(), now(),
  '{"provider":"email","providers":["email"]}', '{}',
  '', '', '', ''
) on conflict (id) do nothing;

insert into auth.identities (
  provider_id, user_id, identity_data, provider, last_sign_in_at, created_at, updated_at
) values (
  'aaaaaaaa-0000-4000-8000-000000000001',
  'aaaaaaaa-0000-4000-8000-000000000001',
  '{"sub":"aaaaaaaa-0000-4000-8000-000000000001","email":"ci-therapist@example.com","email_verified":true,"phone_verified":false}',
  'email', now(), now(), now()
) on conflict (provider, provider_id) do nothing;

-- The public mirror row. AuthService.authenticate backfills this on first login, so the login
-- test would pass without it — but every OTHER test would then be exercising the backfill path
-- instead of the steady state it means to test.
insert into users (id, auth_user_id, email, name)
values ('aaaaaaaa-0000-4000-8000-000000000001',
        'aaaaaaaa-0000-4000-8000-000000000001',
        'ci-therapist@example.com', 'CI Therapist')
on conflict (id) do nothing;

-- 2. TEST_UNSCORED_LEARNER_ID — a caseload learner with NO learner_sittings rows.
-- Drives the refusal branches: UC2's ST-2.2 (409 "no scores on record" -> upload prompt) and
-- UC3's ST-3.2, which refuses before reaching the LLM so no model is needed. infra/seed.sql's
-- ten learners all have three sittings each, so this row cannot come from there.
-- Deliberately no band/band_group either: an unassessed learner has neither.
insert into learners (id, pseudonym, band, band_group, tier, on_caseload)
values ('bbbbbbbb-0000-4000-8000-000000000002', 'Unscored Test Learner', null, null, 'Tier 1', true)
on conflict (id) do nothing;

-- 3. TEST_SHARE_LEARNER_ID — a learner who already has a generated activity. UC7's Share button
-- is disabled without one and UC4's review box only renders under an activity, so both suites
-- need a row that exists before the run starts.
--
-- Reuses Aisha (learner 1111...) rather than inventing an eleventh learner: the share and review
-- flows both read the learner's marks alongside the activity, so it has to be someone who
-- actually has sittings.
-- `content` MUST carry a non-empty "text" key. ActivityPdfRenderer._build_html reads
-- content["text"] and raises "Activity has no content to export" (surfacing as 422) when it is
-- missing, so a fixture with a different shape fails the UC7 share tests rather than the share
-- code being wrong. The three keys here are exactly what
-- ActivityGenerationService writes at activity_generation_service.py:171.
insert into learning_activities (
  id, learner_id, content, literacy_objective, level, status, retry_count, grounded_on
) values (
  'cccccccc-0000-4000-8000-000000000003',
  '11111111-1111-1111-1111-111111111111',
  '{"text":"Step 1: Read the passage aloud.\nStep 2: Underline each initial blend you hear.\nStep 3: Sort the words you underlined by their first two letters.","query":"consonant blends initial position band A2","grounding":[]}',
  'Consonant blends in initial position', 'A2', 'VALIDATED', 0, '{}'
) on conflict (id) do nothing;
