-- Subsystem 3 — scope curriculum retrieval to a learner's BAND GROUP.
--
-- WHY
--   A learner must only ever be grounded in their own band's curriculum. `filter_band` could not
--   express that. It is exact-equality, and the corpus stores 'A' for the 90 unlevelled Band A
--   chunks but 'A1'/'A2'/'A3' for the three band books — so filter_band => 'A' misses the books,
--   and filter_band => 'A3' finds only that one book's 4 chunks. Meanwhile `learners.band_group`
--   is a plain letter, so nothing on the learner side could be handed to this filter at all. The
--   UI's workaround was to send NO band for any B or C learner, which silently grounded Band B
--   learners in Band A material.
--
--   `filter_band_group` matches on the letter, so a Band A learner reaches all 120 A-chunks and a
--   Band B learner reaches exactly the 159 B-chunks. A band with no corpus (C today) returns zero
--   rows, and the caller refuses rather than widening — see ActivityGenerationService.
--
--   `filter_band` is kept, unchanged, for exact-band use from the CLI (`--band A1`). The two AND
--   together, so passing both narrows to a single level within a group.
--
-- WHY DROP RATHER THAN `create or replace`
--   A function's argument list is part of its identity. Adding a parameter to a `create or
--   replace` creates a SECOND function rather than replacing the first, and PostgREST then cannot
--   resolve `rpc('match_curriculum', ...)` between the two — it fails with an ambiguity error at
--   call time, not at deploy time. Both old signatures must go first.
--
-- IDEMPOTENT: the drops are `if exists`, and the creates are full definitions.

-- ── 1. Remove the old signatures ─────────────────────────────────────────────
drop function if exists match_curriculum(vector, text, text, text, int);
drop function if exists hybrid_match_curriculum(
  vector, text, text, text, text, int, int, float, float, int
);

-- ── 2. Pure vector retrieval, band-group scoped ──────────────────────────────
create or replace function match_curriculum(
  query_embedding vector(768),
  filter_band text default null,           -- exact band, e.g. 'A1' (CLI)
  filter_band_group text default null,     -- band LETTER, e.g. 'A' (every A* chunk)
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
    and (filter_band       is null or c.band = filter_band)
    and (filter_band_group is null or left(c.band, 1) = filter_band_group)
    and (filter_concept    is null or c.concept = filter_concept)
    and (filter_stage      is null or c.stage = filter_stage)
  order by c.embedding <=> query_embedding
  limit match_count;
$$;

-- ── 3. Hybrid retrieval, band-group scoped ───────────────────────────────────
-- The band filter lives in the `filtered` CTE, so it applies BEFORE either ranking arm sees a
-- row: out-of-band chunks are never candidates for the vector side or the keyword side, and
-- cannot be resurrected by RRF fusion.
create or replace function hybrid_match_curriculum(
  query_embedding vector(768),
  query_text text,
  filter_band text default null,
  filter_band_group text default null,
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
      and (filter_band       is null or c.band = filter_band)
      and (filter_band_group is null or left(c.band, 1) = filter_band_group)
      and (filter_concept    is null or c.concept = filter_concept)
      and (filter_stage      is null or c.stage = filter_stage)
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

-- ── 4. Verify ────────────────────────────────────────────────────────────────
-- Both counts must be 1. A 2 means a drop was skipped and an overload survives, which PostgREST
-- cannot disambiguate — rerun step 1 with the old signature spelled exactly.
select
  (select count(*) from pg_proc where proname = 'match_curriculum')        as match_curriculum,
  (select count(*) from pg_proc where proname = 'hybrid_match_curriculum') as hybrid_match;
