from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.security import current_therapist
from app.schemas.dto import LearnerOverview, LearnerPage, SittingPoint
from app.services.learner_overview_service import (
    LearnerNotFoundError,
    LearnerOverviewService,
)
from app.services.learner_service import LearnerService
from app.services.profiling_service import ProfilingService
from app.services.assessment_service import AssessmentService

router = APIRouter(prefix="/learners", tags=["learners"])
svc = LearnerService()
profiling_svc = ProfilingService()
assessment_svc = AssessmentService()
overview_svc = LearnerOverviewService()


@router.get("", response_model=LearnerPage)
def list_learners(
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=100),
    q: str | None = Query(None, description="free text over pseudonym, student id and band"),
    caseload: bool = Query(True, description="restrict to the therapist's own learners"),
    _: str = Depends(current_therapist),
):
    """One page of learners (UC2).

    PAGED, not a bare array. `learners` holds the anonymised research cohort alongside the
    caseload — thousands of rows — and PostgREST caps a select at 1,000 and truncates WITHOUT
    erroring, so an unpaged endpoint would serve a fraction of the table and look healthy doing
    it. Search runs server-side for the same reason.

    `caseload` defaults true so the Learners tab opens on the therapist's own learners.
    """
    return svc.list_learners(page=page, per_page=per_page, query=q, caseload_only=caseload)

@router.get("/{learner_id}")
def get_learner(learner_id: str, _: str = Depends(current_therapist)):
    return svc.get_learner(learner_id)

@router.get("/{learner_id}/sittings", response_model=list[SittingPoint])
def list_learner_sittings(learner_id: str, _: str = Depends(current_therapist)):
    """Every score on record for this learner, oldest first (UC2).

    Replaced `/profiles`, which served the seven derived cognitive dimensions. The profile page
    gets this same list inside its `/overview` call, so this exists for callers that want the
    history alone.
    """
    return profiling_svc.list_sittings(learner_id)

@router.get("/{learner_id}/assessments")
def list_learner_assessments(learner_id: str, _: str = Depends(current_therapist)):
    return assessment_svc.list_assessments(learner_id)


@router.get("/{learner_id}/overview", response_model=LearnerOverview)
def get_learner_overview(learner_id: str, _: str = Depends(current_therapist)):
    """The learner across both Subsystem 2 tables — profile plus DIAL marks (UC2).

    One call rather than two: LearnerDetailPage renders the cognitive profile and the DIAL radar
    chart on the same screen, and they come from different tables joined on a column the frontend
    should not have to know about.

    A missing profile or a missing cohort link is a 200 with nulls, not an error — most of the
    caseload has one, neither, or both, and the page has an empty state for each. Only an unknown
    learner is a 404.
    """
    try:
        return overview_svc.get_overview(learner_id)
    except LearnerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
