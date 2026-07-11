from fastapi import APIRouter, Depends
from app.core.security import current_therapist
from app.services.profiling_service import ProfilingService

router = APIRouter(prefix="/profiles", tags=["profiles"])
svc = ProfilingService()


@router.post("/{learner_id}")
def generate_profile(learner_id: str, _: str = Depends(current_therapist)):
    return svc.generate_profile(learner_id)
