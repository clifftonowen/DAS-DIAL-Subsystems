"""Auth dependency: verify the Supabase JWT on protected routes.

Wire real verification with the project's jwt secret. Kept minimal so the
skeleton boots without secrets during early development.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

bearer = HTTPBearer(auto_error=False)


async def current_therapist(cred: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    """Returns the authenticated therapist's id. TODO: verify JWT signature."""
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    # TODO: decode + verify cred.credentials against settings.supabase_jwt_secret
    return "therapist-dev"  # placeholder identity for local dev
