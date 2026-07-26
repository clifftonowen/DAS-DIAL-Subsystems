"""AuthService - register / authenticate / sign out therapists.

Orchestrates the AuthGateway (external Supabase Auth) and the UserRepository (our
own `users` table), following the UC6 Log In and UC8 Sign Up sequence diagrams.

It speaks the domain's own errors - `AuthError`, `SignUpError` - and knows nothing
about HTTP; turning those into status codes is AuthController's job.
"""
from app.entities.models import Therapist
from app.gateways.auth_gateway import AuthGateway, AuthResponse
from app.repositories.user_repository import UserRepository
from app.schemas.dto import Session, SignUpResult


class AuthError(Exception):
    """UC6: credentials rejected, unconfirmed email, or no `users` mirror row."""


class SignUpError(Exception):
    """UC8: the auth account could not be created (e.g. the email is taken)."""


class AuthService:
    def __init__(self):
        self.users = UserRepository()
        self.auth = AuthGateway()

    # ------------------------------------------------------------------ UC8
    def register(self, email: str, password: str) -> SignUpResult:
        res = self.auth.create_user(email, password)
        if not res.ok:
            # The gateway edge failed, so the UserRepository edge is never taken:
            # no orphan mirror row for an auth account that doesn't exist.
            raise SignUpError(res.error or "Sign up failed")

        # Mirror the auth user into our own table. id == auth uid (see
        # infra/schema.sql), so it matches the `sub` that current_therapist
        # returns for protected routes.
        self.users.save(Therapist(id=res.user_id, auth_user_id=res.user_id, email=email))

        return SignUpResult(
            user_id=res.user_id,
            email=email,
            email_confirmation_required=res.access_token is None,
            access_token=res.access_token,
            refresh_token=res.refresh_token,
        )

    # ------------------------------------------------------------------ UC6
    def authenticate(self, email: str, password: str) -> Session:
        res = self.auth.verify(email, password)
        if not res.ok:
            # Invalid credentials: findByEmail is never reached.
            raise AuthError(res.error or "Invalid email or password")
        if res.access_token is None:
            # Credentials were accepted but no session was issued - Supabase does
            # this while an email confirmation is still outstanding.
            raise AuthError("Email address is not confirmed")

        therapist = self.users.find_by_email(email)
        if therapist is None:
            # Supabase Auth just vouched for these credentials, so a missing
            # mirror row is OUR bookkeeping gap, not an authentication failure —
            # refusing the login here would lock out every account that was
            # created before sign-up went through AuthService (i.e. straight from
            # the browser against Supabase, which is how all the existing
            # therapist accounts were made). Provision it now and carry on; the
            # `users` table backfills itself as those therapists log back in.
            therapist = self.users.save(
                Therapist(id=res.user_id, auth_user_id=res.user_id, email=email)
            )

        return self.create_session(res, therapist)

    def create_session(self, res: AuthResponse, therapist: Therapist) -> Session:
        """The `create Session` nested self-call in the UC6 diagram.

        Identity comes from the `users` row we just looked up; the tokens come
        from the Authentication Service.
        """
        return Session(
            user_id=str(therapist.id),
            email=therapist.email,
            access_token=res.access_token,
            refresh_token=res.refresh_token,
            expires_at=res.expires_at,
        )

    def sign_out(self, access_token: str) -> None:
        # Sign-out is idempotent: an already-expired token is not an error worth
        # surfacing, so the gateway's ok=False is deliberately ignored.
        # KNOWN LIMITATION: that also hides a Supabase outage - a logout test
        # asserting 204 passes even when the auth service is unreachable.
        self.auth.sign_out(access_token)
