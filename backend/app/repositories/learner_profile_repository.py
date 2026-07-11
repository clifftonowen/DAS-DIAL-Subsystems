from app.repositories.base import BaseRepository


class LearnerProfileRepository(BaseRepository):
    table = "learner_profiles"

    def save(self, profile: dict) -> dict:
        return self.db.upsert(profile).execute().data

    def find_by_learner(self, learner_id: str) -> dict | None:
        rows = self.db.select("*").eq("learner_id", learner_id).execute().data
        return rows[0] if rows else None
