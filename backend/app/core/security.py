"""Auth dependency: verify the Supabase JWT on protected routes.

Verification is delegated to Supabase's own /auth/v1/user endpoint via
get_user() rather than decoding the JWT locally. This works regardless of
whether the project signs tokens with the legacy HS256 shared secret or the
newer asymmetric JWT signing keys, so it doesn't depend on SUPABASE_JWT_SECRET
matching whatever scheme is currently active.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.supabase_client import get_supabase

bearer = HTTPBearer(auto_error=False)


async def current_therapist(cred: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    """Returns the authenticated therapist's id (Supabase auth user id)."""
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        result = get_supabase().auth.get_user(cred.credentials)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    if not result or not result.user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    return result.user.id  # Supabase auth user id
