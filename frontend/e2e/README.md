# Frontend e2e tests (Playwright)

**Status: adopted and wired into CI** (`frontend-e2e` job). `@playwright/test` is a
devDependency, the config is `frontend/playwright.config.js`, and `login.spec.js` covers UC6.

## What this is (and how it relates to the Selenium `system` tests)

Both this folder and `backend/tests/system/` are **browser end-to-end** — real UI, real backend,
real Supabase. The difference is the toolchain:

| | Playwright (`frontend/e2e/`) | Selenium (`backend/tests/system/`) |
|---|---|---|
| Language | JavaScript (lives with the frontend) | Python (lives with the backend) |
| Status | wired into CI (`frontend-e2e` job) | wired into CI (`system` job) |
| Covers | UC6 log in / sign out | UC6, UC8, UC9, UC4, UC7 — with plan IDs |
| Nice-to-haves | auto-waiting, trace viewer, codegen | — |

These are the **same tier of the pyramid**, and both are currently maintained. That is a
deliberate, temporary state, not an accident: the Selenium suite already owns the system-level
plan IDs (ST-6.x, ST-8.x, ST-9.x), so this tier sticks to the login boundary rather than
duplicating them. **Long-term, pick one** — a flow covered here and there is a flow whose failures
have to be diagnosed twice.

## Running locally

The app must already be running; the config does not start it (`webServer` manages one process,
and this tier needs a backend alongside the frontend).

```bash
# terminal 1 — backend
cd backend && uvicorn app.main:app --port 8000
# terminal 2 — frontend (built + served)
cd frontend && VITE_API_URL=http://127.0.0.1:8000 \
  VITE_SUPABASE_URL=... VITE_SUPABASE_ANON_KEY=... \
  npm run build && npm run preview -- --port 4173
# terminal 3 — the tests
cd frontend && TEST_THERAPIST_EMAIL=... TEST_THERAPIST_PASSWORD=... npm run test:e2e
```

Browser binaries install once with `npx playwright install chromium`.

The specs **self-skip** without `TEST_THERAPIST_EMAIL` / `TEST_THERAPIST_PASSWORD`, matching the
backend e2e/system tiers — an unconfigured checkout stays green. Read the skip count before
treating a pass as evidence. Credentials must belong to the Supabase **test** project, never
production.

Useful while writing specs: `npx playwright test --headed`, `--debug`, `--ui`, and
`npx playwright codegen http://127.0.0.1:4173`.

## CI

The `frontend-e2e` job in `.github/workflows/tests.yml` starts the backend, builds and serves the
frontend, installs chromium, and runs `npm run test:e2e`, uploading the HTML report on failure.

It shares the `supabase-test-project` **concurrency group** with `backend-e2e` and `system`, and
runs last in the chain `backend-e2e -> system -> frontend-e2e`. All three
mutate one Supabase project, and letting two of them run at once has already broken a CI run —
see the note on the `backend-e2e` job.
