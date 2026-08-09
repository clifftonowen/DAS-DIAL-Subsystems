"""INTEGRATION — UC8 Sign Up. Call-graph based, bottom-up.

UC8 has the same lifelines as UC6 in the same order, so the levels are identical
and only the messages differ — which is why the two use cases were planned
together: the level-1 and level-2 fixtures are shared.

    Level 4   AuthView  --signUp(email, password)-->           [HTTP boundary]
    Level 3   AuthController  --register(email, password)-->
    Level 2   AuthService  --createUser(email, password)-->  AuthGateway
                           --save(therapist)-------------->  UserRepository
    Level 1   AuthGateway  --create user account-->  Authentication Service (faked)
              UserRepository  --insert-->  Supabase DB                     (faked)

The difference from UC6 is that level 2 is a **write** path with two
side-effecting edges that must both succeed, and their order is load bearing: the
auth account is created before the mirror row is written. IT-8.4 pins that the
second edge is not taken when the first fails.

Level 4 lives on the frontend — see
frontend/src/views/__integration__/AuthView.uc8.integration.test.jsx.
"""
import pytest

from app.entities.models import Therapist
from app.gateways.auth_gateway import AuthGateway
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService, SignUpError

pytestmark = pytest.mark.integration

NEW_ID = "22222222-2222-4222-8222-222222222222"
NEW_EMAIL = "new.therapist@das.org.sg"
PASSWORD = "Passw0rd!"


# --------------------------------------------------------------------------- #
# Level 1 — the leaves
# --------------------------------------------------------------------------- #
def test_user_repository_writes_through_the_fake_db(fake_supabase):
    """IT-8.1: real UserRepository over the faked Supabase DB."""
    fake = fake_supabase(seed={"users": []})

    returned = UserRepository().save(Therapist(id=NEW_ID, email=NEW_EMAIL))

    assert returned.email == NEW_EMAIL
    assert [r["id"] for r in fake.store["users"]] == [NEW_ID]


def test_auth_gateway_creates_a_user_in_the_fake_auth_service(fake_supabase):
    """IT-8.2: real AuthGateway over the faked Authentication Service."""
    fake_supabase(auth_users=[])

    res = AuthGateway().create_user(NEW_EMAIL, PASSWORD)

    assert res.ok is True
    assert res.user_id
    # The fake auth directory now holds the account, so a verify succeeds.
    assert AuthGateway().verify(NEW_EMAIL, PASSWORD).ok is True


# --------------------------------------------------------------------------- #
# Level 2 — AuthService added, gateway and repository both real
# --------------------------------------------------------------------------- #
def test_register_fires_both_edges_and_keeps_the_mirror_consistent(fake_supabase):
    """IT-8.3: the `users` row id equals the auth user id, proving both level-2
    edges fired in order and the mirror is consistent."""
    fake = fake_supabase(seed={"users": []}, auth_users=[])

    result = AuthService().register(NEW_EMAIL, PASSWORD)

    assert result.user_id
    assert len(fake.store["users"]) == 1
    assert fake.store["users"][0]["id"] == result.user_id
    assert fake.store["users"][0]["email"] == NEW_EMAIL


def test_register_skips_the_repository_edge_when_the_email_is_taken(fake_supabase):
    """IT-8.4: the gateway edge fails, so the UserRepository edge is not taken —
    the `users` table still holds exactly one row, not two."""
    fake = fake_supabase(
        seed={"users": [{"id": NEW_ID, "email": NEW_EMAIL}]},
        auth_users=[{"id": NEW_ID, "email": NEW_EMAIL, "password": PASSWORD}],
    )

    with pytest.raises(SignUpError, match="already registered"):
        AuthService().register(NEW_EMAIL, PASSWORD)

    assert len(fake.store["users"]) == 1
    assert fake.queries_on("users") == []


# --------------------------------------------------------------------------- #
# Level 3 — AuthController added, whole backend stack real
# --------------------------------------------------------------------------- #
def test_signup_route_creates_the_account_and_the_mirror_row(client, fake_supabase):
    """IT-8.5: POST /auth/signup through router -> service -> gateway/repo."""
    fake = fake_supabase(seed={"users": []}, auth_users=[])

    resp = client.post("/auth/signup", json={"email": NEW_EMAIL, "password": PASSWORD})

    assert resp.status_code == 200
    assert resp.json()["email"] == NEW_EMAIL
    assert resp.json()["user_id"]
    assert len(fake.store["users"]) == 1


def test_signup_route_rejects_a_short_password_without_a_partial_write(client, fake_supabase):
    """IT-8.6: a password below the Supabase minimum fails at the gateway, so no
    `users` row is written — the write path leaves no partial state."""
    fake = fake_supabase(seed={"users": []}, auth_users=[])

    resp = client.post("/auth/signup", json={"email": NEW_EMAIL, "password": "abc"})

    assert resp.status_code == 400
    assert resp.json()["detail"]
    assert fake.store["users"] == []


def test_signup_then_login_succeeds(client, fake_supabase):
    """IT-8.7: cross use case — UC8's postcondition satisfies UC6's precondition.
    Signing up and then logging in with the same credentials yields a token."""
    fake_supabase(seed={"users": []}, auth_users=[])

    signup = client.post("/auth/signup", json={"email": NEW_EMAIL, "password": PASSWORD})
    assert signup.status_code == 200

    login = client.post("/auth/login", json={"email": NEW_EMAIL, "password": PASSWORD})

    assert login.status_code == 200
    assert login.json()["access_token"]
    assert login.json()["user_id"] == signup.json()["user_id"]
