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

## The two seams every backend test uses

1. **Auth** — `app.core.security.current_therapist`. Unit/integration bypass it with the
   `auth_ok` fixture (`app.dependency_overrides`). E2E uses a **real** token from `access_token`.
2. **Database** — everything reaches Supabase through `app.core.supabase_client.get_supabase()`.
   The `fake_supabase` fixture swaps in an in-memory double (`tests/support/fake_supabase.py`)
   and patches every module that imported the name, so no test touches the network.

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

## System — Selenium, real browser, per use case

Request `system_creds` **before** `driver` so the test skips without launching Chrome when env
is missing. Use the `login()` helper and `frontend_url`.

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
separate job in `.github/workflows/tests.yml`; e2e/system read repo Secrets and self-skip until
those are configured.
