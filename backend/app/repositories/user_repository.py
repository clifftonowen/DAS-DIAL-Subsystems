from app.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    table = "users"

    def save(self, therapist: dict) -> dict:
        return self.db.upsert(therapist).execute().data

    def find_by_email(self, email: str) -> dict | None:
        rows = self.db.select("*").eq("email", email).execute().data
        return rows[0] if rows else None
