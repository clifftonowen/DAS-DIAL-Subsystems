from fastapi import APIRouter, Depends
from app.core.security import current_therapist
from app.schemas.dto import ShareIn
from app.services.share_service import ShareService

router = APIRouter(prefix="/share", tags=["share"])
svc = ShareService()


@router.post("")
def share_activity(body: ShareIn, _: str = Depends(current_therapist)):
    return svc.share(body.activity_id, body.recipient_email)
