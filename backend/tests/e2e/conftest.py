"""E2E-only fixtures: raw test-user credentials and cleanup of created accounts.

Kept out of the shared conftest for the same reason system/conftest.py exists —
these are meaningless at the hermetic levels. Everything here chains
`supabase_env`, so an unconfigured checkout skips instead of failing.
"""
import uuid

import pytest

from tests.conftest import _require_env


@pytest.fixture
def therapist_credentials(supabase_env):
    """The seeded test therapist's email + password.

    UC6 needs the raw credentials, not just a token, because logging in *is* the
    thing under test — the shared `access_token` fixture would do the log-in for us.
    """
    _require_env("TEST_THERAPIST_EMAIL", "TEST_THERAPIST_PASSWORD")
    import os
    return {
        "email": os.environ["TEST_THERAPIST_EMAIL"],
        "password": os.environ["TEST_THERAPIST_PASSWORD"],
    }


@pytest.fixture
def service_client(supabase_env):
    """A service-role Supabase client, for teardown the API doesn't expose."""
    from supabase import create_client
    return create_client(supabase_env["url"], supabase_env["key"])


# RFC 2606 reserves example.com for testing, so it is never deliverable. Do NOT
# use a .local / .example address here: Credentials.email is a pydantic EmailStr,
# and email-validator rejects special-use domains with 422 before the request ever
# reaches Supabase. If the test project refuses example.com, change this one line.
THROWAWAY_DOMAIN = "example.com"


@pytest.fixture
def throwaway_email():
    """A unique address per test run, so a signup e2e never collides with itself."""
    return f"pm3+{uuid.uuid4()}@{THROWAWAY_DOMAIN}"


@pytest.fixture
def cleanup_users(service_client):
    """Yields a `register(user_id)` callable; deletes those users in teardown.

    Without this every signup run left a real auth user behind in the test
    project, so CI accumulated junk accounts indefinitely. Failures during
    cleanup are swallowed: a test that already failed shouldn't be masked by a
    teardown error, and a missing user is the desired end state anyway.
    """
    created = []
    yield created.append
    for user_id in created:
        try:
            service_client.table("users").delete().eq("id", user_id).execute()
        except Exception:
            pass
        try:
            service_client.auth.admin.delete_user(user_id)
        except Exception:
            pass
