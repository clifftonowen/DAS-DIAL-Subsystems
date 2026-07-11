"""AuthGateway - wraps Supabase Auth (external service)."""
from app.core.supabase_client import get_supabase


class AuthGateway:
    def verify(self, email: str, password: str):
        return get_supabase().auth.sign_in_with_password(
            {"email": email, "password": password}
        )

    def create_user(self, email: str, password: str):
        return get_supabase().auth.sign_up({"email": email, "password": password})
