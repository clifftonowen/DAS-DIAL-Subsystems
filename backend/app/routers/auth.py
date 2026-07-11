"""Auth controller: email + password signup / login / logout via Supabase."""
from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.schemas.dto import Credentials, SignUpResult, Session
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])
svc = AuthService()
bearer = HTTPBearer(auto_error=True)


@router.post("/signup", response_model=SignUpResult)
def sign_up(body: Credentials):
    return svc.register(body.email, body.password)


@router.post("/login", response_model=Session)
def log_in(body: Credentials):
    return svc.authenticate(body.email, body.password)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def log_out(cred: HTTPAuthorizationCredentials = Depends(bearer)):
    svc.sign_out(cred.credentials)
