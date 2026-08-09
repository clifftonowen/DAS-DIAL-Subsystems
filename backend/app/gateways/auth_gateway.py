"""AuthGateway - wraps Supabase Auth (the external Authentication Service).

Sequence-diagram contract (UC6 Log In, UC8 Sign Up): this is the last lifeline we
own before the Authentication Service actor, and it always answers AuthService
with an `AuthResponse` - `ok=True` carrying the session, or `ok=False` carrying an
error string. No gotrue exception escapes this layer, which is what lets
AuthService branch on a value instead of on an exception.
"""
from typing import Optional

from pydantic import BaseModel

from app.core.supabase_client import get_auth_supabase

try:  # gotrue ships with supabase; guard the import so the app still boots
    # Catch gotrue's BASE error, not AuthApiError. AuthApiError covers only HTTP
    # error responses; sibling subclasses like AuthWeakPasswordError and
    # AuthInvalidCredentialsError descend from CustomAuthError instead, so
    # catching AuthApiError let a short password escape as an unhandled 500.
    from gotrue.errors import AuthError as GotrueAuthError
except Exception:  # pragma: no cover - fallback if the package layout changes
    GotrueAuthError = Exception


class AuthResponse(BaseModel):
    """What AuthGateway hands back to AuthService.

    `ok=True` with `access_token=None` is the email-confirmation-pending case:
    Supabase created the user but issued no session until the emailed link is
    clicked.
    """
    ok: bool
    user_id: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_at: Optional[int] = None
    error: Optional[str] = None


class AuthGateway:
    def create_user(self, email: str, password: str) -> AuthResponse:
        """UC8 `createUser`: create the auth account. Duplicate email -> ok=False."""
        try:
            res = get_auth_supabase().auth.sign_up({"email": email, "password": password})
        except GotrueAuthError as e:
            return AuthResponse(ok=False, error=str(e))
        return self._to_response(res)

    def verify(self, email: str, password: str) -> AuthResponse:
        """UC6 `verify`: exchange email + password for a session.

        Rejected credentials come back as `ok=False`, not as an exception.
        """
        try:
            res = get_auth_supabase().auth.sign_in_with_password(
                {"email": email, "password": password}
            )
        except GotrueAuthError as e:
            return AuthResponse(ok=False, error=str(e))
        return self._to_response(res)

    def sign_out(self, access_token: str) -> AuthResponse:
        """Revoke the session behind the given access token.

        An already-expired token comes back as `ok=False` rather than raising, so
        gotrue errors stay inside this layer like they do for the other two calls.
        """
        try:
            get_auth_supabase().auth.admin.sign_out(access_token)
        except GotrueAuthError as e:
            return AuthResponse(ok=False, error=str(e))
        return AuthResponse(ok=True)

    @staticmethod
    def _to_response(res) -> AuthResponse:
        """Flatten Supabase's own AuthResponse into ours.

        Read through `getattr` so a partial response - a user with no session,
        which is what email confirmation produces - doesn't raise.
        """
        user = getattr(res, "user", None)
        if user is None:
            return AuthResponse(ok=False, error="Authentication service returned no user")
        session = getattr(res, "session", None)
        return AuthResponse(
            ok=True,
            user_id=str(user.id),
            access_token=getattr(session, "access_token", None),
            refresh_token=getattr(session, "refresh_token", None),
            expires_at=getattr(session, "expires_at", None),
        )
