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

## Status of each piece
Search the code for `TODO:` — each marks a spot a team member owns (real JWT verify, ProfilingAlgorithm scoring, LangGraph wiring, embeddings, PDF render, OCR parsing). 
