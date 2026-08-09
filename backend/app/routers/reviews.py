"""
ReviewController — the /reviews endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status 
from app.core.security import current_therapist
from app.schemas.dto import ReviewIn
from app.services.review_service import ReviewService, StorageError

router = APIRouter(prefix="/reviews", tags=["reviews"])
svc = ReviewService()


@router.post("")
def submit_review(body: ReviewIn, therapist: str = Depends(current_therapist)):
    try:
        return svc.submit_review(body.activity_id, therapist, body.text, body.status)
    except StorageError as exc:
        # 502: the API did its job, the database refused the write.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))

@router.get("/{activity_id}")
def list_reviews(activity_id: str, _: str = Depends(current_therapist)):
    return svc.list_reviews(activity_id)
