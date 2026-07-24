"""AssessmentService - parse an uploaded student sample into an AssessmentRecord."""
from app.repositories.assessment_repository import AssessmentRepository


class AssessmentService:
    def __init__(self):
        self.assessments = AssessmentRepository()

    def parse_and_store(self, learner_id: str, file) -> dict:
        # TODO: OCR / parse the writing sample into task_results
        record = {"learner_id": learner_id, "task_results": {}, "risk_score": 0.0}
        self.assessments.save(record)
        return record

    def list_assessments(self, learner_id: str) -> list[dict]:
        return self.assessments.find_by_learner(learner_id)
