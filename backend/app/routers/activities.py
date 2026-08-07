from fastapi import APIRouter, Depends
from app.core.security import current_therapist
from app.schemas.dto import GenerationParams
from app.services.activity_generation_service import ActivityGenerationService

router = APIRouter(prefix="/activities", tags=["activities"])
svc = ActivityGenerationService()


@router.post("/{learner_id}/generate")
def generate_activity(learner_id: str, params: GenerationParams,
                      _: str = Depends(current_therapist)):
    return svc.generate(learner_id, params.model_dump())
