from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from app.core.security import current_therapist
from app.services.assessment_service import AssessmentService, StorageError
from app.schemas.dto import (
    AssessmentConfirmRequest, AssessmentMetric, AssessmentPreview, assessment_metrics,
)
from app.ingestion.assessment_parser import InvalidFormatError, ParseError

router = APIRouter(prefix="/assessments", tags=["assessments"])
svc = AssessmentService()


@router.get("/metrics", response_model=list[AssessmentMetric])
def list_metrics(_: str = Depends(current_therapist)):
    """The four DIAL marks the upload form collects, and the ceiling each one allows.

    Served so the form and the confirm validator cannot disagree: both read
    NORMALISATION_CEILINGS, one over HTTP and one directly. The frontend used to hardcode these
    numbers, which meant a rubric change had to be made in two places or the form would accept
    marks the API rejects.
    """
    return assessment_metrics()


@router.get("/semesters", response_model=list[str])
def list_semesters(_: str = Depends(current_therapist)):
    """Semesters the upload form offers, newest first — those on record plus the next two.

    The lookahead is the point: the list is built from stored sittings, so without it the first
    upload of a newly-started semester would have nothing to select. Never an error — an empty
    table is a legitimate answer for a fresh project, and the form falls back to letting the
    therapist type one.
    """
    return svc.list_semesters()


@router.post("/preview", response_model=AssessmentPreview)
def preview_assessment(learner_id: str = Form(...), file: UploadFile = File(...), _: str = Depends(current_therapist)):
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