from fastapi import APIRouter, Depends
from app.core.security import current_therapist
from app.services.learner_service import LearnerService

router = APIRouter(prefix="/learners", tags=["learners"])
svc = LearnerService()


@router.get("")
def list_learners(_: str = Depends(current_therapist)):
    return svc.list_learners()
