from app.repositories.base import BaseRepository


class AssessmentRepository(BaseRepository):
    table = "assessment_records"

    def save(self, record: dict) -> dict:
        return self.db.upsert(record).execute().data

    def find_by_learner(self, learner_id: str) -> list[dict]:
        return self.db.select("*").eq("learner_id", learner_id).execute().data
