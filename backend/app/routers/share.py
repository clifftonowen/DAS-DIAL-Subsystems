from fastapi import APIRouter, Depends, HTTPException, status
from app.core.security import current_therapist
from app.schemas.dto import ShareIn
from app.services.share_service import ShareService, ExportError, InvalidEmailError
from app.gateways.email_gateway import EmailSendError

router = APIRouter(prefix="/share", tags=["share"])
svc = ShareService()


@router.post("")
def share_activity(body: ShareIn, _: str = Depends(current_therapist)):
    try: 
        return svc.share(body.activity_id, body.recipient_email)
    except InvalidEmailError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except ExportError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except EmailSendError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))

