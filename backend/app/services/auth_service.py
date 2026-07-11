"""AuthService - register / authenticate therapists."""
from app.gateways.auth_gateway import AuthGateway
from app.repositories.user_repository import UserRepository


class AuthService:
    def __init__(self):
        self.users = UserRepository()
        self.auth = AuthGateway()

    def register(self, email: str, password: str) -> dict:
        res = self.auth.create_user(email, password)
        self.users.save({"email": email})
        return {"email": email, "auth": bool(res)}

    def authenticate(self, email: str, password: str) -> dict:
        res = self.auth.verify(email, password)
        return {"session": bool(res), "email": email}
