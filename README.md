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
infra/           # schema.sql (Supabase), docker-compose
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
