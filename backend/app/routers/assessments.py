from fastapi import APIRouter, Depends, UploadFile, File, Form
from app.core.security import current_therapist
from app.services.assessment_service import AssessmentService

router = APIRouter(prefix="/assessments", tags=["assessments"])
svc = AssessmentService()


@router.post("/upload")
def upload_assessment(learner_id: str = Form(...), file: UploadFile = File(...),
                      _: str = Depends(current_therapist)):
    return svc.parse_and_store(learner_id, file)
