"""ShareService - render an activity to PDF and email it to a therapist.

This is the flow of error handling before proceeding with sending 

1. validate email address
2. validate activity id and render the PDF
3. hand the PDF and email address to gateway 

"""

import re 

from app.repositories.activity_repository import ActivityRepository
from app.gateways.email_gateway import EmailGateway, EmailSendError
from app.services.pdf_renderer import ActivityPdfRenderer, PdfRenderError


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
 
class InvalidEmailError(Exception):
    "The recipient's email address is invalid."
 
 
class ExportError(Exception):
    "The activity could not be exported as a PDF."
 

class ShareService:
    def __init__(self):
        self.activities = ActivityRepository()
        self.email = EmailGateway()
        self.renderer = ActivityPdfRenderer()

    def share(self, activity_id: str, recipient_email: str) -> dict:
        recipient = self._validate_email(recipient_email)
        pdf = self._export(activity_id)
        self.email.send(pdf, recipient)
 
        return {
            "sent": True,
            "activity_id": activity_id,
            "recipient_email": recipient,
            "pdf_bytes": len(pdf),
        }
 
    def _validate_email(self, recipient_email):
        recipient = (recipient_email or "").strip()
        if not EMAIL_RE.match(recipient):
            raise InvalidEmailError("Invalid email address, please re-enter")
        return recipient
 
    def _export(self, activity_id: str) -> bytes:
        try:
            activity = self.activities.find_by_id(activity_id)
        except Exception as exc:  
            raise ExportError(f"Could not load the activity: {exc}") from exc
 
        if not activity:
            raise ExportError("Activity not found")
 
        try:
            pdf = self.renderer.render(activity)
        except PdfRenderError as exc:
            raise ExportError(str(exc)) from exc
 
        return pdf

