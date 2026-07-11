"""Auth dependency: verify the Supabase JWT on protected routes.

Supabase issues HS256 access tokens signed with the project JWT secret and
carrying `aud: "authenticated"`. We verify the signature and audience, then
return the auth user id (the token `sub` claim) as the therapist identity.
"""
import jwt
from jwt import PyJWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.config import settings

bearer = HTTPBearer(auto_error=False)


async def current_therapist(cred: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    """Returns the authenticated therapist's id (Supabase auth user id)."""
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    if not settings.supabase_jwt_secret:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "SUPABASE_JWT_SECRET not configured",
        )
    try:
        payload = jwt.decode(
            cred.credentials,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing subject")
    return sub  # Supabase auth user id
