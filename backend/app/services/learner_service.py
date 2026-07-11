from app.repositories.learner_repository import LearnerRepository


class LearnerService:
    def __init__(self):
        self.learners = LearnerRepository()

    def list_learners(self) -> list[dict]:
        return self.learners.list_all()
