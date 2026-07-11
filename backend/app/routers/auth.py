from fastapi import APIRouter
from app.schemas.dto import Credentials
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])
svc = AuthService()


@router.post("/signup")
def sign_up(body: Credentials):
    return svc.register(body.email, body.password)


@router.post("/login")
def log_in(body: Credentials):
    return svc.authenticate(body.email, body.password)
