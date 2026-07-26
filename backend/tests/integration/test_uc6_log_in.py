"""INTEGRATION — UC6 Log In. Call-graph based, bottom-up.

The call graph is read straight off the UC6 sequence diagram: each lifeline is a
node, each synchronous message an edge, and a lifeline's call depth is its level.
Bottom-up means starting at the rightmost lifelines (the leaves) and adding one
lifeline to the left per level.

    Level 4   AuthView  --logIn(email, password)-->            [HTTP boundary]
    Level 3   AuthController  --authenticate(email, password)-->
    Level 2   AuthService  --verify(email, password)-->  AuthGateway
                           --findByEmail(email)------->  UserRepository
    Level 1   AuthGateway  --verify credentials-->  Authentication Service (faked)
              UserRepository  --select-->  Supabase DB                    (faked)

Only the driver at the boundary is faked (`FakeSupabase`); everything below each
level is real code. The `create Session` nested self-call sits inside AuthService,
so it enters at level 2 and needs no level of its own.

Level 4 lives on the frontend — see
frontend/src/views/__integration__/AuthView.uc6.integration.test.jsx.
"""
import pytest

from app.gateways.auth_gateway import AuthGateway
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthError, AuthService

pytestmark = pytest.mark.integration

THERAPIST_ID = "11111111-1111-4111-8111-111111111111"
EMAIL = "therapist@das.org.sg"
PASSWORD = "Passw0rd!"

_USER_ROW = {"id": THERAPIST_ID, "email": EMAIL, "name": "T. One"}
_CREDENTIALS = [{"id": THERAPIST_ID, "email": EMAIL, "password": PASSWORD}]


def _seed(fake_supabase, **kw):
    """Both level-1 drivers seeded consistently: the `users` mirror row and the
    matching credential pair in the fake Authentication Service."""
    return fake_supabase(seed={"users": [_USER_ROW]}, auth_users=_CREDENTIALS, **kw)


# --------------------------------------------------------------------------- #
# Level 1 — the leaves
# --------------------------------------------------------------------------- #
def test_user_repository_reads_through_the_fake_db(fake_supabase):
    """IT-6.1: real UserRepository over the faked Supabase DB."""
    _seed(fake_supabase)

    therapist = UserRepository().find_by_email(EMAIL)

    assert str(therapist.id) == THERAPIST_ID
    assert therapist.email == EMAIL


def test_auth_gateway_verifies_through_the_fake_auth_service(fake_supabase):
    """IT-6.2: real AuthGateway over the faked Authentication Service."""
    _seed(fake_supabase)

    res = AuthGateway().verify(EMAIL, PASSWORD)

    assert res.ok is True
    assert res.access_token


# --------------------------------------------------------------------------- #
# Level 2 — AuthService added, gateway and repository both real
# --------------------------------------------------------------------------- #
def test_authenticate_wires_the_gateway_and_repository_together(fake_supabase):
    """IT-6.3: token from the fake auth driver, identity from the fake DB, with
    no application code mocked in between."""
    _seed(fake_supabase)

    session = AuthService().authenticate(EMAIL, PASSWORD)

    assert session.user_id == THERAPIST_ID
    assert session.email == EMAIL
    assert session.access_token
    assert session.refresh_token


def test_authenticate_provisions_a_legacy_account_with_no_mirror_row(fake_supabase):
    """IT-6.4a: regression — the state the real project was actually in. The auth
    account exists but the `users` table is empty, because every therapist signed
    up through the old UI, which talked to Supabase directly and never reached
    AuthService. Login must succeed and leave a mirror row behind."""
    fake = fake_supabase(seed={"users": []}, auth_users=_CREDENTIALS)

    session = AuthService().authenticate(EMAIL, PASSWORD)

    assert session.access_token
    assert session.user_id == THERAPIST_ID
    assert [r["email"] for r in fake.store["users"]] == [EMAIL]


def test_authenticate_skips_the_repository_edge_on_a_bad_password(fake_supabase):
    """IT-6.4: the AuthService -> UserRepository edge is not taken when the
    gateway edge fails — the fake DB records zero queries against `users`."""
    fake = _seed(fake_supabase)

    with pytest.raises(AuthError):
        AuthService().authenticate(EMAIL, "wrong")

    assert fake.queries_on("users") == []


# --------------------------------------------------------------------------- #
# Level 3 — AuthController added, whole backend stack real
# --------------------------------------------------------------------------- #
def test_login_route_returns_a_token(client, fake_supabase):
    """IT-6.5: POST /auth/login through router -> service -> gateway/repo -> fakes."""
    _seed(fake_supabase)

    resp = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json()["access_token"]


def test_login_route_returns_401_on_a_bad_password(client, fake_supabase):
    """IT-6.6: the failure path surfaces as 401 with a detail."""
    _seed(fake_supabase)

    resp = client.post("/auth/login", json={"email": EMAIL, "password": "wrong"})

    assert resp.status_code == 401
    assert resp.json()["detail"]


def test_login_route_rejects_a_malformed_email_before_the_service(client, fake_supabase):
    """IT-6.7: Pydantic's EmailStr on Credentials rejects the body with 422, so
    the service is never reached — no query hits either fake."""
    fake = _seed(fake_supabase)

    resp = client.post("/auth/login", json={"email": "not-an-email", "password": "x"})

    assert resp.status_code == 422
    assert fake.queries == []


def test_the_issued_token_opens_a_protected_route(client, fake_supabase):
    """IT-6.8: UC6's postcondition ("an active session") is real, not just a
    token string — the bearer it returns satisfies current_therapist, which
    calls the Authentication Service on every protected request."""
    fake_supabase(
        seed={"users": [_USER_ROW], "learners": [{"id": "l1", "pseudonym": "Ada"}]},
        auth_users=_CREDENTIALS,
    )

    token = client.post(
        "/auth/login", json={"email": EMAIL, "password": PASSWORD}
    ).json()["access_token"]

    resp = client.get("/learners", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
