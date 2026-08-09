"""AssessmentService - parse an uploaded assessment report into a preview,
then persist it as an AssessmentRecord once the therapist confirms."""
from app.repositories.assessment_repository import AssessmentRepository
from app.entities.models import AssessmentRecord
from app.ingestion.assessment_parser import parse_assessment_report, validate_format
from app.schemas.dto import AssessmentPreview, AssessmentConfirmRequest


class StorageError(Exception):
    pass


class AssessmentService:
    def __init__(self):
        self.assessments = AssessmentRepository()

    def parse_preview(self, learner_id: str, file) -> AssessmentPreview:
        """Validate + parse only. Nothing is saved yet — this is what the
        card view on the frontend renders before the therapist confirms."""
        validate_format(file)                               # -> InvalidFormatError
        return parse_assessment_report(file, learner_id)     # -> ParseError

    def confirm_and_save(self, payload: AssessmentConfirmRequest) -> dict:
        """Called after the therapist reviews the card and confirms."""
        record = AssessmentRecord(
            learner_id=payload.learner_id,
            assessment_date=payload.assessment_date,
            risk_score=payload.risk_score,
            task_results=payload.task_results,
            strengths=payload.strengths,
            weaknesses=payload.weaknesses,
            confidence_score=payload.confidence_score,
        )
        try:
            saved = self.assessments.save(record.model_dump(mode="json"))
        except Exception as e:
            raise StorageError(str(e))
        return {"status": "success", "message": "Data saved successfully", "record": saved}
    def list_assessments(self, learner_id: str) -> list[dict]:
        return self.assessments.find_by_learner(learner_id)
