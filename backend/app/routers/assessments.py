from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from app.core.security import current_therapist
from app.services.assessment_service import AssessmentService, StorageError
from app.schemas.dto import AssessmentPreview, AssessmentConfirmRequest
from app.ingestion.assessment_parser import InvalidFormatError, ParseError

router = APIRouter(prefix="/assessments", tags=["assessments"])
svc = AssessmentService()


@router.post("/preview", response_model=AssessmentPreview)
def preview_assessment(learner_id: str = Form(...), file: UploadFile = File(...),
                        _: str = Depends(current_therapist)):
    try:
        return svc.parse_preview(learner_id, file)
    except InvalidFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ParseError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/confirm")
def confirm_assessment(payload: AssessmentConfirmRequest, _: str = Depends(current_therapist)):
    try:
        return svc.confirm_and_save(payload)
    except StorageError as e:
        raise HTTPException(status_code=500, detail=str(e))