"""Single shared Supabase client. Repositories depend on this.

The `supabase` import is lazy so the app boots for local development /
tests before the package or secrets are configured.
"""
from functools import lru_cache
from app.core.config import settings


@lru_cache
def get_supabase():
    if not settings.supabase_url:
        raise RuntimeError("SUPABASE_URL not set. Copy .env.example to .env.")
    from supabase import create_client
    return create_client(settings.supabase_url, settings.supabase_key)
