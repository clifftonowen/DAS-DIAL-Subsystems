"""Shared Supabase clients. Repositories depend on `get_supabase`.

The `supabase` import is lazy so the app boots for local development /
tests before the package or secrets are configured.

There are deliberately TWO clients — see `get_auth_supabase` for why they must
not be the same object.
"""
from functools import lru_cache
from app.core.config import settings


def _create():
    if not settings.supabase_url:
        raise RuntimeError("SUPABASE_URL not set. Copy .env.example to .env.")
    from supabase import create_client
    return create_client(settings.supabase_url, settings.supabase_key)


@lru_cache
def get_supabase():
    """The DATA-plane client: every repository reaches Postgres through this.

    It must keep its service-role Authorization header for the whole process, so
    nothing may perform a sign-in on it. Use `get_auth_supabase` for that.
    """
    return _create()


@lru_cache
def get_auth_supabase():
    """The AUTH-plane client, used only by AuthGateway.

    Why this is separate: `sign_in_with_password` / `sign_up` emit a SIGNED_IN
    event, and supabase-py reacts by throwing away the client's PostgREST
    instance and REPLACING its Authorization header with that user's access token
    (see supabase/_sync/client.py::_listen_to_auth_events). On a single shared
    client that silently demotes every later database call from service-role to
    "whoever logged in most recently" — which RLS then rejects (error 42501 on the
    `users` upsert), and which in a multi-user process means one therapist's login
    changes the privileges another therapist's request runs under.

    Keeping the two apart means a login can only ever affect the auth client.
    """
    return _create()
