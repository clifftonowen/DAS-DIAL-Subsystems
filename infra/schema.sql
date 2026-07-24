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
