"""Shared pytest fixtures for every test level.

Fixture map:
    client         -> FastAPI TestClient (all levels)
    auth_ok        -> bypass current_therapist (unit + integration)
    fake_supabase  -> in-memory DB swapped over every get_supabase() binding
    supabase_env   -> real test-project settings (e2e/system); skips if absent
    access_token   -> a real signed-in JWT for the seeded therapist (e2e)
    live_server    -> a running uvicorn instance (system)
    driver         -> headless Chrome via Selenium (system)

The DB seam: repositories reach Supabase through
`app.core.supabase_client.get_supabase`, but several modules bind that name
at import time (`from ... import get_supabase`). `fake_supabase` patches the
source *and* each importer so nothing slips through to a real network call.
"""
import os
import socket
import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.security import current_therapist


# --------------------------------------------------------------------------- #
# All levels
# --------------------------------------------------------------------------- #
@pytest.fixture
def client():
    """A TestClient bound to the real app. Dependency overrides applied by
    other fixtures (e.g. auth_ok) take effect through this instance."""
    return TestClient(app)


# --------------------------------------------------------------------------- #
# Unit + integration
# --------------------------------------------------------------------------- #
@pytest.fixture
def auth_ok():
    """Override the auth dependency so protected routes accept any request.
    Yields the fake therapist id the override returns."""
    user_id = "test-therapist-id"
    app.dependency_overrides[current_therapist] = lambda: user_id
    yield user_id
    app.dependency_overrides.pop(current_therapist, None)


@pytest.fixture
def fake_supabase(monkeypatch):
    """Swap the real Supabase client for an in-memory FakeSupabase.

    Returns a factory: call `make(seed={...})` to install a fake pre-loaded
    with rows and get the instance back for assertions. Patches every module
    that holds a `get_supabase` reference.

    For UC6/UC8, `auth_users=[{"email", "password"}]` seeds the fake
    Authentication Service and `confirm_email=True` models a project with email
    confirmation switched on.

    `missing_rpcs={"distinct_semesters"}` makes that Postgres function raise PGRST202,
    modelling a project whose migrations are behind — how the repository's fallback
    paths are exercised.
    """
    from tests.support.fake_supabase import FakeSupabase
    import app.core.supabase_client as sc
    import app.repositories.base as base
    import app.core.security as security
    import app.gateways.auth_gateway as auth_gateway

    installed = {}

    def make(seed=None, user_id="test-therapist-id", auth_users=None, confirm_email=False,
             fail_on_execute=None, missing_rpcs=()):
        fake = FakeSupabase(seed=seed, user_id=user_id,
                            auth_users=auth_users, confirm_email=confirm_email,
                            fail_on_execute=fail_on_execute, missing_rpcs=missing_rpcs)
        getter = lambda: fake
        sc.get_supabase.cache_clear()          # drop any real cached client
        sc.get_auth_supabase.cache_clear()
        monkeypatch.setattr(sc, "get_supabase", getter)      # source + lazy importers
        monkeypatch.setattr(sc, "get_auth_supabase", getter)
        monkeypatch.setattr(base, "get_supabase", getter)    # BaseRepository.db
        monkeypatch.setattr(security, "get_supabase", getter)  # current_therapist
        # AuthGateway binds the AUTH-plane client at import time. One FakeSupabase
        # stands in for both planes; the split exists to stop a real sign-in from
        # rewriting the real data client's service-role header.
        monkeypatch.setattr(auth_gateway, "get_auth_supabase", getter)
        installed["fake"] = fake
        return fake

    return make


# --------------------------------------------------------------------------- #
# E2E + system — real Supabase test project (via env / GitHub Secrets)
# --------------------------------------------------------------------------- #
def _require_env(*names):
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        pytest.skip(f"missing env for this level: {', '.join(missing)}")


@pytest.fixture
def supabase_env():
    """Skip the test unless the real test-project settings are present."""
    _require_env("SUPABASE_URL", "SUPABASE_KEY")
    return {
        "url": os.environ["SUPABASE_URL"],
        "key": os.environ["SUPABASE_KEY"],
    }


@pytest.fixture
def access_token(supabase_env):
    """A real JWT for the seeded test therapist, obtained by signing in.

    Requires TEST_THERAPIST_EMAIL / TEST_THERAPIST_PASSWORD to identify a user
    that exists in the test project (seed it once via infra/seed.sql or the
    Supabase dashboard).
    """
    _require_env("TEST_THERAPIST_EMAIL", "TEST_THERAPIST_PASSWORD")
    from supabase import create_client
    sb = create_client(supabase_env["url"], supabase_env["key"])
    res = sb.auth.sign_in_with_password({
        "email": os.environ["TEST_THERAPIST_EMAIL"],
        "password": os.environ["TEST_THERAPIST_PASSWORD"],
    })
    assert res.session, "sign-in failed against the test project"
    return res.session.access_token


@pytest.fixture
def uc4_activity(supabase_env):
    """Create one disposable activity for UC4 E2E/system review submission.

    The activity is newer than any seeded row, so LearnerDetailPage selects it
    as the learner's latest activity. Deleting it also deletes its reviews via
    the reviews.activity_id ON DELETE CASCADE foreign key.

    THE CONTENT CARRIES A UNIQUE MARKER, exposed to the test as `activity["marker"]`.
    "Newest wins" holds only while this run is the sole writer, and it has already
    failed in CI: two runs of the same commit overlapped, each inserted an activity
    for TEST_LEARNER_ID, and each browser could load the other's row — so UC4's
    delete-then-expect-a-rejected-write test deleted an activity the page was not
    showing and waited 20s for an error that was never coming. Serialising the CI
    jobs closes that window (see the concurrency group in .github/workflows/tests.yml),
    but a test that ASSUMES its own row is on screen still fails unreadably when the
    assumption breaks. Waiting for this marker turns "some other writer got here
    first" into an immediate, named failure instead of a bare TimeoutException.
    """
    _require_env("TEST_LEARNER_ID")
    from supabase import create_client

    learner_id = os.environ["TEST_LEARNER_ID"]
    marker = f"UC4 fixture activity {uuid.uuid4().hex}"
    sb = create_client(supabase_env["url"], supabase_env["key"])
    rows = sb.table("learning_activities").insert({
        "learner_id": learner_id,
        "content": {"text": marker},
        "literacy_objective": "UC4 review test",
        "level": "A2",
        "status": "GENERATED",
        "grounded_on": [],
    }).execute().data
    if not rows:
        pytest.fail("could not create the temporary UC4 activity")

    activity = {**rows[0], "marker": marker}
    yield activity

    try:
        sb.table("learning_activities").delete().eq("id", activity["id"]).execute()
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# System — running backend + headless browser
# --------------------------------------------------------------------------- #
def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def live_server():
    """Start the real app under uvicorn in a background thread for the whole
    session. Yields the base URL. Used by Selenium system tests that hit the
    API directly, and available if you serve the UI against it."""
    import uvicorn

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(100):  # wait up to ~10s for startup
        if server.started:
            break
        time.sleep(0.1)
    yield base_url
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def driver():
    """Headless Chrome via Selenium. webdriver-manager fetches the matching
    ChromeDriver. Set SELENIUM_HEADLESS=0 to watch it run locally."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    opts = Options()
    if os.environ.get("SELENIUM_HEADLESS", "1") != "0":
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1280,900")

    drv = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    drv.implicitly_wait(5)
    yield drv
    drv.quit()


@pytest.fixture
def frontend_url():
    """Where the built frontend is being served (vite preview). Defaults to
    the CI/local preview port; override with FRONTEND_URL."""
    _require_env("FRONTEND_URL") if os.environ.get("FRONTEND_URL") else None
    return os.environ.get("FRONTEND_URL", "http://127.0.0.1:4173")
