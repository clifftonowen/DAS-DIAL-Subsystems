# Frontend e2e tests (Playwright)

**Status: scaffolded, not yet installed.** `login.spec.js` is a skipped stub and
`playwright.config.template.js` is a template. Nothing here runs until you adopt Playwright.

## What this is (and how it relates to the Selenium `system` tests)

Both this folder and `backend/tests/system/` are **browser end-to-end** — real UI, real backend,
real Supabase. The difference is the toolchain:

| | Playwright (`frontend/e2e/`) | Selenium (`backend/tests/system/`) |
|---|---|---|
| Language | JavaScript (lives with the frontend) | Python (lives with the backend) |
| Status | placeholder | wired into CI (`system` job) |
| Nice-to-haves | auto-waiting, trace viewer, codegen | — |

These are the **same tier of the pyramid**. Long-term, pick **one** browser-e2e stack — don't
maintain both. This scaffold just gives frontend devs a JS-native option to grow into; if the team
prefers Python, delete this folder and keep the Selenium `system` tests.

## Enabling Playwright

```bash
cd frontend
npm i -D @playwright/test
npx playwright install          # downloads browser binaries
mv e2e/playwright.config.template.js e2e/playwright.config.js
```

Add a script to `package.json`:

```json
"scripts": { "test:e2e": "playwright test" }
```

## Running

Point it at a running app (or uncomment `webServer` in the config to have Playwright start it):

```bash
# terminal 1 — backend
cd backend && uvicorn app.main:app --port 8000
# terminal 2 — frontend (built + served)
cd frontend && VITE_API_URL=http://127.0.0.1:8000 \
  VITE_SUPABASE_URL=... VITE_SUPABASE_ANON_KEY=... \
  npm run build && npm run preview -- --port 4173
# terminal 3 — the tests (needs TEST_THERAPIST_EMAIL / _PASSWORD)
cd frontend && npx playwright test
```

Then remove `.skip` from the `test.describe.skip(...)` block in `login.spec.js`.

## Future CI

When adopted, add a `frontend-e2e` job to `.github/workflows/tests.yml` mirroring the `system`
job (build frontend, start backend, `npx playwright install --with-deps`, `npm run test:e2e`,
upload the Playwright report on failure). A placeholder comment marks the slot in that file.
