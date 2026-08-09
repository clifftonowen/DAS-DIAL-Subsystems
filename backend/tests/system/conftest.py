"""System-level fixtures: env gating + screenshot-on-failure.

System tests assume the built frontend is already being served (vite preview)
and the backend is running — see backend/tests/README.md for the two commands,
and the `system` job in .github/workflows/tests.yml for the CI wiring.
"""
import os
import uuid
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


# RFC 2606 reserves example.com for testing, so it is never deliverable. Do NOT
# use a .local / .example address here: Credentials.email is a pydantic EmailStr,
# and email-validator rejects special-use domains with 422 before the request ever
# reaches Supabase. If the test project refuses example.com, change this one line.
THROWAWAY_DOMAIN = "example.com"


@pytest.fixture
def throwaway_email():
    """A unique address per run, so UC8's sign-up flow never collides with itself."""
    return f"pm3+{uuid.uuid4()}@{THROWAWAY_DOMAIN}"


@pytest.fixture
def cleanup_emails(system_creds):
    """Yields `register(email)`; deletes those accounts in teardown.

    The UI never reveals the new user's id, so cleanup resolves it from the
    `users` mirror row by email. Errors are swallowed: a test that already failed
    shouldn't be masked by a teardown error, and a missing account is the desired
    end state anyway. Without this, every run leaves a real auth user behind in
    the test project.
    """
    emails = []
    yield emails.append

    from supabase import create_client
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    for email in emails:
        try:
            rows = sb.table("users").select("id").eq("email", email).execute().data
        except Exception:
            continue
        for row in rows:
            for delete in (
                lambda: sb.table("users").delete().eq("id", row["id"]).execute(),
                lambda: sb.auth.admin.delete_user(row["id"]),
            ):
                try:
                    delete()
                except Exception:
                    pass


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
