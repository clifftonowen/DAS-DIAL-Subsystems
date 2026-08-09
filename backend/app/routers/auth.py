"""AuthController: email + password signup / login / logout via Supabase.

The only layer that knows HTTP. AuthService raises the domain errors the UC6 and
UC8 diagrams name - `AuthError`, `SignUpError` - and this translates them into
status codes.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.schemas.dto import Credentials, Session, SignUpResult
from app.services.auth_service import AuthError, AuthService, SignUpError

router = APIRouter(prefix="/auth", tags=["auth"])
svc = AuthService()
bearer = HTTPBearer(auto_error=True)


@router.post("/signup", response_model=SignUpResult)
def sign_up(body: Credentials):
    """UC8 `signUp(email, password)`."""
    try:
        return svc.register(body.email, body.password)
    except SignUpError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.post("/login", response_model=Session)
def log_in(body: Credentials):
    """UC6 `logIn(email, password)`."""
    try:
        return svc.authenticate(body.email, body.password)
    except AuthError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def log_out(cred: HTTPAuthorizationCredentials = Depends(bearer)):
    svc.sign_out(cred.credentials)
