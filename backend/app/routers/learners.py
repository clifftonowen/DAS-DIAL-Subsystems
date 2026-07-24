from fastapi import APIRouter, Depends
from app.core.security import current_therapist
from app.services.learner_service import LearnerService
from app.services.profiling_service import ProfilingService
from app.services.assessment_service import AssessmentService

router = APIRouter(prefix="/learners", tags=["learners"])
svc = LearnerService()
profiling_svc = ProfilingService()
assessment_svc = AssessmentService()


@router.get("")
def list_learners(_: str = Depends(current_therapist)):
    return svc.list_learners()

@router.get("/{learner_id}")
def get_learner(learner_id: str, _: str = Depends(current_therapist)):
    return svc.get_learner(learner_id)

@router.get("/{learner_id}/profiles")
def list_learner_profiles(learner_id: str, _: str = Depends(current_therapist)):
    return profiling_svc.list_profiles(learner_id)

@router.get("/{learner_id}/assessments")
def list_learner_assessments(learner_id: str, _: str = Depends(current_therapist)):
    return assessment_svc.list_assessments(learner_id)
