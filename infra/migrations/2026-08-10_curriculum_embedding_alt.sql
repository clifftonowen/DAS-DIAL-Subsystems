-- Add a SECOND embedding column so two embedding models can be evaluated side by side.
--
-- Why: comparing embedding models means re-embedding the corpus, and there is exactly one
-- `embedding` column on a SHARED hosted Supabase. Two people evaluating two models against one
-- column means whoever re-embeds last destroys the other's vectors, and neither run can be
-- repeated. `embedding_alt` holds the challenger; `embedding` stays the incumbent (nomic-embed-text)
-- so the baseline remains queryable at all times.
--
-- `embedding_alt_model` is not decoration: `embedding_model` records the model behind `embedding`
-- only, so without a second column the challenger's vectors would be anonymous — and a vector whose
-- model you cannot name is a vector you cannot trust a measurement from.
--
-- Dated 2026-08-10 to sort AFTER 2026-08-09_curriculum_band_group_filter.sql. That is deliberate,
-- not a typo: this migration redefines the same two functions, so applying it before that one
-- would silently revert filter_band_group.
--
-- Idempotent — safe to re-run. Run in the Supabase SQL editor.

alter table curriculum_chunks add column if not exists embedding_alt vector(768);
alter table curriculum_chunks add column if not exists embedding_alt_model text;

create index if not exists idx_curriculum_embedding_alt
  on curriculum_chunks using hnsw (embedding_alt vector_cosine_ops);

-- Both functions gain `use_alt`, selecting which column ranks. DROP first, always: PostgREST
-- resolves overloads by argument NAME, and two candidates differing only by a defaulted trailing
-- param are ambiguous to it — the RPC then fails at runtime with PGRST203, not at migration time.
-- Same reasoning as 2026-08-09_curriculum_band_group_filter.sql:19-31.
drop function if exists match_curriculum(vector(768), text, text, text, text, int);
drop function if exists hybrid_match_curriculum(
  vector(768), text, text, text, text, text, int, int, float, float, int
);

-- NOTE on `case` and the index: switching column inside the ORDER BY expression means neither HNSW
-- index can serve the scan, so this is a sequential scan over the band-filtered rows. That is a
-- deliberate trade and not a regression worth avoiding: the corpus is 264 lesson_plan chunks, where
-- an exact scan is both microseconds AND more accurate than an approximate HNSW probe. Revisit only
-- if the corpus grows by orders of magnitude, at which point the challenger should have won or lost
-- and this column should be gone.
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

notify pgrst, 'reload schema';
