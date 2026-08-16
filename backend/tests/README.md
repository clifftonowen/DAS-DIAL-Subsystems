# Testing guide

How the test pyramid is wired and how to add tests at each level. Run everything
from the `backend/` directory (config lives in `backend/pytest.ini`).

```
tests/
  conftest.py            # shared fixtures (client, auth_ok, fake_supabase, access_token, driver…)
  support/fake_supabase.py   # in-memory Supabase double
  unit/                  # marker: unit         — fast, everything mocked
  integration/           # marker: integration  — real layers, DB driver faked
  e2e/                   # marker: e2e           — real test project, real JWT
  system/                # marker: system        — Selenium, real browser
```

Select a level with its marker: `pytest -m unit`, `-m integration`, `-m e2e`, `-m system`,
or `-m "unit or integration"` for the hermetic set.

**Naming.** Tests derived from a use case are named for it — `test_uc6_log_in.py`,
`test_uc8_sign_up.py` — and the same filename appears in each tier directory, so a case ID
in the test plan traces straight to a file. Every test's docstring names its case ID
(UT-6.5, IT-8.3, …). Tests not tied to one use case keep a subject name
(`test_learner_repository.py`) or a call-graph-level name (`test_service_repo.py`).

## The two seams every backend test uses

1. **Auth** — `app.core.security.current_therapist`. Unit/integration bypass it with the
   `auth_ok` fixture (`app.dependency_overrides`). E2E uses a **real** token from `access_token`.
2. **Database** — everything reaches Supabase through `app.core.supabase_client.get_supabase()`.
   The `fake_supabase` fixture swaps in an in-memory double (`tests/support/fake_supabase.py`)
   and patches **four** modules that imported the name (`core.supabase_client`,
   `repositories.base`, `core.security`, `gateways.auth_gateway`), so no test touches the network.

`FakeSupabase` also doubles the **Authentication Service** for UC6/UC8:

```python
fake = fake_supabase(
    seed={"users": [{"id": uid, "email": "t@das.org.sg"}]},   # the DB
    auth_users=[{"id": uid, "email": "t@das.org.sg", "password": "Passw0rd!"}],
    confirm_email=False,      # True -> sign_up returns a user but no session
)
fake.queries_on("users")      # [(table, op), …] — prove an edge was NOT taken
```

`missing_rpcs={"distinct_semesters"}` makes that Postgres function raise **PGRST202**, modelling a
project whose migrations are behind. The call is still logged, so a test can prove the fast path
was attempted before the caller fell back — the only thing distinguishing the two paths, since
both return the same list (UT-2.74 – UT-2.76).

`sign_up` / `sign_in_with_password` raise the **real** gotrue exception classes, and the
one live Supabase raises for each case — a weak password is `AuthWeakPasswordError`,
which is *not* an `AuthApiError`. `AuthGateway` therefore catches gotrue's base
`AuthError`; catching `AuthApiError` used to let a short password escape as a 500.
IDs in fixtures must be real UUIDs, because `UserRepository` speaks `Therapist` entities
and `Therapist.id` is a `UUID`.

---

## Unit — one activation bar, all collaborators mocked

Backend (`tests/unit/`):

```python
import pytest
from unittest.mock import Mock
from fastapi import HTTPException
from app.services.learner_service import LearnerService

pytestmark = pytest.mark.unit

def test_get_learner_404_when_missing():
    svc = LearnerService()
    svc.learners = Mock()                        # replace the collaborator
    svc.learners.find_by_id.return_value = None
    with pytest.raises(HTTPException) as exc:
        svc.get_learner("nope")
    assert exc.value.status_code == 404
```

Router units use `client` + `auth_ok` and monkeypatch the service method
(see `tests/unit/test_learners_router.py`).

Frontend (`frontend/src/**/__tests__/*.test.jsx`) — Jest + React Testing Library. Mock
`../lib/supabase` so the real client never loads:

```jsx
jest.mock("../../lib/supabase", () => ({ supabase: { auth: { signOut: jest.fn() } } }));
import { render, screen } from "@testing-library/react";
import ProfileMenu from "../ProfileMenu";

test("shows the email", async () => {
  render(<ProfileMenu session={{ user: { email: "a@b.com" } }} />);
  // ...
});
```

For a full step-by-step on adding a new frontend component test, see
**[`frontend/test/README.md`](../../frontend/test/README.md)**.

## Integration — bottom-up call graph, only the DB driver faked

Use `fake_supabase(seed={...})`; use REAL services/repositories/routers on top.

```python
import pytest
pytestmark = pytest.mark.integration

def test_list_learners_end_to_end_through_fake_db(client, auth_ok, fake_supabase):
    fake_supabase(seed={"learners": [{"id": "l1", "name": "Ada"}]})
    resp = client.get("/learners")            # router -> service -> repo -> fake DB
    assert resp.status_code == 200
    assert resp.json()[0]["name"] == "Ada"
```

Start a new module at the lowest layer touched and add one test per layer moving up
(repo → service+repo → router+service+repo), mirroring `tests/integration/`.

## E2E — one full-stack flow per use case (real test project)

Request `access_token` (real JWT) and send it as a bearer header. Auto-skips without secrets.

```python
import pytest
pytestmark = pytest.mark.e2e

def test_list_learners(client, access_token):
    r = client.get("/learners", headers={"Authorization": f"Bearer {access_token}"})
    assert r.status_code == 200
```

For LLM-backed use cases, stub the model deterministically with the built-in seam
`LLMApiClient.use_provider(FakeProvider())` — see `tests/e2e/test_uc_generate_profile.py`.

**Env:** `SUPABASE_URL`, `SUPABASE_KEY`, `TEST_THERAPIST_EMAIL`, `TEST_THERAPIST_PASSWORD`
(the therapist must exist in the test project — seed via `infra/seed.sql` or the dashboard).

**Tests that write** (UC8 sign-up) must register what they create for teardown, or the test
project accumulates junk accounts on every CI run:

```python
def test_signup(client, throwaway_email, cleanup_users):
    r = client.post("/auth/signup", json={"email": throwaway_email, "password": PASSWORD})
    cleanup_users(r.json()["user_id"])        # deleted in teardown, service-role key
```

`throwaway_email` uses `@example.com` (RFC 2606, undeliverable). Do **not** switch it to a
`.local` or `.example` address: `Credentials.email` is a pydantic `EmailStr` and
email-validator rejects special-use domains with 422 before the request reaches Supabase.
If "Confirm email" is on for the test project, sign-up issues no session — the tests detect
that from `email_confirmation_required` and skip the follow-up log-in with a message naming
the setting, rather than failing on configuration.

## System — Selenium, real browser, per use case

Request `system_creds` **before** `driver` so the test skips without launching Chrome when env
is missing. Use the `login()` / `sign_up()` / `feedback()` / `is_signed_in()` helpers in
`tests/system/_helpers.py` and the `frontend_url` fixture. UC8's browser tests create real
accounts, so they register the address with `cleanup_emails` (see the e2e note above).

```python
import pytest
pytest.importorskip("selenium")
from tests.system._helpers import login
pytestmark = pytest.mark.system

def test_dashboard(system_creds, driver, frontend_url):
    login(driver, frontend_url, system_creds["email"], system_creds["password"])
    assert "Learners" in driver.find_element("tag name", "body").text
```

Selectors come from the real components (`#email`, `#password`, "Log in", "My Profile").
A failing test drops a screenshot into `SYSTEM_ARTIFACT_DIR` (CI uploads them).

**Before running:** start the backend (`uvicorn app.main:app --port 8000`) and serve the built
frontend (`npm run build && npm run preview -- --port 4173`) with `VITE_API_URL`,
`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` set. Set `SELENIUM_HEADLESS=0` to watch it run.

---

## Markers & CI

Markers are declared in `pytest.ini` (`--strict-markers` rejects typos). CI runs each level as a
separate job in `.github/workflows/tests.yml`; backend-e2e/system read repo Secrets and self-skip until
those are configured.

---

## UC2 traceability — Generate Learner Profile + cohort clustering

Every UC2 test carries its plan ID in its docstring (`"""UT-2.5: ..."""`), and each module's
docstring maps activation bars to the IDs it covers — the convention UC6/UC8 established.

### Superseded by the design change — UT-2.1 – UT-2.11 and IT-2.1 – IT-2.11

**These eleven plan IDs are void, and the files the plan named were never written.** They are
listed here rather than deleted so a reader tracing the PM3 plan finds out *why* there is no
`test_uc2_generate_profile.py` instead of concluding the tier is missing.

The plan's UC2 assumed `ProfilingAlgorithm.analyse()` deriving seven cognitive dimensions from
`assessment_records.task_results` by keyword, then persisting them through
`LearnerProfileRepository.saveProfile()` into a `learner_profiles` table. Both are gone. The
dimensions were mock scaffolding; the system standardises on the four marks DAS actually
measures, and `learner_profiles` was dropped in the 2026-08-07 merge (`activity_repository.py:17`
records the foreign key that moved with it). "Generate a profile" is now a **promotion**: read
the newest `learner_sittings` row and make it the learner's current marks. There is no
derivation left to test.

| Void bar | What the plan expected | Status | Covered instead by |
|----------|------------------------|--------|--------------------|
| AB2.2 | `ProfileController.generateProfile` | reshaped | **IT-2.29 – IT-2.32** (`integration/test_uc2_generate_profile.py`) |
| AB2.3 | `ProfilingService.generateProfile` | reshaped | **UT-2.61, UT-2.62**, IT-2.28 |
| AB2.4 | `AssessmentRepository.findByLearner` | no longer the source | **UT-2.64, UT-2.65**, IT-2.27 |
| AB2.5 | `ProfilingAlgorithm.analyse` | **deleted** | nothing — the method does not exist |
| AB2.6 | `LearnerProfileRepository.saveProfile` | **table dropped** | nothing — the table does not exist |
| — | IT-2.1 – IT-2.11 | reshaped | IT-2.12 onwards, below |

Two IDs are worth calling out because they look like holes but are not:
`ProfilingService` raises exactly one error now, `NoScoresError` (409), covered by UT-2.62 and
IT-2.30; and the sitting history the plan expected `findByLearner` to return is UT-2.63 /
`list_sittings()`.

`integration/test_uc2_generate_profile.py` **reuses the plan's file name** for IT-2.27 – IT-2.32.
The name is the one the plan gave IT-2.1 – IT-2.11, so a reader tracing the plan lands somewhere
real; the contents are the current design's, not the void one's.

### The current map — AB2.7 onwards

Everything below either extends the plan (clustering, the workbook, the React tier carry no IDs
there) or replaces a void bar above. The IDs **continue** the sequence rather than renumbering
it, so surviving plan rows stay valid and the plan needs only appending.

| Bar | Unit under test | IDs | File |
|-----|-----------------|-----|------|
| AB2.7 | `ProfilingAlgorithm.cluster` | UT-2.12 – UT-2.18 | `unit/test_profiling_algorithm_cluster.py` |
| AB2.8 | `ProfilingAlgorithm.cluster_by_group` | UT-2.19, UT-2.20 | `unit/test_profiling_algorithm_cluster.py` |
| AB2.9 | `dial_workbook.load_latest_per_student` | UT-2.21, UT-2.22 | `unit/test_dial_workbook.py` |
| AB2.10 | `dial_workbook._collapse_writing` | UT-2.23, UT-2.24 | `unit/test_dial_workbook.py` |
| AB2.11 | `dial_workbook._band_group` | UT-2.25 | `unit/test_dial_workbook.py` |
| AB2.12 | `dial_workbook.coverage` + feature sets | UT-2.26 | `unit/test_dial_workbook.py` |
| AB2.13 | `Graph.jsx` (React) | UT-2.27 – UT-2.36 | `frontend/src/components/__tests__/Graph.test.jsx` |
| AB2.14 | `LearnerOverviewService.get_overview` | UT-2.37, UT-2.38 | `unit/test_learner_overview_service.py` |
| AB2.15 | `LearnerOverviewService._metrics` | UT-2.39, UT-2.40 | `unit/test_learner_overview_service.py` |
| AB2.16 | `ingest_dial_data.build_rows` | UT-2.43, UT-2.44 | `unit/test_ingest_dial_data.py` |
| AB2.18 | `dial_workbook.percentiles` | UT-2.46, UT-2.47 | `unit/test_dial_workbook.py` |
| AB2.19 | `ProfileRadarChart.jsx` (React) | UT-2.48 – UT-2.52 | `frontend/src/components/__tests__/ProfileRadarChart.test.jsx` |
| AB2.20 | `MainPage.jsx` (React) | UT-2.53 – UT-2.55 | `frontend/src/views/__tests__/MainPage.clusterClickthrough.test.jsx` |
| AB2.21 | `LearnersPage.jsx` (React) | UT-2.56 – UT-2.60 | `frontend/src/views/__tests__/LearnersPage.test.jsx` |
| AB2.22 | `ProfilingService.generate_profile` | UT-2.61, UT-2.62 | `unit/test_profiling_service.py` |
| AB2.23 | `ProfilingService.list_sittings` | UT-2.63 | `unit/test_profiling_service.py` |
| AB2.24 | `LearnerSittingRepository` | UT-2.64, UT-2.65 | `unit/test_learner_sitting_repository.py` |
| AB2.28 | `LearnerSittingRepository.distinct_semesters` | UT-2.74 – UT-2.76 | `unit/test_learner_sitting_repository.py` |
| AB2.25 | `ScoreHistoryChart.jsx` (React) | UT-2.66 – UT-2.70 | `frontend/src/components/__tests__/ScoreHistoryChart.test.jsx` |
| AB2.26 | `dial_workbook.latest_per_semester` | UT-2.71, UT-2.72 | `unit/test_dial_workbook.py` |
| AB2.27 | `tests.support.fake_supabase` contract | UT-2.73 | `unit/test_fake_supabase_contract.py` |
| — | bottom-up call graph for `/dashboard/clusters` | IT-2.12 – IT-2.19 | `integration/test_dashboard_clusters.py` |
| — | bottom-up call graph for `/learners/{id}/overview` | IT-2.20 – IT-2.26 | `integration/test_learner_overview.py` |
| — | bottom-up call graph for `POST /profiles/{id}` | IT-2.27 – IT-2.32 | `integration/test_uc2_generate_profile.py` |

**AB2.17 and UT-2.41, UT-2.42, UT-2.45 are unused.** They were reserved while the workbook bars
were being split and never claimed. Left as gaps deliberately: renumbering to close them would
invalidate every ID already written into a docstring.

Within AB2.13, the two dashboard controls are:

| IDs | Covers |
|-----|--------|
| UT-2.34 | the clustering scope toggle — default is cohort, switching re-colours, a selected chip is cleared |
| UT-2.35 | the band filter — narrows plot and legend, works in both scopes, **never recolours a surviving point** |

UT-2.35's colour-stability case is the load-bearing one. Colours are assigned by index into
the sorted label list, so deriving them from the *filtered* rows would renumber the palette on
every filter change and repaint the whole plot. `Graph.jsx` builds its `palette` from the
unfiltered rows to prevent exactly that, and this test is what holds it in place.

### The browser and end-to-end tiers

**ST-2.1 and ST-2.2 are implemented** in `system/test_uc2_generate_profile.py`, with a Playwright
counterpart in `frontend/e2e/generate-profile.spec.js`. ST-2.1 is the happy path; ST-2.2 is the
no-scores branch, which the page turns into UC1's upload modal rather than an error.

**ST-2.3 and ST-2.4 will not be implemented.** Only two of the plan's four ST-2 branches are
reachable, because UC2 now has two failure modes rather than four (see the error table below):
3 and 4 were written against `NoPatternError` and `ProfileGenerationError`, which no longer exist.
Do not re-add them from the PDF — there is no code path that raises them.

The UC2 **end-to-end** flow is `e2e/test_uc_generate_profile.py`: the happy path (promotion returns
200 with the learner's id) and alt flow 2a (no sittings -> 409). Its alt branches 6.2/7.2 and
6.3/7.3 are void for the same reason as ST-2.3/2.4.

### Error types UC2 actually raises

**The plan's four-way error table is void.** It described `EmptyDataError` (404),
`NoPatternError`, `ProfileGenerationError` (422) and `StorageError` (500). The first three were
removed with `analyse()` and the `learner_profiles` table; a promotion cannot fail to find a
pattern, because it derives nothing. What `routers/profiles.py:28-33` maps today:

| Exception | Raised by | Flow | HTTP | Covered by |
|-----------|-----------|------|------|------------|
| `NoScoresError` | `services/profiling_service.py:38` | learner has no sittings | **409** | UT-2.62, IT-2.28d, **IT-2.30** |
| `StorageError` | `repositories/base.py` | database refused | 500 | **IT-2.32b** (forced) |

**`StorageError` is never raised on this path, so the router's `except` clause is dead code.**
`repositories/base.StorageError` is raised in four places (`assessment_repository`,
`assessment_service` ×2, `review_service`), and neither `LearnerRepository.save` nor
`LearnerSittingRepository.latest_for_learner` is one of them: both call `.execute()` bare. A real
outage during Generate Profile therefore escapes as the raw driver exception, and FastAPI turns
it into a 500 with no `detail`. IT-2.32 pins that as the *actual* behaviour so wrapping the
repository later fails the test loudly; IT-2.32b proves the clause itself maps correctly once
something does raise it. The fix belongs in `LearnerRepository`, not in the tests.

**409, not 404, and that distinction is load-bearing.** The learner exists and the request was
well-formed; the resource is just not in a state that can satisfy it yet. `LearnerDetailPage`
keys its inline "upload an assessment" prompt off exactly this status, so collapsing it into 404
(which also means "no such learner") would leave the UI unable to tell the two apart. This is
also the status UC1 exists to stop the therapist ever seeing.

---

## UC3 traceability — Generate Adaptive Learning Activity

Most of UC3 carries its plan IDs in docstrings the usual way (`unit/test_uc3_activity_graph.py`
holds UT-3.3 – UT-3.9). Six plan IDs do **not** appear anywhere, and all six are covered — just at
a different tier or under a different number. Mapped here so a reader tracing the PM3 plan does not
conclude the tier is missing.

| Plan ID | What the plan named | Covered by |
|---------|---------------------|------------|
| UT-3.1 | `ActivityGenerationService.generateActivity` (valid) | `unit/test_activity_generation_service.py` — `build_query` and what `generate` persists |
| UT-3.2 | best flagged attempt returned | **IT-3.9** (`integration/test_uc3_generate_activity.py`) — the loop that produces a best attempt is not reachable from the service's own unit |
| UT-3.10 | `ActivityRepository` persists a VALIDATED activity | `unit/test_activity_generation_service.py` (the saved-row group), **IT-3.8** |
| UT-3.11 | `ActivityRepository` persists a FLAGGED activity | **IT-3.9, IT-3.10** |
| UT-3.12 | controller displays a validated activity | **IT-3.11** (`frontend/src/views/__integration__/LearnerDetailPage.uc3.integration.test.jsx`) |
| UT-3.13 | controller displays a flagged activity | **IT-3.12** (same file) |

**IT-3.2 and IT-3.3 do not mean what the plan says.** `integration/test_uc3_generate_activity.py`
gave those two numbers to its guardrail cases, which were written first, and the plan's retry-loop
pair continues the sequence as **IT-3.8 / IT-3.9** rather than renumbering passing tests — the same
convention UC2's clustering IDs used. Follow the plan IDs and you land on the guardrails.

**ST-3.3 and ST-3.4 are not implemented, deliberately.** Both are claims about the validate loop
(reprompt-then-succeed; FLAGGED at max_retries), and driving either needs a `ValidativeAgent` whose
verdict the test controls. The only seam for that is `LLMApiClient.use_provider(...)`, which is
in-process; the system tier drives a separate backend over HTTP and cannot reach it, so the verdict
would come from a real model and the test would pass or fail on the model's mood. The behaviour is
pinned at the tiers that can control it: UT-3.4 / UT-3.5 and IT-3.8 / IT-3.9. See the docstring in
`system/test_uc3_generate_activity.py`.

---

## UC5 traceability — Retrieve Instructional Strategy (included by UC3)

**The diagram's names are not the code's names.** The UC5 sequence diagram labels its lifelines
`RetrievalService` and `KnowledgeBaseRepository`. What `ActivityGenerationService` actually calls
is `CurriculumRetrievalService` / `CurriculumRepository`, over the `curriculum_chunks` corpus
rather than an `instructional_strategies` one. Mapped here rather than renaming either side:

| Diagram lifeline | Code |
|------------------|------|
| `RetrievalService.retrieve()` | `CurriculumRetrievalService.retrieve()` |
| `KnowledgeBaseRepository.search()` | `CurriculumRepository.hybrid_match_curriculum()` |
| `instructional_strategies` | `curriculum_chunks` |

| Bar | Unit under test | IDs | File |
|-----|-----------------|-----|------|
| AB5.1 | `CurriculumRetrievalService.retrieve` | UT-5.5 – UT-5.9 | `unit/test_uc5_retrieve_strategy.py` |
| AB5.2 | `LLMApiClient.embed` / `embed_many` | UT-5.10, UT-5.11 | `unit/test_uc5_retrieve_strategy.py` |
| AB5.3 | `CurriculumRepository.*match_curriculum` | UT-5.12, UT-5.13 | `unit/test_uc5_retrieve_strategy.py` |
| AB5.4 | `curriculum_repository._with_alt` | UT-5.14, UT-5.15 | `unit/test_uc5_retrieve_strategy.py` |
| AB5.5 | `llm_client._unit` | UT-5.16, UT-5.17 | `unit/test_uc5_retrieve_strategy.py` |
| AB5.6 | `OllamaProvider._task_prefix` | UT-5.18 | `unit/test_uc5_retrieve_strategy.py` |
| — | bottom-up call graph, levels 1→2 | IT-5.1, IT-5.3, IT-5.4 | `integration/test_uc5_retrieve_strategy.py` |

**UT-5.1 – UT-5.4 are reserved, not missing.** They belong to the diagram's `RetrievalService`
lifeline; the unit IDs start at UT-5.5 so the plan's own numbering stays usable if that lifeline
is ever implemented as a second corpus. **IT-5.2 is absent** for the same reason: the integration
call graph has two levels, not three, because there is no service between the repository and the
RPC.

### The one thing a UC5 reader must know

`retrieve()` catches **every** exception and returns `[]` (`curriculum_retrieval_service.py:52`).
An empty corpus, a filter that matched nothing, a missing migration and Supabase being down are
all indistinguishable to a caller. That is survivable only because UC3's `MIN_SIMILARITY` gate
treats no-grounding as fatal and refuses to generate, so a swallowed outage becomes a refusal
rather than an ungrounded activity. **UT-5.9 pins the swallow and says why**; remove the gate
above it and this becomes a silent failure that produces confident, unsourced worksheets.
