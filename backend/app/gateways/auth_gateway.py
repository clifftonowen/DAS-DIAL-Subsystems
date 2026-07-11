"""AuthGateway - wraps Supabase Auth (external service).

Email + password auth. Each method returns the raw Supabase AuthResponse so
the service layer decides how to shape the API response. Supabase raises
`AuthApiError` on bad credentials / duplicate email; the service translates
those into HTTP errors.
"""
from app.core.supabase_client import get_supabase


class AuthGateway:
    def create_user(self, email: str, password: str):
        """Sign up a therapist with email + password.

        If the project has email confirmation on, the returned response has a
        user but no session until the emailed link is clicked.
        """
        return get_supabase().auth.sign_up({"email": email, "password": password})

    def verify(self, email: str, password: str):
        """Exchange email + password for a Supabase session (access token)."""
        return get_supabase().auth.sign_in_with_password(
            {"email": email, "password": password}
        )

    def sign_out(self, access_token: str):
        """Revoke the session behind the given access token."""
        return get_supabase().auth.admin.sign_out(access_token)
