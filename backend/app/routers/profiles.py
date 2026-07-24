from fastapi import APIRouter, Depends
from app.core.security import current_therapist
from app.services.profiling_service import ProfilingService
from app.services.activity_generation_service import ActivityGenerationService

router = APIRouter(prefix="/profiles", tags=["profiles"])
svc = ProfilingService()
activity_svc = ActivityGenerationService()


@router.post("/{learner_id}")
def generate_profile(learner_id: str, _: str = Depends(current_therapist)):
    return svc.generate_profile(learner_id)

@router.get("/{profile_id}/activities")
def list_profile_activities(profile_id: str, _: str = Depends(current_therapist)):
    return activity_svc.list_activities(profile_id)
