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
  skills text[] not null default '{}'
);

create index if not exists idx_curriculum_embedding
  on curriculum_chunks using hnsw (embedding vector_cosine_ops);
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
