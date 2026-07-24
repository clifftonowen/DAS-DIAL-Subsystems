from app.repositories.base import BaseRepository

class LearnerRepository(BaseRepository):
    table = "learners"

    def save(self, learner: dict) -> dict:
        return self.db.upsert(learner).execute().data

    def find_by_id(self, learner_id: str) -> dict | None:
        rows = self.db.select("*").eq("id", learner_id).execute().data
        return rows[0] if rows else None

    def list_all(self) -> list[dict]:
        return self.db.select("*").execute().data


