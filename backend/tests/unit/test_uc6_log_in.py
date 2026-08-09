"""UNIT — UC6 Log In.

One test per activation bar of the UC6 sequence diagram, every collaborator
mocked. Bars, in right-to-left diagram order:

    AB6.2  AuthController.log_in          UT-6.3, UT-6.4
    AB6.3  AuthService.authenticate       UT-6.5, UT-6.6, UT-6.7
    AB6.4  AuthService.create_session     UT-6.8   (the nested self-call)
    AB6.5  UserRepository.find_by_email   UT-6.9, UT-6.10
    AB6.6  AuthGateway.verify             UT-6.11, UT-6.12

AB6.1 (AuthView) is a React bar — see
frontend/src/views/__tests__/AuthView.uc6.test.jsx for UT-6.1 and UT-6.2.
"""
import pytest
from unittest.mock import Mock

from app.entities.models import Therapist
from app.gateways.auth_gateway import AuthGateway, AuthResponse
from app.repositories.user_repository import UserRepository
from app.routers import auth as auth_router
from app.services.auth_service import AuthError, AuthService

pytestmark = pytest.mark.unit

# Therapist.id is a UUID, so fixtures use real UUIDs rather than "u-001" labels.
THERAPIST_ID = "11111111-1111-4111-8111-111111111111"
EMAIL = "therapist@das.org.sg"
PASSWORD = "Passw0rd!"


def _ok_response(access_token="jwt.test"):
    return AuthResponse(
        ok=True,
        user_id=THERAPIST_ID,
        access_token=access_token,
        refresh_token="rt.test",
        expires_at=4102444800,  # 2100-01-01, comfortably in the future
    )


# --------------------------------------------------------------------------- #
# AB6.2 — AuthController.log_in
# --------------------------------------------------------------------------- #
def test_log_in_returns_session_on_valid_credentials(client, monkeypatch):
    """UT-6.3: valid credentials -> 200 and the Session DTO."""
    from app.schemas.dto import Session

    authenticate = Mock(return_value=Session(
        user_id=THERAPIST_ID, email=EMAIL,
        access_token="jwt.test", refresh_token="rt.test", expires_at=4102444800,
    ))
    monkeypatch.setattr(auth_router.svc, "authenticate", authenticate)

    resp = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})

    assert resp.status_code == 200
    assert resp.json()["access_token"] == "jwt.test"
    assert resp.json()["user_id"] == THERAPIST_ID
    authenticate.assert_called_once_with(EMAIL, PASSWORD)


def test_log_in_returns_401_on_auth_error(client, monkeypatch):
    """UT-6.4: AuthError from the service -> 401 with a detail, no token."""
    def boom(_email, _password):
        raise AuthError("Invalid email or password")

    monkeypatch.setattr(auth_router.svc, "authenticate", boom)

    resp = client.post("/auth/login", json={"email": EMAIL, "password": "wrong"})

    assert resp.status_code == 401
    assert "Invalid email or password" in resp.json()["detail"]
    assert "access_token" not in resp.json()


# --------------------------------------------------------------------------- #
# AB6.3 — AuthService.authenticate
# --------------------------------------------------------------------------- #
def test_authenticate_returns_session_and_looks_up_the_therapist():
    """UT-6.5: happy path — token from the gateway, identity from the repository."""
    svc = AuthService()
    svc.auth = Mock()
    svc.auth.verify.return_value = _ok_response()
    svc.users = Mock()
    svc.users.find_by_email.return_value = Therapist(id=THERAPIST_ID, email=EMAIL)

    session = svc.authenticate(EMAIL, PASSWORD)

    assert session.access_token == "jwt.test"
    assert session.user_id == THERAPIST_ID
    svc.auth.verify.assert_called_once_with(EMAIL, PASSWORD)
    svc.users.find_by_email.assert_called_once_with(EMAIL)


def test_authenticate_rejects_bad_credentials_without_touching_the_repository():
    """UT-6.6: on the invalid-credentials branch the AuthService -> UserRepository
    edge is never taken. This is the interaction assertion the `alt` fragment in
    the diagram encodes: find_by_email sits inside the valid operand only."""
    svc = AuthService()
    svc.auth = Mock()
    svc.auth.verify.return_value = AuthResponse(ok=False, error="invalid login credentials")
    svc.users = Mock()

    with pytest.raises(AuthError):
        svc.authenticate(EMAIL, "wrong")

    svc.users.find_by_email.assert_not_called()


def test_authenticate_provisions_a_missing_mirror_row():
    """UT-6.7: boundary case — Supabase Auth accepts the user but we hold no
    `users` row.

    Must not blow up (an AttributeError on None out of create_session) and must
    not refuse the login: Auth already vouched for the credentials. Every
    therapist account that predates sign-up going through AuthService is in this
    state, so the row is created on the fly.
    """
    svc = AuthService()
    svc.auth = Mock()
    svc.auth.verify.return_value = _ok_response()
    svc.users = Mock()
    svc.users.find_by_email.return_value = None
    svc.users.save.side_effect = lambda t: t

    session = svc.authenticate(EMAIL, PASSWORD)

    assert session.user_id == THERAPIST_ID
    assert session.access_token == "jwt.test"
    svc.users.save.assert_called_once()
    saved = svc.users.save.call_args.args[0]
    assert isinstance(saved, Therapist)
    assert str(saved.id) == THERAPIST_ID     # id == auth uid, as register would write
    assert saved.email == EMAIL


# --------------------------------------------------------------------------- #
# AB6.4 — AuthService.create_session (nested self-call)
# --------------------------------------------------------------------------- #
def test_create_session_combines_the_auth_response_and_the_therapist():
    """UT-6.8: pure function — no collaborators. Tokens come from the auth
    response, identity from the therapist row."""
    svc = AuthService()

    session = svc.create_session(
        _ok_response(), Therapist(id=THERAPIST_ID, email=EMAIL, name="T. One")
    )

    assert session.user_id == THERAPIST_ID
    assert session.email == EMAIL
    assert session.access_token == "jwt.test"
    assert session.refresh_token == "rt.test"
    assert session.expires_at > 0


# --------------------------------------------------------------------------- #
# AB6.5 — UserRepository.find_by_email
# --------------------------------------------------------------------------- #
def test_find_by_email_maps_the_row_to_a_therapist(fake_supabase):
    """UT-6.9: the row is hydrated into a Therapist entity."""
    fake_supabase(seed={"users": [
        {"id": THERAPIST_ID, "email": EMAIL, "name": "T. One"},
    ]})

    therapist = UserRepository().find_by_email(EMAIL)

    assert str(therapist.id) == THERAPIST_ID
    assert therapist.email == EMAIL
    assert therapist.name == "T. One"


def test_find_by_email_returns_none_when_absent(fake_supabase):
    """UT-6.10: a miss is None, not an exception."""
    fake_supabase(seed={"users": [{"id": THERAPIST_ID, "email": EMAIL}]})

    assert UserRepository().find_by_email("absent@das.org.sg") is None


# --------------------------------------------------------------------------- #
# AB6.6 — AuthGateway.verify
# --------------------------------------------------------------------------- #
def test_verify_returns_ok_with_the_access_token(fake_supabase):
    """UT-6.11: a good credential pair -> ok=True carrying the session."""
    fake_supabase(auth_users=[{"id": THERAPIST_ID, "email": EMAIL, "password": PASSWORD}])

    res = AuthGateway().verify(EMAIL, PASSWORD)

    assert res.ok is True
    assert res.user_id == THERAPIST_ID
    assert res.access_token
    assert res.error is None


def test_verify_converts_an_auth_api_error_into_a_failed_response(fake_supabase):
    """UT-6.12: the Supabase AuthApiError does NOT escape the gateway — the
    service must be able to branch on a value, per the diagram's AuthResponse."""
    fake_supabase(auth_users=[{"id": THERAPIST_ID, "email": EMAIL, "password": PASSWORD}])

    res = AuthGateway().verify(EMAIL, "wrong")

    assert res.ok is False
    assert res.access_token is None
    assert "Invalid login credentials" in res.error
