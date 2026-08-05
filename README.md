# DAS D.I.A.L — Subsystems 2 & 3

AI-based individualised learning platform.

- **Subsystem 2 — Cognitive Profiling**: assessment records → `ProfilingAlgorithm` → `LearnerProfile`
- **Subsystem 3 — Adaptive Activity Generator**: profile → RAG retrieval → LangGraph generate/validate loop → `LearningActivity`

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

```bash
pip install -r backend/requirements-analysis.txt   # pandas + openpyxl, ingest only
cd backend
python -m scripts.ingest_dial_data --dry-run       # audit + fitted models, writes nothing
python -m scripts.ingest_dial_data                 # needs the Supabase .env
```

`--dry-run` prints per-feature coverage, re-checks the data assumptions the feature
selection rests on, and shows each band model's silhouette sweep, chosen k and centroids.
Run it first — it needs no secrets, and the audit is how you notice a new workbook has
broken an assumption.

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

## Testing

We run a four-level test pyramid. The bottom three run anywhere with **no secrets**;
the top two run against a dedicated Supabase **test** project (see below).

| Level | What it proves | Stack | Where |
|-------|----------------|-------|-------|
| **Unit** | one function/component in isolation (all collaborators mocked) | `pytest` + `TestClient`; **Jest** + React Testing Library | `backend/tests/unit`, `frontend/src/**/__tests__` |
| **Integration** | layers wired bottom-up (repo → service → router); only the DB driver faked | `pytest` | `backend/tests/integration` |
| **E2E** | one full-stack flow per use case, real DB + real JWT | `pytest` + real Supabase | `backend/tests/e2e` |
| **System** | real UI in a real browser per use case | `pytest` + **Selenium** (headless Chrome) | `backend/tests/system` |

Two more frontend tiers are **scaffolded** (stubs — fill in as features grow): frontend
**integration** (Jest + MSW) in `frontend/src/views/__integration__/`, and frontend **e2e**
(Playwright) in `frontend/e2e/`. See each folder's README.

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
`.github/workflows/tests.yml` runs all five jobs on every push/PR. Unit, integration and
frontend jobs run with no secrets; **e2e** and **system** read the repo Secrets listed at the
top of that file (they self-skip and stay green until you configure them).

**How to add a new test** — backend levels (unit/integration/e2e/system) are in
[`backend/tests/README.md`](backend/tests/README.md); frontend component (UI) tests are in
[`frontend/test/README.md`](frontend/test/README.md).

## Team workflow [OPTIONAL]
See [`docs/collaboration.md`](docs/collaboration.md) — claim an Issue + open a
draft PR before you start, and install GitLive so you can see who's editing which file in real time
(avoids overlapping work and frontend merge conflicts).

## Status of each piece
Search the code for `TODO:` — each marks a spot a team member owns (real JWT verify, ProfilingAlgorithm scoring, LangGraph wiring, embeddings, PDF render, OCR parsing). 
