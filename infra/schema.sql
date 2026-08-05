-- DAS D.I.A.L schema (Subsystems 2 & 3). Run in Supabase SQL editor.
create extension if not exists vector;

-- Therapists mirror Supabase auth.users (id = auth uid)
create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  auth_user_id uuid references auth.users(id),
  email text unique not null,
  name text default ''
);

create table if not exists learners (
  id uuid primary key default gen_random_uuid(),
  pseudonym text not null,
  band_level text not null,        -- Band A / B / C
  tier text default ''
);

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

create table if not exists learner_profiles (
  id uuid primary key default gen_random_uuid(),
  learner_id uuid references learners(id) on delete cascade,
  phonological_processing float default 0,
  decoding float default 0,
  spelling float default 0,
  comprehension float default 0,
  working_memory float default 0,
  executive_functioning float default 0,
  visualisation float default 0,
  created_at timestamptz default now()
);

-- ============================================================
-- Subsystem 2: the anonymised DAS research cohort + its k-means clusters.
-- Distinct from `learners` (the therapist's own caseload) — see
-- infra/migrations/2026-08-05_learner_scores.sql for the full rationale on every column.
-- Loaded by `python -m scripts.ingest_dial_data` from backend/.
-- ============================================================
create table if not exists learner_scores (
  student_id   text primary key,          -- anonymised, e.g. 'Student 0001'
  learner_id   uuid references learners(id) on delete set null,
  semester     text not null,             -- the most recent sitting on record
  band         text,                      -- NewBand: A1..C9
  band_group   text,                      -- 'A' | 'B' | 'C' — the clustering scope
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

  -- TWO clustering scopes, stored side by side so the dashboard can toggle between them.
  --   cluster_band    '<band_group> <rank>', e.g. 'B 2' — one model per band group
  --   cluster_cohort  'Cohort <rank>'        — one model over everyone
  -- Different populations: every learner gets a cluster_cohort, but the 3 whose band is
  -- missing fall below MIN_GROUP and get no cluster_band.
  cluster_band   text,
  cluster_cohort text,
  updated_at timestamptz default now()
);
create index if not exists idx_learner_scores_cluster_band   on learner_scores (cluster_band);
create index if not exists idx_learner_scores_cluster_cohort on learner_scores (cluster_cohort);
create index if not exists idx_learner_scores_band           on learner_scores (band_group);

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
  profiled uuid references learner_profiles(id),
  content jsonb default '{}',
  literacy_objective text default '',
  level text default '',
  status text default 'GENERATED',       -- GENERATED / VALIDATED / FLAGGED
  grounded_on text[] default '{}',
  created_at timestamptz default now()
);

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
  band text not null,                      -- 'A1' | 'A2' | 'A3'  (finer than learners.band_level)
  module text,                             -- 'Barebone Sentence' | 'Predicate Expanders'
  concept text not null,                   -- 'action_predicate' | 'all' | ...  <- curriculum join key
  stage text,                              -- 'presentation' | 'practice' | 'production' | ...
  sequence_no int default 1,               -- Practice worksheet 1 vs 2 vs 3
  doc_type text not null default 'lesson_plan',   -- lesson_plan | resource
  writing_traits text[] default '{}',      -- 6+1, lowercased; optional filter (63% coverage)
  cognitive_constructs text[] default '{}',-- bridge to learner_profiles' seven floats

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
  embedding vector(768),                    -- nomic-embed-text (Ollama, default provider)
  embedding_model text,
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
create or replace function match_curriculum(
  query_embedding vector(768),
  filter_band text default null,
  filter_concept text default null,
  filter_stage text default null,
  match_count int default 3
)
returns table (
  id uuid, activity_title text, content_md text, answer_key text,
  concept text, stage text, source_file text, page_start text, similarity float
)
language sql stable as $$
  select c.id, c.activity_title, c.content_md, c.answer_key,
         c.concept, c.stage, c.source_file, c.page_start,
         1 - (c.embedding <=> query_embedding) as similarity
  from curriculum_chunks c
  where c.doc_type = 'lesson_plan'
    and (filter_band    is null or c.band    = filter_band)
    and (filter_concept is null or c.concept = filter_concept)
    and (filter_stage   is null or c.stage   = filter_stage)
  order by c.embedding <=> query_embedding
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
  filter_concept text default null,
  filter_stage text default null,
  match_count int default 3,
  rrf_k int default 50,               -- RRF smoothing constant (larger => flatter rank weighting)
  full_text_weight float default 1.0,
  semantic_weight float default 1.0,
  candidate_pool int default 50       -- rows each side contributes before fusion
)
returns table (
  id uuid, activity_title text, content_md text, answer_key text,
  concept text, stage text, source_file text, page_start text,
  similarity float, score float
)
language sql stable as $$
  with filtered as (
    select * from curriculum_chunks c
    where c.doc_type = 'lesson_plan'
      and (filter_band    is null or c.band    = filter_band)
      and (filter_concept is null or c.concept = filter_concept)
      and (filter_stage   is null or c.stage   = filter_stage)
  ),
  semantic as (
    select f.id,
           row_number() over (order by f.embedding <=> query_embedding) as rank,
           1 - (f.embedding <=> query_embedding) as similarity
    from filtered f
    where f.embedding is not null
    order by f.embedding <=> query_embedding
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
