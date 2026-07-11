from fastapi import APIRouter, Depends
from app.core.security import current_therapist
from app.schemas.dto import ReviewIn
from app.services.review_service import ReviewService

router = APIRouter(prefix="/reviews", tags=["reviews"])
svc = ReviewService()


@router.post("")
def submit_review(body: ReviewIn, therapist: str = Depends(current_therapist)):
    return svc.submit_review(body.activity_id, therapist, body.text)
