# Frontend e2e tests (Playwright)

**Status: adopted and wired into CI** (`frontend-e2e` job). `@playwright/test` is a
devDependency, and the config is `frontend/playwright.config.js`.

## Coverage

One spec per use case, so the PM3 plan's frontend-E2E column has a visible slot for each:

| Spec | Use case | State |
|---|---|---|
| `login.spec.js` | UC6 Log In | live |
| `upload-assessment.spec.js` | UC1 Upload Assessment Data | live — stops at the preview, see below |
| `generate-profile.spec.js` | UC2 Generate Learner Profile | live |
| `generate-activity.spec.js` | UC3 (+ UC5 implicitly) | live — happy path gated on a learner id |
| `review-activity.spec.js` | UC4 Review Learning Activity | live |
| `retrieve-strategy.spec.js` | UC5 Retrieve Instructional Strategy | **permanently skipped** — no UI of its own |
| `share-activity.spec.js` | UC7 Share Learning Activity | live |
| `sign-up.spec.js` | UC8 Sign Up | live — refusal branch only, see below |
| `view-learners.spec.js` | UC9 View Learner List | live |

Three specs deliberately stop short of what the Selenium suite does, and the reason is the same
each time — **this tier has no database teardown**, so it must not leave rows behind:

- **UC1** never clicks "Confirm & save". The form only offers lookahead semesters, so a saved
  sitting is permanently that learner's newest — and UC2 promotes the newest sitting, so an
  unreclaimed row would silently change what UC2's tests read in *both* suites. Selenium can
  confirm because its `uploaded_sitting` fixture deletes what it created.
- **UC8** drives the duplicate-refusal branch, not account creation. Creating an account per CI
  run would orphan an auth user each time and draw on the project's signup quota, which is what
  makes the Selenium suite skip.
- **UC5** has no standalone UI. Its trigger is "UC3 reaches the retrieval step", so it is
  exercised inside `generate-activity.spec.js`.

## How this relates to the Selenium `system` tests

Both this folder and `backend/tests/system/` are **browser end-to-end** — real UI, real backend,
real Supabase. The difference is the toolchain:

| | Playwright (`frontend/e2e/`) | Selenium (`backend/tests/system/`) |
|---|---|---|
| Language | JavaScript (lives with the frontend) | Python (lives with the backend) |
| Status | wired into CI (`frontend-e2e` job) | wired into CI (`system` job) |
| Covers | UC1-UC9, one spec each | UC1, UC2, UC3, UC4, UC6, UC7, UC8, UC9 — with plan IDs |
| Nice-to-haves | auto-waiting, trace viewer, codegen | — |

These are the **same tier of the pyramid**, and the overlap is now deliberate rather than
avoided. This folder used to stick to the login boundary so it would not re-drive flows the
Selenium suite already owned; that policy was dropped so the PM3 plan has a browser-E2E slot per
use case. The cost is real and worth stating: **a flow covered in both suites is a flow whose
failures have to be diagnosed twice.** To keep that cost down, the specs here assert the same
observable postconditions and use the same selectors as their Selenium counterparts, so a change
to the UI breaks both together with the same message rather than one at a time. **Long-term, still
pick one.**

Shared setup (`logIn`, `openLearner`) lives in `_helpers.js` — the counterpart to
`backend/tests/system/_helpers.py`. `login.spec.js` keeps its own inline copy on purpose: a test
for login that authenticates through a shared login helper proves the helper, not the feature.

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
treating a pass as evidence: `playwright test` exits 0 when every spec is skipped, which is how
this job once reported green while running two specs out of nine. CI now fails a run in which
nothing executed (see below), but locally that is on you to notice.

Several specs need a learner as well as credentials, and skip individually without one:

| Variable | Used by | Must be |
|---|---|---|
| `TEST_LEARNER_ID` | UC2, UC3 | a learner **with** DIAL marks |
| `TEST_UNSCORED_LEARNER_ID` | UC2, UC3 | a learner with **no** DIAL marks |
| `TEST_SHARE_LEARNER_ID` | UC4, UC7 | a learner who already has a **generated activity** |

Credentials must belong to the Supabase **test** project, never production.

Useful while writing specs: `npx playwright test --headed`, `--debug`, `--ui`, and
`npx playwright codegen http://127.0.0.1:4173`.

## CI

The `frontend-e2e` job in `.github/workflows/tests.yml` starts the backend, builds and serves the
frontend, installs chromium, and runs `npm run test:e2e`, uploading the HTML report on failure.

It then **fails the job if zero tests actually ran**. On CI the config adds a `json` reporter
(`playwright-results.json`), and the "Fail if no browser tests actually ran" step reads its
`stats` block. Without that check an all-skipped run — missing secrets, or a `describe.skip` left
in a spec — passes silently, and a green badge gets read as browser coverage it does not have.

The same step also **annotates every spec file that ran nothing**, which catches the subtler
shape: with the three learner-id secrets unset, login / sign-up / upload-assessment /
view-learners still run, so the run is non-empty and goes green while UC2, UC3, UC4 and UC7 never
execute. That is a warning rather than a failure — an unset secret is a configuration choice, and
only a wholly dead tier is an error — so **read the annotations, not just the tick**.

It shares the `supabase-test-project` **concurrency group** with `backend-e2e` and `system`, and
runs last in the chain `backend-e2e -> system -> frontend-e2e`. All three
mutate one Supabase project, and letting two of them run at once has already broken a CI run —
see the note on the `backend-e2e` job.
