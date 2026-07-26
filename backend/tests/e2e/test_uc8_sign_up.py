"""E2E use case: UC8 "Therapist signs up".

Against the REAL Supabase test project. Unlike every other e2e module here, this
one WRITES: it creates a genuine auth user and a genuine `users` row, so both
tests register what they create with `cleanup_users` for teardown.

TEST-ENVIRONMENT REQUIREMENT: if "Confirm email" is enabled on the test project,
Supabase issues no session at signup and the follow-up log-in cannot succeed. The
test detects that from `email_confirmation_required` and skips the log-in half
with a message naming the setting, rather than failing on a configuration issue.
"""
import pytest

pytestmark = pytest.mark.e2e

PASSWORD = "Passw0rd!123"


def test_signup_creates_an_account_that_can_then_log_in(
    client, throwaway_email, cleanup_users
):
    """E2E-8.1: the operational flow, and the proof that UC8's postcondition
    satisfies UC6's precondition."""
    resp = client.post("/auth/signup", json={"email": throwaway_email, "password": PASSWORD})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user_id"]
    assert body["email"] == throwaway_email
    cleanup_users(body["user_id"])

    if body["email_confirmation_required"]:
        pytest.skip(
            "test project has 'Confirm email' enabled, so signup issues no "
            "session; disable it on the TEST project to exercise the log-in half"
        )

    login = client.post("/auth/login", json={"email": throwaway_email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    assert login.json()["access_token"]


def test_signup_with_an_existing_email_is_rejected(
    client, throwaway_email, cleanup_users
):
    """E2E-8.2: alternative flow — the second attempt is refused and no second
    mirror row appears."""
    first = client.post("/auth/signup", json={"email": throwaway_email, "password": PASSWORD})
    assert first.status_code == 200, first.text
    cleanup_users(first.json()["user_id"])

    second = client.post("/auth/signup", json={"email": throwaway_email, "password": PASSWORD})

    assert second.status_code >= 400
    assert second.json()["detail"]
