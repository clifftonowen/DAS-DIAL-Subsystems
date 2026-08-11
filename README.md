# DAS D.I.A.L — Subsystems 2 & 3

AI-based individualised learning platform.

- **Subsystem 2 — Cognitive Profiling**: DIAL assessment marks → `ProfilingAlgorithm.cluster()` → cohort clusters + per-learner progress
- **Subsystem 3 — Adaptive Activity Generator**: a learner's weakest marks → RAG retrieval → generate/validate loop → `LearningActivity`

## Architecture 

```
View (React + Tailwind)
  → Controller (FastAPI routers)
    → Service (application logic)
      → Repository (Supabase + pgvector)   → Entities
      → Agent/Algorithm (LangChain + LangGraph)
      → Gateway (Supabase Auth, Email, LLM)
```

Folder map:

```
backend/app/
  routers/       # Controller layer — HTTP endpoints
  services/      # application logic
  repositories/  # Supabase data access (+ pgvector search)
  agents/        # ProfilingAlgorithm, ActivityGraph, Generative/Validative agents
  gateways/      # AuthGateway, EmailGateway, LLMApiClient
  entities/      # domain models
  core/          # config, supabase client, auth dependency
frontend/src/    # AuthView, Dashboard, UploadView + api/supabase clients
infra/           # schema.sql (Supabase), migrations/, docker-compose
notebooks/       # cohort clustering analysis (Subsystem 2) — see Setup step 4
```

## Setup

### 1. Supabase
1. Create a project at supabase.com.
2. SQL editor → paste and run `infra/schema.sql` (enables pgvector + all tables + `match_strategies`).
3. Copy the Project URL, anon key, service-role key, and JWT secret.

### 2. Backend
```bash
cd backend
cp .env.example .env      # fill in Supabase + OpenAI keys
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open http://localhost:8000/docs — all endpoints are live. `GET /health` should return `{"status":"ok"}`.

### 3. Frontend
```bash
cd frontend
cp .env.example .env      # fill in Supabase URL + anon key + API url
npm install
npm run dev               # http://localhost:5173
```

### 4. Cohort clustering (Subsystem 2, UC2) — optional
Populates the dashboard's 3D cohort scatter from `DIAL_Anonymised_Data.xlsx` (gitignored;
place it at the repo root). Without this step the scatter shows its empty state and
everything else works normally.

The cohort loads into `learners`, the **same table as the therapist's caseload** —
`on_caseload` tells the two apart. On an existing project, run the migrations in date order
first. Two of them **drop a table** and leave the drop commented out for you to run once the
verification query above it checks out — `2026-08-07_merge_learner_scores.sql` folds in the old
`learner_scores`, and `2026-08-08_dial_dimensions.sql` removes `learner_profiles`. Back up first.

```bash
pip install -r backend/requirements-analysis.txt   # pandas + openpyxl, ingest only
cd backend
python -m scripts.ingest_dial_data --dry-run       # audit + fitted models, writes nothing
python -m scripts.ingest_dial_data                 # needs the Supabase .env
```

`--dry-run` prints per-feature coverage and percentile coverage, re-checks the data
assumptions the feature selection rests on, and shows each band model's silhouette sweep,
chosen k and centroids. Run it first — it needs no secrets, and the audit is how you notice
a new workbook has broken an assumption.

**The ingest never deletes and never renames.** It upserts on `student_id` and sends only
workbook-derived columns, so a learner who is both on the caseload and in the workbook has
their marks refreshed while keeping their pseudonym, tier and caseload flag. There is no
`--replace`: `learner_sittings` and `assessment_records` cascade from this table, and a stale
row is a far cheaper mistake than a deleted score history.

**How it works.** `ProfilingAlgorithm.cluster()` standardises the literacy scores, sweeps
k = 2…10, and keeps the k with the best silhouette. The ingest fits it **twice**:

| Scope | Models | Column | Result |
|-------|--------|--------|--------|
| cohort | one, over all 5,783 | `cluster_cohort` | k=4, silhouette 0.365 |
| band | one per band group A/B/C, each its own k | `cluster_band` | k=5/4/2, silhouette 0.43/0.42/0.34 |

The band models score better because the assessment papers differ by band — phonics tops out
at 25 in A1, 30 in A2 and 46 in A3 — so a single cohort-wide fit partly recovers which paper a
student sat rather than how they are doing (its high-phonics cluster is 56.8% band A3). Both
are stored so the dashboard can toggle between them and show the comparison; the scatter opens
on the cohort model and its band filter works in either scope. The API serves the labels as a
plain SELECT — no model is fitted on the request path.

The evidence behind every one of those choices — including why `FluencyMark` and the three
separate writing-genre columns are excluded — is worked through in
[`notebooks/subsystem2_clustering.ipynb`](notebooks/subsystem2_clustering.ipynb), which
imports the same modules the ingest script uses so the two cannot drift.

### The learner profile is the four marks

There is no derived profile any more. `learner_profiles` and its seven cognitive dimensions
(phonological processing, decoding, spelling, comprehension, working memory, executive
functioning, visualisation) were mock scaffolding — produced by keyword-matching subtest names,
over seeded data. The system standardises on what DAS actually measures. See
`infra/migrations/2026-08-08_dial_dimensions.sql`.

`GET /learners/{id}/overview` serves both views of those four marks in one call:

- **DIAL Assessment** — a radar of the learner's *current* marks, each as a **percentile within
  their band group**. Not the raw mark and not percent-of-max: a radar shares one radius across
  every axis, and the four marks are on neither the same rubric (phonics /46, word reading /10)
  nor the same rubric across bands. A paper the learner never sat — writing, for every band A
  learner — has its axis **omitted** rather than drawn at zero, and the legend still carries the
  mark that was awarded.
- **Progress & Activity** — a line chart of one mark across every semester on record, with a
  metric picker and a raw ↔ percentile toggle. Percentiles here rank a sitting against everyone
  who sat *the same paper in the same semester*, so the line moves as the learner does rather
  than as the cohort around them changes.

The history lives in `learner_sittings`, one row per learner per semester (~22,892 from the
workbook). `learners` keeps the newest sitting as the current marks — a deliberate duplication,
because the cohort scatter reads 5,783 rows in one request and k-means needs a stable snapshot.

**"Generate Profile" promotes**, it does not compute: it copies the learner's most recent
sitting onto their row. With no sittings at all it returns **409**, and the page turns that into
an inline prompt to upload an assessment. Both writers — the workbook ingest and UC1's upload —
land in `learner_sittings`, which is where they meet.

### One table for every learner

`learners` holds both populations, distinguished by `on_caseload`:

| | caseload | research cohort |
|---|---|---|
| how many | the therapist's own, ~10 seeded | ~5,773 anonymised |
| identity | `pseudonym`, `tier` | `student_id` only |
| DIAL marks + history | if they are also in the workbook | always |
| profile / activities / share | yes | yes — a profile is just their marks |

Every learner has a uuid, a detail page and the same actions. `on_caseload` drives a badge and
the Learners tab's default filter; it does not restrict anything, because a profile is now the
four marks the research cohort also has.

Two consequences worth knowing before you touch this table. `GET /learners` is **paged and
searched server-side** and defaults to the caseload — PostgREST caps a select at 1,000 rows and
truncates *without erroring*, so an unpaged read serves a sixth of the table while looking
healthy. And the dashboard's **Total Learners counts everything** (so it reads ~5,783), while
Missing Profiles and Pending Review beside it are caseload concepts.

## Testing

We run a four-level test pyramid. The bottom three run anywhere with **no secrets**;
the top two run against a dedicated Supabase **test** project (see below).

| Level | What it proves | Stack | Where |
|-------|----------------|-------|-------|
| **Unit** | one function/component in isolation (all collaborators mocked) | `pytest` + `TestClient`; **Jest** + React Testing Library | `backend/tests/unit`, `frontend/src/**/__tests__` |
| **Integration** | layers wired bottom-up (repo → service → router); only the DB driver faked | `pytest` | `backend/tests/integration` |
| **E2E** | one full-stack flow per use case, real DB + real JWT | `pytest` + real Supabase | `backend/tests/e2e` |
| **System** | real UI in a real browser per use case | `pytest` + **Selenium** (headless Chrome) | `backend/tests/system` |

Two more frontend tiers are **implemented and in CI**: frontend **integration** (Jest + MSW,
`frontend/src/views/__integration__/`, the `frontend-integration` job) and frontend **e2e**
(Playwright, `frontend/e2e/`, the `frontend-e2e` job). See each folder's README.

The frontend integration tier is where a **client/server contract** breaks get caught: the view
and `lib/api.js` are real and only the network is replaced, so it sees request shaping and
response handling that a unit test — which mocks `lib/api.js` — cannot. It has already caught two
such bugs; both are described in that folder's README.

### Install
```bash
cd backend  && pip install -r requirements.txt -r requirements-dev.txt
cd frontend && npm install
```

### Run locally
```bash
# Backend — from backend/
pytest -m unit            # fast, no DB
pytest -m integration     # fast, DB faked in-memory
pytest -m "unit or integration"   # everything hermetic

# Frontend — from frontend/
npm test                  # Jest (watch: npm run test:watch)
```

E2E and system need env from your Supabase **test** project (never production):
```bash
export SUPABASE_URL=...  SUPABASE_KEY=...  SUPABASE_JWT_SECRET=...
export TEST_THERAPIST_EMAIL=...  TEST_THERAPIST_PASSWORD=...   # a seeded user
pytest -m e2e             # from backend/ — auto-skips if the vars are missing

# System also needs the app running + Chrome:
#   backend/  : uvicorn app.main:app --port 8000
#   frontend/ : VITE_API_URL=http://127.0.0.1:8000 npm run build && npm run preview -- --port 4173
pytest -m system          # from backend/
```

### CI
`.github/workflows/tests.yml` runs all seven jobs on **pull requests and pushes to `main`**. The
four hermetic jobs (`backend-unit`, `backend-integration`, `frontend-unit`,
`frontend-integration`) need no secrets; **`backend-e2e`**, **`system`** and **`frontend-e2e`** read the
repo Secrets listed at the top of that file, and self-skip — staying green — until you configure
them. Read the skip list before quoting a green run as evidence.

Two things about that trigger are deliberate, and both exist because CI broke without them:

- **`push` is scoped to `main`.** A bare `push:` ran a second, identical workflow for every push
  to a branch that already had a PR open.
- **The three secret-backed jobs share a `concurrency` group.** They mutate one Supabase test
  project and one `TEST_LEARNER_ID`, so two overlapping runs interleave their fixtures — which is
  exactly how a UC4 system test once failed while the same commit passed on the run beside it.

**How to add a new test** — backend levels (unit/integration/e2e/system) are in
[`backend/tests/README.md`](backend/tests/README.md); frontend component (UI) tests are in
[`frontend/test/README.md`](frontend/test/README.md).

## Team workflow [OPTIONAL]
See [`docs/collaboration.md`](docs/collaboration.md) — claim an Issue + open a
draft PR before you start, and install GitLive so you can see who's editing which file in real time
(avoids overlapping work and frontend merge conflicts).

## Status of each piece
Search the code for `TODO:` — each marks a spot a team member owns (real JWT verify, ProfilingAlgorithm scoring, LangGraph wiring, embeddings, PDF render, OCR parsing). 
