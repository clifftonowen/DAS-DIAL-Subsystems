"""AuthService - register / authenticate / sign out therapists via Supabase.

Orchestrates the AuthGateway (external Supabase Auth) and the UserRepository
(our own `users` table). Translates Supabase auth failures into HTTP errors and
shapes responses into the DTOs the router returns.
"""
from fastapi import HTTPException, status

from app.gateways.auth_gateway import AuthGateway
from app.repositories.user_repository import UserRepository
from app.schemas.dto import SignUpResult, Session

try:  # gotrue ships with supabase; guard the import so the app still boots
    from gotrue.errors import AuthApiError
except Exception:  # pragma: no cover - fallback if the package layout changes
    AuthApiError = Exception


class AuthService:
    def __init__(self):
        self.users = UserRepository()
        self.auth = AuthGateway()

    def register(self, email: str, password: str) -> SignUpResult:
        try:
            res = self.auth.create_user(email, password)
        except AuthApiError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

        user = getattr(res, "user", None)
        session = getattr(res, "session", None)
        if user is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sign up failed")

        # Mirror the auth user into our own table. id == auth uid (see schema.sql),
        # so it matches the `sub` that current_therapist returns for protected routes.
        self.users.save({"id": user.id, "auth_user_id": user.id, "email": email})

        return SignUpResult(
            user_id=user.id,
            email=email,
            email_confirmation_required=session is None,
            access_token=getattr(session, "access_token", None),
            refresh_token=getattr(session, "refresh_token", None),
        )

    def authenticate(self, email: str, password: str) -> Session:
        try:
            res = self.auth.verify(email, password)
        except AuthApiError:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

        session = getattr(res, "session", None)
        user = getattr(res, "user", None)
        if session is None or user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

        return Session(
            user_id=user.id,
            email=email,
            access_token=session.access_token,
            refresh_token=session.refresh_token,
            expires_at=getattr(session, "expires_at", None),
        )

    def sign_out(self, access_token: str) -> None:
        try:
            self.auth.sign_out(access_token)
        except AuthApiError:
            # Token already invalid/expired: treat sign-out as idempotent.
            pass
