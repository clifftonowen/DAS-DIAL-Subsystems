"""System-level fixtures: env gating + screenshot-on-failure.

System tests assume the built frontend is already being served (vite preview)
and the backend is running — see backend/tests/README.md for the two commands,
and the `system` job in .github/workflows/tests.yml for the CI wiring.
"""
import os
from pathlib import Path

import pytest

_ARTIFACT_DIR = Path(os.environ.get("SYSTEM_ARTIFACT_DIR", "test-artifacts"))


@pytest.fixture
def system_creds():
    """Skip system tests unless the test project + test-user creds are present."""
    needed = ["SUPABASE_URL", "SUPABASE_KEY",
              "TEST_THERAPIST_EMAIL", "TEST_THERAPIST_PASSWORD"]
    missing = [n for n in needed if not os.environ.get(n)]
    if missing:
        pytest.skip(f"system tests need env: {', '.join(missing)}")
    return {
        "email": os.environ["TEST_THERAPIST_EMAIL"],
        "password": os.environ["TEST_THERAPIST_PASSWORD"],
    }


# --- screenshot on failure -------------------------------------------------- #
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Record each phase's result on the item so teardown can detect failure."""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


def pytest_runtest_teardown(item):
    """After a failed system test, dump a screenshot from the live driver into
    SYSTEM_ARTIFACT_DIR (uploaded by the CI `system` job for debugging)."""
    rep = getattr(item, "rep_call", None)
    if rep is None or not rep.failed:
        return
    drv = item.funcargs.get("driver")
    if drv is None:
        return
    _ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        drv.save_screenshot(str(_ARTIFACT_DIR / f"{item.name}.png"))
    except Exception:
        pass
