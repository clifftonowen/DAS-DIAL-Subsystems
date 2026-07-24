from app.repositories.learner_repository import LearnerRepository


class LearnerService:
    def __init__(self):
        self.learners = LearnerRepository()

    def list_learners(self) -> list[dict]:
        return self.learners.list_all()

    def get_learner(self, learner_id: str) -> dict | None:
        from fastapi import HTTPException
        learner = self.learners.find_by_id(learner_id)
        if not learner:
            raise HTTPException(status_code=404, detail="Learner not found")
        return learner
