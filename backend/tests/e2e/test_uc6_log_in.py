"""E2E use case: UC6 "Therapist logs in".

Boundary to boundary through the HTTP API against the REAL Supabase test project
— no fakes, no mocking, a real JWT. Auto-skips when the test-project secrets or
the test-user env are absent (see conftest: supabase_env, therapist_credentials),
so local runs and forks without secrets stay green.
"""
import pytest

pytestmark = pytest.mark.e2e


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_login_issues_a_token_that_opens_a_protected_route(client, therapist_credentials):
    """E2E-6.1: the operational flow. Logging in returns a real JWT, and that
    token satisfies `current_therapist` on a protected route — which is what UC6's
    postcondition ("an active session") actually means."""
    resp = client.post("/auth/login", json=therapist_credentials)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user_id"]

    follow_up = client.get("/learners", headers=_auth(body["access_token"]))
    assert follow_up.status_code == 200


def test_login_with_a_wrong_password_is_rejected(client, therapist_credentials):
    """E2E-6.2: alternative flow — no token is issued, and the protected route
    stays closed without one."""
    resp = client.post("/auth/login", json={
        "email": therapist_credentials["email"],
        "password": "definitely-wrong",
    })

    assert resp.status_code == 401
    assert "access_token" not in resp.json()

    assert client.get("/learners").status_code in (401, 403)
