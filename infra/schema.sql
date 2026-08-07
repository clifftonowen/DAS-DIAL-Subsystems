-- DAS D.I.A.L schema (Subsystems 2 & 3). Run in Supabase SQL editor.
create extension if not exists vector;

-- Therapists mirror Supabase auth.users (id = auth uid)
create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  auth_user_id uuid references auth.users(id),
  email text unique not null,
  name text default ''
);

-- ============================================================
-- EVERY learner, of both kinds, in one table.
--
--   on_caseload = true    the therapist's own learners. Have a pseudonym and a tier; the only
--                         ones with assessment_records, generated profiles and activities.
--   on_caseload = false   the anonymised DAS research cohort behind the analytics scatter
--                         (~5,783 rows, loaded by `python -m scripts.ingest_dial_data`).
--                         Identified only by student_id; no pseudonym, no tier.
--
-- These were two tables (`learners` and `learner_scores`) joined by a nullable self-FK. They
-- describe the same kind of thing, stored band twice in two disagreeing spellings, and gave one
-- person two identities — see infra/migrations/2026-08-07_merge_learner_scores.sql.
--
-- THE TABLE IS LARGE. PostgREST caps a select at 1,000 rows and TRUNCATES WITHOUT ERRORING, so
-- every full read pages (LearnerRepository.list_cohort) and every count is a count(), never
-- len(rows). An unpaged `select("*")` here quietly returns a sixth of the table.
-- ============================================================
create table if not exists learners (
  id uuid primary key default gen_random_uuid(),

  -- Anonymised workbook key, e.g. 'Student 0001'. NULL for a learner created in the app, which
  -- is why it cannot be the primary key. Unique so the ingest can upsert on it: the workbook
  -- has no idea what a uuid is.
  student_id text unique,

  -- Caseload identity. Empty for cohort rows — the cohort is anonymised research data.
  pseudonym text default '',
  tier text default '',
  on_caseload boolean not null default false,

  band       text,                        -- NewBand: A1..C9
  band_group text,                        -- 'A' | 'B' | 'C' — the clustering + percentile scope
  semester     text,                      -- the most recent sitting on record
  school_level text,
  age          int,

  phonics               real,             -- \
  word_reading_accuracy real,             --  > the clustering features
  word_spelling         real,             -- /
  writing            real,                -- plottable, not clustered (absent for band A)
  writing_genre      text,
  narrative_writing  real,                -- \
  exposition_writing real,                --  > mutually exclusive; provenance for `writing`
  persuasive_writing real,                -- /
  fluency_mark real,                      -- = 2 x word_reading_accuracy; never clustered

  -- Percentile rank of each mark WITHIN THE LEARNER'S BAND GROUP, computed at ingest. The
  -- profile page's radar chart shares one radius across axes, and the rubric differs by band
  -- (phonics maxes at 25 in A1, 46 in A3) — so neither raw marks nor percent-of-max can go on
  -- it. Null means not assessed, never "bottom of the cohort".
  -- See infra/migrations/2026-08-06_score_percentiles.sql.
  phonics_pct               real,
  word_reading_accuracy_pct real,
  word_spelling_pct         real,
  writing_pct               real,

  -- TWO clustering scopes, stored side by side so the dashboard can toggle between them.
  --   cluster_band    '<band_group> <rank>', e.g. 'B 2' — one model per band group
  --   cluster_cohort  'Cohort <rank>'        — one model over everyone
  -- Different populations: every scored learner gets a cluster_cohort, but the 3 whose band is
  -- missing fall below MIN_GROUP and get no cluster_band.
  cluster_band   text,
  cluster_cohort text,
  updated_at timestamptz default now()
);
create index if not exists idx_learners_cluster_band   on learners (cluster_band);
create index if not exists idx_learners_cluster_cohort on learners (cluster_cohort);
create index if not exists idx_learners_band_group     on learners (band_group);
-- The Learners tab filters on this by default, and it is true for ~10 rows out of thousands.
create index if not exists idx_learners_on_caseload    on learners (on_caseload);

create table if not exists assessment_records (
  id uuid primary key default gen_random_uuid(),
  learner_id uuid references learners(id) on delete cascade,
  assessment_date date default now(),
  risk_score float default 0,
  task_results jsonb default '{}',
  strengths text[] default '{}',
  weaknesses text[] default '{}',
  confidence_score float default 0
);

-- One row per learner per SEMESTER — the score history behind the profile page's line chart.
--
-- Different grain from `learners`, which holds one row per person with their CURRENT marks.
-- The workbook carries ~22,892 sittings for 5,783 students across nine semesters; the ingest
-- writes all of them here and the newest one onto `learners`.
--
-- Replaced `learner_profiles` and its seven derived cognitive dimensions, which were mock
-- scaffolding — see infra/migrations/2026-08-08_dial_dimensions.sql.
create table if not exists learner_sittings (
  id uuid primary key default gen_random_uuid(),
  learner_id uuid not null references learners(id) on delete cascade,
  semester text not null,                 -- '2024 Sem 1' — sorts chronologically as text

  -- The paper sat THAT semester: phonics is out of 30 in A2 and 46 in A3, so the band a mark
  -- should be read against belongs to the sitting, not to the learner.
  band       text,
  band_group text,

  phonics               real,
  word_reading_accuracy real,
  word_spelling         real,
  writing               real,
  writing_genre         text,

  -- Percentile within (semester, band_group), so the line moves as the learner does rather
  -- than as the cohort around them changes.
  phonics_pct               real,
  word_reading_accuracy_pct real,
  word_spelling_pct         real,
  writing_pct               real,

  -- 'workbook' (the ingest) | 'upload' (UC1's confirm step) | 'seed' (infra/seed.sql's
  -- ten mock learners). Provenance only — nothing branches on it, but it is how you tell
  -- a demo row from a real mark.
  source text not null default 'workbook',
  created_at timestamptz default now(),
  unique (learner_id, semester)             -- the ingest's upsert key
);
create index if not exists idx_sittings_learner on learner_sittings (learner_id, semester desc);

-- One row per k-means fit — the cohort model plus one per band group — so the dashboard can
-- show how each k was chosen and compare the two scopes.
create table if not exists clustering_runs (
  id              uuid primary key default gen_random_uuid(),
  scope           text not null default 'band',  -- 'cohort' | 'band'
  tier            text not null,          -- 'Cohort', or the band group this model was fitted on
  features        text[] not null,
  k               int not null,           -- chosen by best silhouette, not configured
  best_silhouette real not null,
  silhouette_by_k jsonb not null,         -- the whole k = 2..10 sweep
  n_learners      int not null,
  created_at      timestamptz default now()
);
create index if not exists idx_clustering_runs_scope
  on clustering_runs (scope, tier, created_at desc);

-- RAG corpus: ELL-MLP teaching resources embedded for retrieval
create table if not exists instructional_strategies (
  id uuid primary key default gen_random_uuid(),
  content text not null,
  source text default '',
  tags text[] default '{}',
  embedding vector(1536)
);
create index if not exists idx_strategies_embedding
  on instructional_strategies using ivfflat (embedding vector_cosine_ops) with (lists = 100);

create table if not exists learning_activities (
  id uuid primary key default gen_random_uuid(),
  -- Was `profiled uuid references learner_profiles(id)`. Points at the learner directly now
  -- that the profile IS their marks — there is no separate profile row to hang it off.
  learner_id uuid references learners(id),
  content jsonb default '{}',
  literacy_objective text default '',
  level text default '',
  status text default 'GENERATED',       -- GENERATED / VALIDATED / FLAGGED
  grounded_on text[] default '{}',
  created_at timestamptz default now()
);
create index if not exists idx_activities_learner on learning_activities (learner_id);

create table if not exists reviews (
  id uuid primary key default gen_random_uuid(),
  activity_id uuid references learning_activities(id) on delete cascade,
  therapist_id uuid references users(id),
  text text default '',
  created_at timestamptz default now()
);

create table if not exists tasks (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  meta text default '',
  status text default 'PENDING',
  created_at timestamptz default now()
);

create table if not exists calendar_events (
  id uuid primary key default gen_random_uuid(),
  event_date date not null,
  description text default '',
  created_at timestamptz default now()
);

-- Similarity search used by KnowledgeBaseRepository.similarity_search()
create or replace function match_strategies(query_embedding vector(1536), match_count int)
returns table (id uuid, content text, source text, tags text[], similarity float)
language sql stable as $$
  select id, content, source, tags,
         1 - (embedding <=> query_embedding) as similarity
  from instructional_strategies
  order by embedding <=> query_embedding
  limit match_count;
$$;

-- ============================================================
-- Subsystem 3: curriculum corpus (RAG exemplars)
-- Distinct from instructional_strategies (ELL-MLP strategy corpus)
-- and from learning_activities (generated, per-learner output).
-- ============================================================
create table if not exists curriculum_chunks (
  id uuid primary key default gen_random_uuid(),

  -- filters
  band text not null,                      -- 'A' | 'B' | 'C' (matches learners.band_group), or
                                           -- 'A1'|'A2'|'A3' for the three levelled band books
  module text,                             -- 'Barebone Sentence' | 'Predicate Expanders'
  concept text not null,                   -- 'action_predicate' | 'all' | ...  <- curriculum join key
  stage text,                              -- 'presentation' | 'practice' | 'production' | ...
  sequence_no int default 1,               -- Practice worksheet 1 vs 2 vs 3
  doc_type text not null default 'lesson_plan',   -- lesson_plan | resource
  writing_traits text[] default '{}',      -- 6+1, lowercased; optional filter (63% coverage)
  -- Free-text construct tags on a curriculum chunk. Used to bridge to a learner's needs; the
  -- seven cognitive floats they were written against are gone, and the four DIAL metrics are
  -- what a learner is described by now. Retrieval matches on band/concept/stage regardless.
  cognitive_constructs text[] default '{}',

  -- content (fed to the LLM after retrieval)
  activity_title text,                     -- body heading; best discriminator on metadata ties
  content_md text not null,                -- full worksheet / teaching text
  answer_key text,
  objective text,

  -- guardrail
  prerequisites text[] default '{}',       -- scope-and-sequence as data

  -- provenance
  source_file text not null,
  page_start text,
  page_end text,

  -- vector + bookkeeping
  embedding vector(768),                    -- incumbent model (see embedding_model for which)
  embedding_model text,

  -- Challenger slot, for evaluating a second embedding model without destroying the incumbent's
  -- vectors. Both are 768-dim so they are interchangeable at the RPC boundary; which one ranks is
  -- chosen per-call by `use_alt`. NULL until something re-embeds into it.
  embedding_alt vector(768),
  embedding_alt_model text,

  ingest_version text,
  raw_header text,                         -- debugging
  embed_text text,                         -- optional: "why did this match?"

  -- reserved for v2 (create, leave empty)
  skills text[] not null default '{}',

  -- full-text search (hybrid retrieval keyword side); generated + stored, filled by Postgres
  fts tsvector generated always as (
    to_tsvector('english', coalesce(activity_title, '') || ' ' || coalesce(content_md, ''))
  ) stored
);

create index if not exists idx_curriculum_embedding
  on curriculum_chunks using hnsw (embedding vector_cosine_ops);
create index if not exists idx_curriculum_embedding_alt
  on curriculum_chunks using hnsw (embedding_alt vector_cosine_ops);
create index if not exists idx_curriculum_fts
  on curriculum_chunks using gin (fts);
create index if not exists idx_curriculum_filter
  on curriculum_chunks (band, module, concept, stage);
create index if not exists idx_curriculum_traits
  on curriculum_chunks using gin (writing_traits);
create index if not exists idx_curriculum_constructs
  on curriculum_chunks using gin (cognitive_constructs);
create index if not exists idx_curriculum_source
  on curriculum_chunks (source_file);

-- Mirrors match_strategies(); used by CurriculumRepository.match_curriculum().
-- Filters run in WHERE (correctness); the vector only ranks survivors (relevance).
-- TWO band filters, and they mean different things. `filter_band` is exact ('A1'), for the CLI.
-- `filter_band_group` is the LETTER ('A'), and is what a learner is scoped by: learners carry
-- band_group, and a Band A learner must reach all 120 A-chunks — the 90 stored as 'A' plus the
-- three band books stored as 'A1'/'A2'/'A3'. See 2026-08-09_curriculum_band_group_filter.sql.
create or replace function match_curriculum(
  query_embedding vector(768),
  filter_band text default null,
  filter_band_group text default null,
  filter_concept text default null,
  filter_stage text default null,
  match_count int default 3,
  use_alt boolean default false        -- false => `embedding` (incumbent), true => `embedding_alt`
)
returns table (
  id uuid, activity_title text, content_md text, answer_key text,
  concept text, stage text, source_file text, page_start text, similarity float
)
language sql stable as $$
  select c.id, c.activity_title, c.content_md, c.answer_key,
         c.concept, c.stage, c.source_file, c.page_start,
         1 - ((case when use_alt then c.embedding_alt else c.embedding end) <=> query_embedding)
           as similarity
  from curriculum_chunks c
  where c.doc_type = 'lesson_plan'
    and (case when use_alt then c.embedding_alt else c.embedding end) is not null
    and (filter_band       is null or c.band = filter_band)
    and (filter_band_group is null or left(c.band, 1) = filter_band_group)
    and (filter_concept    is null or c.concept = filter_concept)
    and (filter_stage      is null or c.stage = filter_stage)
  order by (case when use_alt then c.embedding_alt else c.embedding end) <=> query_embedding
  limit match_count;
$$;

-- Hybrid retrieval: vector (semantic) + full-text (keyword), fused by Reciprocal Rank Fusion.
-- RRF is scale-free (ranks, not raw scores), so cosine similarity and ts_rank need no normalising.
-- Empty query_text or no keyword hit => keyword CTE is empty => graceful fall back to pure vector.
-- Returns match_curriculum's columns plus `score` (the fused RRF score used for ordering).
create or replace function hybrid_match_curriculum(
  query_embedding vector(768),
  query_text text,
  filter_band text default null,
  filter_band_group text default null,
  filter_concept text default null,
  filter_stage text default null,
  match_count int default 3,
  rrf_k int default 50,               -- RRF smoothing constant (larger => flatter rank weighting)
  full_text_weight float default 1.0,
  semantic_weight float default 1.0,
  candidate_pool int default 50,      -- rows each side contributes before fusion
  use_alt boolean default false       -- false => `embedding` (incumbent), true => `embedding_alt`
)
returns table (
  id uuid, activity_title text, content_md text, answer_key text,
  concept text, stage text, source_file text, page_start text,
  similarity float, score float
)
language sql stable as $$
  -- Band filtering lives HERE, not after ranking: out-of-band chunks are never candidates for
  -- either arm, so RRF fusion cannot resurrect one.
  with filtered as (
    select *, (case when use_alt then c.embedding_alt else c.embedding end) as vec
    from curriculum_chunks c
    where c.doc_type = 'lesson_plan'
      and (filter_band       is null or c.band = filter_band)
      and (filter_band_group is null or left(c.band, 1) = filter_band_group)
      and (filter_concept    is null or c.concept = filter_concept)
      and (filter_stage      is null or c.stage = filter_stage)
  ),
  semantic as (
    select f.id,
           row_number() over (order by f.vec <=> query_embedding) as rank,
           1 - (f.vec <=> query_embedding) as similarity
    from filtered f
    where f.vec is not null
    order by f.vec <=> query_embedding
    limit candidate_pool
  ),
  keyword as (
    select f.id,
           row_number() over (
             order by ts_rank_cd(f.fts, websearch_to_tsquery('english', query_text)) desc
           ) as rank
    from filtered f
    where query_text is not null and query_text <> ''
      and f.fts @@ websearch_to_tsquery('english', query_text)
    order by ts_rank_cd(f.fts, websearch_to_tsquery('english', query_text)) desc
    limit candidate_pool
  )
  select f.id, f.activity_title, f.content_md, f.answer_key,
         f.concept, f.stage, f.source_file, f.page_start,
         s.similarity,
         coalesce(semantic_weight  / (rrf_k + s.rank), 0.0)
       + coalesce(full_text_weight / (rrf_k + k.rank), 0.0) as score
  from filtered f
  left join semantic s on s.id = f.id
  left join keyword  k on k.id = f.id
  where s.id is not null or k.id is not null
  order by score desc
  limit match_count;
$$;
