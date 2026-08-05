from fastapi import APIRouter, Depends, HTTPException
from app.core.security import current_therapist
from app.repositories.base import StorageError
from app.services.profiling_service import (
    EmptyDataError, ProfileGenerationError, ProfilingService)
from app.services.activity_generation_service import ActivityGenerationService

router = APIRouter(prefix="/profiles", tags=["profiles"])
svc = ProfilingService()
activity_svc = ActivityGenerationService()


@router.post("/{learner_id}")
def generate_profile(learner_id: str, _: str = Depends(current_therapist)):
    """ProfileController.generateProfile() — UC2's entry point (UT-2.1, UT-2.2).

    Each failure gets its own status because each is a different problem for the therapist:
      404  the learner has no assessment data       -> upload an assessment
      422  the data yielded no usable patterns      -> the records need looking at
      500  the database is unreachable              -> nothing they can do; retry later
    Collapsing these into one code would leave the UI unable to say which happened.
    """
    try:
        return svc.generate_profile(learner_id)
    except EmptyDataError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ProfileGenerationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except StorageError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{profile_id}/activities")
def list_profile_activities(profile_id: str, _: str = Depends(current_therapist)):
    return activity_svc.list_activities(profile_id)
