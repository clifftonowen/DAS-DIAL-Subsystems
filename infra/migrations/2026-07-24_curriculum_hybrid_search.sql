-- Add hybrid search (vector + full-text, RRF) to curriculum_chunks.
--
-- Why: match_curriculum ranks purely by vector cosine similarity, which misses exact curriculum
-- terms (e.g. "CVC", "predicate expander", a specific activity name). This adds a full-text
-- keyword side and a hybrid_match_curriculum RPC that fuses the two rankings via Reciprocal Rank
-- Fusion. schema.sql is fresh-install-only (create ... if not exists), so existing databases need
-- this migration. Idempotent — safe to re-run. Run in the Supabase SQL editor.

-- Generated + stored: Postgres backfills existing rows and maintains it on write. No re-ingest.
alter table curriculum_chunks add column if not exists fts tsvector
  generated always as (
    to_tsvector('english', coalesce(activity_title, '') || ' ' || coalesce(content_md, ''))
  ) stored;

create index if not exists idx_curriculum_fts
  on curriculum_chunks using gin (fts);

create or replace function hybrid_match_curriculum(
  query_embedding vector(768),
  query_text text,
  filter_band text default null,
  filter_concept text default null,
  filter_stage text default null,
  match_count int default 3,
  rrf_k int default 50,
  full_text_weight float default 1.0,
  semantic_weight float default 1.0,
  candidate_pool int default 50
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

notify pgrst, 'reload schema';
