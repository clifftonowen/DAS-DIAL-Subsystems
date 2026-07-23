-- Resize curriculum_chunks.embedding from vector(1536) to vector(768).
--
-- Why: the active embedding provider is Ollama (nomic-embed-text, 768-dim), but the
-- column was sized vector(1536) for OpenAI's text-embedding-3-small. Upserts fail with
-- SQLSTATE 22000 ("expected 1536 dimensions, not 768"). The corpus runs on Ollama, so
-- the column (and the match_curriculum RPC that compares against it) move to 768.
--
-- Safe only while curriculum_chunks holds no 1536-dim rows (ingestion has never
-- completed, so the table is empty). If real 1536 vectors exist, truncate and re-ingest
-- instead — you cannot reinterpret them as 768.
--
-- The hnsw index is dropped first (it's bound to the column's dimension) and recreated after.

drop index if exists idx_curriculum_embedding;

alter table curriculum_chunks
  alter column embedding type vector(768);

create index if not exists idx_curriculum_embedding
  on curriculum_chunks using hnsw (embedding vector_cosine_ops);

-- Retrieval RPC must accept a 768-dim query vector to match the column.
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

notify pgrst, 'reload schema';
