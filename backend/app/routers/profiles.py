from fastapi import APIRouter, Depends, HTTPException
from app.core.security import current_therapist
from app.repositories.base import StorageError
from app.services.profiling_service import NoScoresError, ProfilingService
from app.services.activity_generation_service import ActivityGenerationService

router = APIRouter(prefix="/profiles", tags=["profiles"])
svc = ProfilingService()
activity_svc = ActivityGenerationService()


@router.post("/{learner_id}")
def generate_profile(learner_id: str, _: str = Depends(current_therapist)):
    """ProfileController.generateProfile() — UC2's entry point.

    Promotes the learner's most recent sitting to their current marks. See ProfilingService:
    there is no algorithm behind this any more, because the profile IS the four DIAL marks.

    Two failures, because they are two different problems for the therapist:
      409  the learner has no scores on record  -> upload an assessment (UC1)
      500  the database is unreachable          -> nothing they can do; retry later

    409 rather than 404: the learner exists and the request was well-formed — the resource is
    simply not in a state that can satisfy it yet. The profile page keys its inline upload
    prompt off exactly this status, so collapsing it into 404 (which also means "no such
    learner") would leave the UI unable to tell the two apart.
    """
    try:
        return svc.generate_profile(learner_id)
    except NoScoresError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except StorageError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{learner_id}/activities")
def list_learner_activities(learner_id: str, _: str = Depends(current_therapist)):
    """Activities generated for this learner, newest first.

    Keyed on the learner now that `learning_activities.profiled` has become `learner_id` — there
    is no profile row to hang them off.
    """
    return activity_svc.list_activities(learner_id)
