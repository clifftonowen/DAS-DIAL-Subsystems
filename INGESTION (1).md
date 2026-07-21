# INGESTION.md — DAS3 Curriculum Ingestion (build spec for Claude Code)

Build the **offline curriculum ingestion pipeline** for Subsystem 3: turn DAS Band-A
curriculum PDFs into metadata-tagged, embedded chunks in Supabase, so the
`ActivityGraph` can retrieve grounded exemplars.

**This slots into the EXISTING DAS D.I.A.L backend.** Do not create a standalone project.
Follow the existing Controller → Service → Repository → (Entity / Agent / Gateway) layering.

**Read the whole file before writing code. Follow "Build order".** The chunking strategy
below was validated against all 14 real curriculum books — do not substitute a different one.

---

## ⚠️ Known schema conflict — read before building

The existing `learner_profiles` table stores **seven cognitive constructs**:

```sql
phonological_processing, decoding, spelling, comprehension,
working_memory, executive_functioning, visualisation
```

**There is no field that joins a profile to a curriculum concept.** `decoding = 0.35` does
not tell the system to retrieve "Action Predicate, practice worksheet".

This matters unevenly across the corpus:

| Books | Teaches | Maps to a construct? |
|---|---|---|
| `2_A1`, `3_A2`, `4_A3` (3 books, 120pp) | phonemic awareness, alphabet knowledge, oracy | **Yes** → decoding / phonological_processing / visualisation |
| 11 Project Read books (187pp) | Barebone Sentence, Predicate Expanders (sentence construction) | **No clean mapping** to any of the seven |

**Resolution (pending client + team confirmation):** ingest with `concept` as the curriculum
key regardless, and additionally tag each chunk with `cognitive_constructs text[]` naming
which of the seven it plausibly develops. That gives two possible join paths:

- `concept` → precise, but requires the profile to gain a curriculum-competency layer
- `cognitive_constructs` → works with `learner_profiles` **today**, but coarse

**Build both columns. Do not block on the answer.** Flag to the team that
`learner_profiles` likely needs a per-concept competency layer added for Subsystem 3 to
retrieve precisely. See "Open questions".

**Second conflict:** `learners.band_level` is `Band A / B / C`, but the curriculum is
banded `A1 / A2 / A3`. Chunks store the precise band; retrieval may only be able to filter
to `A%` until the learner table gains sub-band precision.

---

## Validated corpus facts (measured — trust these)

**14 Band-A books, two layouts, ~300 pages, ~100–150 chunks expected.**

| Layout | Books | Signal | Evidence |
|---|---|---|---|
| **Band book** | `2_A1.pdf` (53pp), `3_A2.pdf` (49pp), `4_A3.pdf` (18pp) | `Name of Activity:` in body | 12 / 13 / 4 hits |
| **Project Read** | 11 books, 187pp | running header + concept carry-forward | **0** `Name of Activity:` hits |

- **Only 2 parsers are needed for the entire corpus.** Architecture validated.
- Two modules in the header top-left: `Barebone Sentence`, `Predicate Expanders`.
- Stage vocabulary is consistent: Presentation (62 pages), Introduction worksheet (24),
  Practice worksheet (18), Production, Review, Resources, Extended, Summary, plus a long
  tail of creative titles ("Let's recall!", "A Writing Game!", "Expand your sentences!").
- **6+1 Writing Traits boxes on 63% of pages**, consistent vocabulary: Conventions (67),
  Sentence structure (61), Ideas (53), Word choice (51), Presentation (18).
- Retrieval ablation on real chunks: **metadata-filtered 5/5 vs vector-only 2/5.**
  Vector-only drifts to summary/review pages that merely *mention* the concept.
- Chunk sizes after cleaning: presentation 296–1261 chars, worksheets 549–3020,
  resources 266–294. **No chunk is empty after aggregation.**
- Embedding the whole corpus costs ~$0.002. Cost is a non-issue.
- PyMuPDF `get_images()` returns pixel metadata only — **PDFs carry NO image captions.**

---

## Core architecture: metadata is primary, the vector is a safety net

Unusual, and important to internalise before building. A profile-derived query is
`"teach action predicate, Band A1, practice"`; chunk content is `"Mrs Banks ___, The cop ___"`.
**The content has almost no correlation with a learner profile** — the only overlapping
signal ("action predicate") is already in the metadata columns.

| Mechanism | Role | Strength |
|---|---|---|
| Metadata `WHERE` | Finds the correct chunks | **Primary.** Exact, measured 5/5. |
| Vector `ORDER BY` | Screens + weakly orders | **Secondary.** Safety net. |

The vector does exactly two jobs:

1. **Catches metadata errors.** Real case: an "Extended activity 1a" page inherits
   `concept=action_predicate` from its header, but its body is *Synonyms for "Said"* — a
   vocabulary exercise. Only the content reveals this, and the vector ranks it last.
   **This is the strongest justification for embedding full content.**
2. **Separates chunks sharing metadata.** Practice worksheet 1/2/3 are identical on every
   filter column; the vector is the only remaining signal.

It does **not** meaningfully rank two equally-valid chunks — the profile carries nothing that
would distinguish them. Variety across sessions is an *exposure-rotation* problem, not a
ranking problem.

**Why embed full content anyway?** (a) the safety net requires it; (b) the learner-profile
schema is still unsettled — if it gains therapist notes or learner interests, semantic
matching suddenly matters and the content must already be indexed. Costs $0.002; preserves
optionality. Concise summaries would foreclose it and force a re-ingest.

---

## v1 scope decisions

1. **New table `curriculum_chunks`.** Do NOT reuse `learning_activities` — that holds
   *generated* per-learner output (`profiled`, `status`, `grounded_on`), not source material.
   Mixing them would let retrieval return an AI-generated activity as a grounding exemplar.
2. **Do NOT reuse `instructional_strategies`** — that is the ELL-MLP *strategy* corpus used
   by UC5's second retrieval. Curriculum exemplars are a separate corpus. Both feed the
   prompt; they are not the same table.
3. **`learning_activities.grounded_on`** should be populated with `curriculum_chunks.id`
   values by the generation layer. Ingestion just makes those IDs exist.
4. **Curriculum join key = `concept`**; also tag `cognitive_constructs` (see conflict above).
5. **`writing_traits` (6+1) is a secondary optional tag**, never a required filter (63% coverage).
6. **Chunking key = `(module, concept, stage, sequence_no)`.** `sequence_no` is essential:
   Practice worksheet 1 / 2 / 3 are DIFFERENT worksheets and must be different chunks.
7. **Embed metadata prefix + FULL `content_md`.** Never trim or summarise.
8. **IMAGES DEFERRED to v1.5.** v1 ignores them entirely; log image-only pages.
9. **Do NOT drop presentation chunks.** They aggregate to 296–1261 chars containing the
   concept definition and worked examples — the only re-teaching material for mastery < 0.30.
10. **`resources` / "Barebones" cut-out pages → `doc_type='resource'`**, excluded from
    exemplar retrieval but not deleted.
11. Use **HNSW**, not ivfflat, for the new index. `instructional_strategies` uses
    `ivfflat lists=100`, which is wrong below ~1000 rows; do not copy that pattern.

---

## Non-negotiable rules

1. **Chunking is deterministic. NO LLM in the ingestion path.** Same PDF in → identical
   chunks out. Testable, diffable.
2. **No `RecursiveCharacterTextSplitter`, `SemanticChunker`, or any token/similarity splitter.**
   This corpus is *forms*, not prose. Semantic chunking fails both ways here: it MERGES stages
   (the definition sentence repeats verbatim across presentation/practice/production) and
   SPLITS worksheets from their word banks (an instruction line and a bare verb list have
   near-zero similarity).
3. **A chunk = one complete teaching unit**, not N tokens.
4. **Answer keys are a FIELD of their worksheet chunk, never a separate chunk.**
5. **Read headers/footers by y-coordinate**, never by grepping page text.
6. **PyMuPDF (`fitz`) is the "eyes"** (text + coordinates); your code is the "brain".
7. **Idempotent + versioned.** Re-running wipes and rebuilds a source's chunks.
8. **Respect the existing layering.** Supabase access goes through a Repository; the
   embedding call goes through a Gateway. No direct `supabase` client calls in parser code.
9. **Never run git commands, and build ONE numbered step per turn, then stop.**
   See "Git workflow" before the build order.

---

## Where the code goes (fits the existing structure)

```
backend/
├── app/
│   ├── entities/
│   │   └── curriculum_chunk.py        # NEW — CurriculumChunk, Unit, Page (pydantic)
│   │
│   ├── repositories/
│   │   └── curriculum_repository.py   # NEW — Supabase access for curriculum_chunks
│   │                                  #   upsert_chunks(), delete_by_source(),
│   │                                  #   match_curriculum()  ← used later by retrieval
│   │
│   ├── gateways/
│   │   └── embedding_gateway.py       # NEW (or extend LLMApiClient) — embed(texts)
│   │                                  #   provider-swappable: OpenAI | Ollama
│   │
│   ├── ingestion/                     # NEW package — offline batch, not request-scoped
│   │   ├── __init__.py
│   │   ├── constants.py               # CONCEPTS, CONCEPT_TO_MODULE, PREREQUISITES,
│   │   │                              #   STAGE_MAP, TRAITS, CONCEPT_TO_CONSTRUCTS
│   │   ├── pdf_reader.py              # fitz → list[Page]; positional extraction
│   │   ├── normalise.py               # unicode, stage enum, seq_no, traits, carry-forward
│   │   ├── segment.py                 # universal state machine segment(pages, key_of)
│   │   ├── chunk_builder.py           # Unit → CurriculumChunk; builds embed_text
│   │   ├── pipeline.py                # orchestration: read→detect→parse→build→embed→store
│   │   └── parsers/
│   │       ├── __init__.py
│   │       ├── base.py                # Protocol: matches(doc)->bool; parse(pages)->list[Unit]
│   │       ├── project_read.py        # running header + concept carry-forward (11 books)
│   │       ├── band_book.py           # "Name of Activity:" delimiter (A1/A2/A3)
│   │       └── registry.py            # detect_parser(doc)
│   │
│   └── services/
│       └── curriculum_service.py      # NEW (optional) — if the API ever exposes
│                                      #   ingestion status / chunk browsing
│
├── scripts/
│   └── ingest_curriculum.py           # NEW — CLI entry point (offline batch runner)
│
└── data/
    └── curriculum/                    # NEW — the 14 source PDFs (gitignored)

infra/
└── schema.sql                         # EXTEND — append curriculum_chunks + indexes
                                       #   + match_curriculum() function
```

**Layering notes:**
- `ingestion/` is a **batch package**, not a request-scoped Service. It is invoked by a
  script, not a router. It *uses* the Repository and Gateway rather than bypassing them.
- Follow the existing `@lru_cache` singleton pattern for the repository/gateway accessors,
  consistent with the rest of the backend.
- No new router is required for v1. Ingestion is run from the command line.

---

## Schema — APPEND to `infra/schema.sql`

```sql
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
  concept text not null,                   -- 'action_predicate' | 'all' | ...  ← curriculum join key
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
  embedding vector(1536),
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
  query_embedding vector(1536),
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
```

**Note:** `<=>` (cosine) must match `vector_cosine_ops`, or the index is ignored.

---

## THE COLUMNS (complete)

### Filter columns — used in `WHERE`, indexed

| Column | Type | Example | Why |
|---|---|---|---|
| `band` | text NOT NULL | `A1` | **Hardest constraint.** An A1 learner must never get A3 material. |
| `module` | text | `Barebone Sentence` | 2 values; derivable from concept; free narrowing + reporting |
| `concept` | text NOT NULL | `action_predicate` | **Curriculum join key** |
| `stage` | text | `practice` | Mastery score → stage. Turns a number into a retrieval decision. |
| `sequence_no` | int | `2` | Practice worksheet 1 vs 2 vs 3. **Required.** |
| `doc_type` | text NOT NULL | `lesson_plan` | `lesson_plan` \| `resource`; excludes cut-out templates |
| `writing_traits` | text[] | `{conventions,sentence structure}` | 6+1, lowercased. **Optional filter only.** |
| `cognitive_constructs` | text[] | `{decoding}` | Bridge to `learner_profiles`' seven floats |

### Content columns — fed to the LLM

| Column | Type | Example |
|---|---|---|
| `activity_title` | text | `Introducing Action Predicate` — body heading, best tie-breaker |
| `content_md` | text NOT NULL | full worksheet / teaching text |
| `answer_key` | text | `swims, buzz, swings, hops, barks, quacks` |
| `objective` | text | may be null — extraction unverified |

### Guardrail

| Column | Type | Example |
|---|---|---|
| `prerequisites` | text[] | `{action_predicate}` — validator checks scope |

### Provenance

`source_file`, `page_start`, `page_end` — required for therapist verification and for
populating `learning_activities.grounded_on`.

### Vector + bookkeeping

`embedding`, `embedding_model`, `ingest_version`, `raw_header`, `embed_text` (optional debug).

### Reserved for v2

`skills text[]` — create, **leave empty**. Pending client taxonomy.

---

## WHAT GETS EMBEDDED

**Exactly one string per chunk**, built in `chunk_builder.py`:

```python
def build_embed_text(c: CurriculumChunk) -> str:
    return (
        f"Band {c.band} | {c.module} | {c.concept} | {c.stage} | {c.activity_title}\n"
        f"{c.content_md}"                    # ← FULL content. Never trim or summarise.
    )
```

Concrete example (chunk from pages 316–317):

```
Band A1 | Barebone Sentence | action_predicate | introduction | Introducing Action Predicate
An action predicate tells the action of the subject. The symbol has 4 mountain peaks.
Example: Lion roars. Choose the action predicate relevant to the pictures below.
swings, barks, swims, quacks, hops, buzz
```

- The `|` prefix is **plain text**. The embedder does not parse it and does not create
  columns from it — columns are assigned separately in Python.
- **The full `content_md` follows.** It is the only thing that can discriminate between
  chunks sharing identical metadata.
- **NOT embedded:** the JSON object, images, file paths, page numbers, `answer_key`.
- Truncate at the model limit (~8191 tokens) rather than erroring.
- Result goes in `embedding`; `embed_text` itself is an optional debug column.

**Why the same content sits in two columns:** `embedding` exists to be *found* (fuzzy,
cosine); `content_md` exists to be *fed to the LLM* (exact text). One query returns both.

---

## Chunking strategy

Segment at **`(module, concept, stage, sequence_no)`** — the smallest independently-useful,
complete unit.

### Two boundary signals — `registry.detect_parser()` picks one (step zero)

- **Body delimiter** (`band_book.py`): new chunk on every `Name of Activity:` match.
- **Running header** (`project_read.py`): no body delimiter; each page header carries the
  stage; concept is **carried forward** (remember the last explicit concept heading, apply
  until it changes). New chunk when the key tuple changes.

Using the wrong signal yields zero chunks or one giant chunk. Detect first.

### Universal segmenter (`segment.py`) — write ONCE, both parsers call it

```python
def segment(pages, key_of):
    chunks, cur, key = [], [], None
    for p in pages:
        k = key_of(p)
        if k != key and cur:
            chunks.append(cur); cur = []
        cur.append(p); key = k
    if cur: chunks.append(cur)
    return chunks
```

```python
# project_read.py
segment(pages, key_of=lambda p: (p.concept, p.stage, p.sequence_no))
# band_book.py
segment(pages, key_of=lambda p: p.current_activity_name)
```

---

## Normalisation (`normalise.py`) — REQUIRED or chunks break

**1. Unicode first.** The corpus contains BOTH `Let's recall!` (U+0027) and `Let's recall!`
(U+2019) — visually identical, unequal as strings.
```python
text = text.replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
```

**2. Strip parenthetical suffixes** before comparing stages:
```
"Practice worksheet 1 (Band A1-A3)"        → stage=practice, seq=1
"Practice worksheet 1 (Suggested Answers)" → stage=practice, seq=1   ← SAME → same chunk
"Practice worksheet 2"                     → stage=practice, seq=2   ← DIFFERENT → new chunk
```
This is what keeps an answer key attached to its worksheet.

**3. Extract `sequence_no`** from the trailing digit (default 1).

**4. Map stage to a canonical enum, with a FALLBACK:** if no pattern matches, use the cleaned
header text as the stage. **Never return `None`** — that silently merges unrelated activities.
Known: presentation, introduction, practice, production, production_activity, resources,
extended, wordlist, review, summary, game.

**5. Concept carry-forward.** Compound/Series presentation pages switch the concept state.
Review / Summary / Word-list / generic Extended → `concept="all"`, do NOT inherit. Do NOT
switch concept on a mere body mention of "compound"/"series".

**6. Writing traits.** Parse the 6+1 box; **lowercase** (corpus has both `Word choice` and
`Word Choice`); store as `text[]`; empty array if absent.

**7. `activity_title`.** Extract the bold centred body heading ("Introducing Action
Predicate", "Synonyms: 'Said'"). Distinct from the header; strongest discriminator on ties.

**8. `cognitive_constructs`.** Map via `CONCEPT_TO_CONSTRUCTS` in `constants.py`. Leave empty
where no honest mapping exists (most Project Read grammar concepts). **Do not invent
mappings** — an empty array is more honest than a wrong one.

---

## PDF reading (`pdf_reader.py`) — positional extraction

| Signal | Where | Field |
|---|---|---|
| printed page no | footer band `y/H > 0.90`, digits | `printed_no` |
| header / stage | header band `0.06 < y/H < 0.14`, skipping `6+1`/trait words/module | `raw_header` |
| body title | first bold centred line in body | `activity_title` |
| full text | whole page | `content_md` |
| is-answer-key | matches `answer key\|suggested answers` | routes text to `answer_key` |
| 6+1 box | text near `6+1 Writing Traits` | `writing_traits` |

---

## Image-only pages (the ONLY image behaviour in v1)

Detect "has images AND < ~30 chars of real text after removing boilerplate". **Skip building
a chunk for that page, but LOG it** to `data/curriculum/_orphans.log`. Never silently drop.
Do not extract, store, or embed images in v1.

**Thin-chunk rule (chunk level, NOT page level):** build every chunk, then drop only if still
empty *after aggregation* (< 100 chars cleaned). Measured: **no chunk in the corpus hits this
threshold.** It is a safety net, not a routine filter.

---

## CLI (`scripts/ingest_curriculum.py`)

```
python -m scripts.ingest_curriculum run    --file data/curriculum/14_Action_predicate.pdf [--dry-run] [--no-embed]
python -m scripts.ingest_curriculum run    --all
python -m scripts.ingest_curriculum verify --source 14_Action_predicate.pdf
```

`--dry-run` prints the chunk table (module | concept | stage | seq | pages | has_key | title |
chars) WITHOUT calling the embedding gateway or the database. **Always dry-run a new book first.**

`CurriculumRepository.delete_by_source(source_file)` MUST run before insert → idempotent.

---

## ⛔ Git workflow — MANDATORY

**Do NOT run `git commit`, `git add`, `git push`, or any git command. Ever.**
The developer commits manually so history stays clean and sequential.

**STOP after each numbered step in the build order below.** Do not chain steps.
After completing a step:

1. State plainly which step is done and which files were created or changed.
2. Report the verification result for that step (e.g. "yields 16 chunks — matches spec").
3. **STOP and wait.** Do not begin the next step until the developer explicitly says to continue.

This produces one reviewable commit per feature. Building several steps in one pass forces a
large, unreviewable commit and makes it impossible to bisect a regression later.

If a step's verification fails, **stop and report it** — do not work around it or proceed to
the next step hoping it resolves.

---

## Build order

**One step at a time. Stop after each. Do not commit.**

1. `entities/curriculum_chunk.py` — `Page`, `Unit`, `CurriculumChunk` pydantic models
2. `ingestion/constants.py` — concepts, module map, prerequisites, stage map, traits, constructs
3. `ingestion/pdf_reader.py` — positional `Page` extraction; test on both layouts
4. `ingestion/normalise.py` — unicode → stage + seq_no → traits → carry-forward → title
5. `ingestion/segment.py` — state machine; unit-test with synthetic pages
6. `ingestion/parsers/project_read.py` — **must yield 16 chunks** for `14_Action_predicate.pdf`
7. `ingestion/parsers/band_book.py` — split `2_A1.pdf` on its 12 delimiters
8. `ingestion/parsers/registry.py` — `detect_parser(doc)`
9. `ingestion/chunk_builder.py` — Unit → CurriculumChunk; build `embed_text`; `skills` stays `[]`
10. `scripts/ingest_curriculum.py run --all --dry-run` — **eyeball every chunk table**
11. Append the schema block to `infra/schema.sql`; run it in Supabase
12. `repositories/curriculum_repository.py` + `gateways/embedding_gateway.py`
13. `ingestion/pipeline.py` wiring; `run --all` end to end

---

## Definition of done (v1)

- [ ] `--dry-run` gives stable, correct boundaries on all 14 books
- [ ] `14_Action_predicate.pdf` → **16 chunks**; `2_A1.pdf` splits on its 12 delimiters
- [ ] Practice worksheet 1/2/3 → **3 distinct chunks** (`sequence_no` works)
- [ ] Zero answer-key-only chunks
- [ ] No chunk has `stage = None` (fallback works)
- [ ] Curly-vs-straight apostrophes do not create duplicate stages
- [ ] `writing_traits` populated and lowercased on ~63% of chunks
- [ ] Presentation chunks retained (296–1261 chars each)
- [ ] `resources` chunks tagged `doc_type='resource'`, not deleted
- [ ] `embed_text` = prefix + FULL `content_md`; `embedding_model` recorded per row
- [ ] `skills == []` on every row
- [ ] Image-only pages skipped and logged
- [ ] Re-running is idempotent; no duplicates
- [ ] `curriculum_chunks` is separate from `learning_activities` and `instructional_strategies`
- [ ] Supabase access only via `CurriculumRepository`; embeddings only via the gateway

---

## Do NOT

❌ token/semantic splitters ❌ trim or summarise `content_md` before embedding
❌ write curriculum into `learning_activities` or `instructional_strategies`
❌ image extraction/embedding (v1) ❌ answer-key-only chunks ❌ LLM in the chunking path
❌ populate `skills` (v1) ❌ drop presentation chunks ❌ delete `resources` chunks
❌ grep page text for headers/concept ❌ compare stage strings before normalising
❌ non-idempotent inserts ❌ direct supabase calls from parser code
❌ copy the `ivfflat lists=100` pattern (wrong below ~1000 rows — use HNSW)
❌ **run any git command** (`add`, `commit`, `push`, `checkout`) — the developer commits
❌ **build more than one numbered step per turn** — stop and wait after each

---

## Notes for the retrieval layer (context — not built here)

- **top-k = 3, not 1.** Metadata ties are common (62 presentation pages share metadata).
  Feed 2–3 exemplars so the LLM generalises the *pattern* rather than copying one instance.
- **Two retrievals, fused** (UC3/UC5): `match_curriculum()` for exemplars **and**
  `match_strategies()` for ELL-MLP pedagogy. Both go into one prompt.
- **Populate `learning_activities.grounded_on`** with the `curriculum_chunks.id` values used.
- **Reranker deferred.** Not merely because the pool is small: a cross-encoder scores
  query↔document relevance, and chunks sharing metadata are *equally* relevant to a
  profile-derived query. "Which is better" is not a function of the query.
- **Exposure tracking needed.** Retrieval is deterministic, so the same profile returns the
  same chunks every session and later worksheets are never seen. Add a `learner_exposure`
  table and exclude already-used chunks. Selection among equally-valid chunks is a
  *pedagogical* decision, not a search problem.
- **Empty-filter handling.** If a filter returns zero rows, widen deliberately and visibly
  (drop `sequence_no` → drop `stage` → flag `NO_COVERAGE` to the therapist). Never silently
  drop a filter and return off-band material.

---

## Open questions (raise with team / client — do NOT block the build)

1. **`learner_profiles` has no curriculum join key.** Seven cognitive constructs cannot
   address sentence-construction curriculum. Does the profile need a per-concept competency
   layer, or should retrieval go through `cognitive_constructs`?
2. **`learners.band_level` is `Band A/B/C`; curriculum is `A1/A2/A3`.** Sub-band precision
   needed on the learner side, or accept coarser filtering.
3. Do the band books (A1/A2/A3) carry 6+1 traits, or a different vocabulary? Determines
   whether `writing_traits` is corpus-wide.
4. Is `objective` reliably extractable? Assumed, never tested. May stay null.

## Future (v2 — noted, not built)

- `skills` as a finer join key, pending client taxonomy.
- v1.5: image extraction as assets + `{{img: tag}}` slots for illustrated worksheets.
- Contextual retrieval (situating blurb prepended before embedding).