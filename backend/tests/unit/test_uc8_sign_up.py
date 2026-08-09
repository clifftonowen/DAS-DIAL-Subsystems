"""UNIT — UC8 Sign Up.

One test per activation bar of the UC8 sequence diagram, every collaborator
mocked. Bars, in right-to-left diagram order:

    AB8.2  AuthController.sign_up        UT-8.3, UT-8.4
    AB8.3  AuthService.register          UT-8.5, UT-8.6, UT-8.7
    AB8.4  UserRepository.save           UT-8.8, UT-8.9
    AB8.5  AuthGateway.create_user       UT-8.10, UT-8.11

AB8.1 (AuthView) is a React bar — see
frontend/src/views/__tests__/AuthView.uc8.test.jsx for UT-8.1 and UT-8.2.

The order of the two level-2 messages is load bearing: the auth account is
created *before* the mirror row is written, so a failure on the second edge
leaves an orphaned auth user. UT-8.7 pins that.
"""
import pytest
from unittest.mock import Mock

from app.entities.models import Therapist
from app.gateways.auth_gateway import AuthGateway, AuthResponse
from app.repositories.user_repository import UserRepository
from app.routers import auth as auth_router
from app.services.auth_service import AuthService, SignUpError

pytestmark = pytest.mark.unit

# Therapist.id is a UUID, so fixtures use real UUIDs rather than "u-002" labels.
NEW_ID = "22222222-2222-4222-8222-222222222222"
NEW_EMAIL = "new.therapist@das.org.sg"
EXISTING_EMAIL = "existing@das.org.sg"
PASSWORD = "Passw0rd!"


# --------------------------------------------------------------------------- #
# AB8.2 — AuthController.sign_up
# --------------------------------------------------------------------------- #
def test_sign_up_returns_the_result_on_success(client, monkeypatch):
    """UT-8.3: a new email -> 200 and the SignUpResult body."""
    from app.schemas.dto import SignUpResult

    register = Mock(return_value=SignUpResult(user_id=NEW_ID, email=NEW_EMAIL))
    monkeypatch.setattr(auth_router.svc, "register", register)

    resp = client.post("/auth/signup", json={"email": NEW_EMAIL, "password": PASSWORD})

    assert resp.status_code == 200
    assert resp.json()["user_id"] == NEW_ID
    assert resp.json()["email"] == NEW_EMAIL
    register.assert_called_once_with(NEW_EMAIL, PASSWORD)


def test_sign_up_returns_400_when_the_email_is_taken(client, monkeypatch):
    """UT-8.4: SignUpError from the service -> 400 naming the duplicate."""
    def boom(_email, _password):
        raise SignUpError("User already registered")

    monkeypatch.setattr(auth_router.svc, "register", boom)

    resp = client.post("/auth/signup", json={"email": EXISTING_EMAIL, "password": PASSWORD})

    assert resp.status_code == 400
    assert "already registered" in resp.json()["detail"]
    assert "user_id" not in resp.json()


# --------------------------------------------------------------------------- #
# AB8.3 — AuthService.register
# --------------------------------------------------------------------------- #
def test_register_mirrors_the_auth_user_into_the_users_table():
    """UT-8.5: both level-2 edges fire, and the mirror row carries the auth uid."""
    svc = AuthService()
    svc.auth = Mock()
    svc.auth.create_user.return_value = AuthResponse(
        ok=True, user_id=NEW_ID, access_token="jwt.new", refresh_token="rt.new"
    )
    svc.users = Mock()

    result = svc.register(NEW_EMAIL, PASSWORD)

    assert result.user_id == NEW_ID
    assert result.email == NEW_EMAIL
    assert result.email_confirmation_required is False   # a session was issued
    svc.auth.create_user.assert_called_once_with(NEW_EMAIL, PASSWORD)
    svc.users.save.assert_called_once()
    saved = svc.users.save.call_args.args[0]
    assert isinstance(saved, Therapist)
    assert str(saved.id) == NEW_ID          # id == auth uid, per infra/schema.sql
    assert str(saved.auth_user_id) == NEW_ID
    assert saved.email == NEW_EMAIL


def test_register_does_not_write_a_mirror_row_when_the_gateway_fails():
    """UT-8.6: the gateway edge failed, so the UserRepository edge is not taken —
    no orphan `users` row for an auth account that was never created."""
    svc = AuthService()
    svc.auth = Mock()
    svc.auth.create_user.return_value = AuthResponse(
        ok=False, error="User already registered"
    )
    svc.users = Mock()

    with pytest.raises(SignUpError, match="already registered"):
        svc.register(EXISTING_EMAIL, PASSWORD)

    svc.users.save.assert_not_called()


def test_register_surfaces_a_mirror_write_failure_and_leaves_the_auth_user():
    """UT-8.7: boundary case — the auth account is created but the mirror insert
    fails. The failure must surface rather than be swallowed.

    KNOWN LIMITATION, deliberately pinned rather than fixed: there is no
    compensating delete, so the auth user is now orphaned. See the report's
    known-limitations section.
    """
    svc = AuthService()
    svc.auth = Mock()
    svc.auth.create_user.return_value = AuthResponse(ok=True, user_id=NEW_ID)
    svc.users = Mock()
    svc.users.save.side_effect = RuntimeError("insert failed")

    with pytest.raises(RuntimeError, match="insert failed"):
        svc.register(NEW_EMAIL, PASSWORD)

    # The orphan: the auth account was created and nothing rolls it back.
    svc.auth.create_user.assert_called_once_with(NEW_EMAIL, PASSWORD)


# --------------------------------------------------------------------------- #
# AB8.4 — UserRepository.save
# --------------------------------------------------------------------------- #
def test_save_writes_the_therapist_row(fake_supabase):
    """UT-8.8: the entity lands in the `users` table with id and email mapped."""
    fake = fake_supabase(seed={"users": []})

    UserRepository().save(Therapist(id=NEW_ID, email=NEW_EMAIL))

    assert len(fake.store["users"]) == 1
    assert fake.store["users"][0]["id"] == NEW_ID
    assert fake.store["users"][0]["email"] == NEW_EMAIL


def test_save_is_idempotent(fake_supabase):
    """UT-8.9: upsert semantics — saving twice leaves one row, no exception."""
    fake = fake_supabase(seed={"users": []})
    repo = UserRepository()
    therapist = Therapist(id=NEW_ID, email=NEW_EMAIL)

    repo.save(therapist)
    repo.save(therapist)

    assert len(fake.store["users"]) == 1


# --------------------------------------------------------------------------- #
# AB8.5 — AuthGateway.create_user
# --------------------------------------------------------------------------- #
def test_create_user_returns_ok_with_the_new_user_id(fake_supabase):
    """UT-8.10: a fresh email -> ok=True carrying the generated user id."""
    fake_supabase(auth_users=[])

    res = AuthGateway().create_user(NEW_EMAIL, PASSWORD)

    assert res.ok is True
    assert res.user_id
    assert res.error is None


def test_create_user_converts_a_duplicate_into_a_failed_response(fake_supabase):
    """UT-8.11: the Supabase AuthApiError does NOT escape the gateway."""
    fake_supabase(auth_users=[
        {"id": NEW_ID, "email": EXISTING_EMAIL, "password": PASSWORD},
    ])

    res = AuthGateway().create_user(EXISTING_EMAIL, PASSWORD)

    assert res.ok is False
    assert res.user_id is None
    assert "already registered" in res.error
