"""ShareService - render an activity to PDF and email it to a therapist."""
from app.repositories.activity_repository import ActivityRepository
from app.gateways.email_gateway import EmailGateway


class ShareService:
    def __init__(self):
        self.activities = ActivityRepository()
        self.email = EmailGateway()

    def share(self, activity_id: str, recipient_email: str) -> dict:
        activity = self.activities.find_by_id(activity_id)
        pdf = self._render_pdf(activity)
        sent = self.email.send(pdf, recipient_email)
        return {"sent": sent, "activity_id": activity_id}

    def _render_pdf(self, activity) -> bytes:
        # TODO: render activity dict to a PDF
        return b"%PDF-stub"
