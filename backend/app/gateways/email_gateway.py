"""EmailGateway — sends generated activities as a PDF attachment.

The "Email Server" secondary actor. Talks SMTP, which keeps the provider
swappable: Gmail, Mailtrap, Resend and SendGrid all expose an SMTP endpoint, so
switching providers is a .env change rather than a code change.

Raises EmailSendError when the server rejects the message.
"""
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

log = logging.getLogger(__name__)


class EmailSendError(Exception):
    "The email server returned a negative response."

SUBJECT = "A learning activity has been shared with you"

BODY = (
    "Hello,\n\n"
    "A learning activity has been shared with you from DAS D.I.A.L. "
    "The activity is attached as a PDF.\n\n"
    "This is an automated message — please do not reply."
)


class EmailGateway:
    def send(self, pdf_bytes: bytes, recipient_email: str) -> bool:
        """Deliver the PDF to recipient_email. True on success, else EmailSendError."""
        message = self._build_message(pdf_bytes, recipient_email)

        if not settings.email_enabled:
            print(f"[email] would send {len(pdf_bytes)} bytes to {recipient_email}")
            return True


        if not settings.smtp_host:
            raise EmailSendError("Email is enabled but SMTP_HOST is not configured")

        try:
            self._deliver(message)
        except smtplib.SMTPAuthenticationError as exc:
            raise EmailSendError("Email server rejected our credentials") from exc
        except smtplib.SMTPRecipientsRefused as exc:
            raise EmailSendError(f"Email server deemed {recipient_email} as invalid") from exc
        except (smtplib.SMTPException, OSError) as exc:
            # OSError covers the host being unreachable or the TLS handshake failing.
            raise EmailSendError(f"Could not reach the email server: {exc}") from exc

        print(f"[email] sent {len(pdf_bytes)} bytes to {recipient_email}")
        return True


    def _build_message(self, pdf_bytes: bytes, recipient_email: str) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = SUBJECT
        message["From"] = settings.smtp_from or settings.smtp_user or "no-reply@das-dial.local"
        message["To"] = recipient_email
        message.set_content(BODY)
        message.add_attachment(pdf_bytes, maintype="application", subtype="pdf",
                               filename="learning-activity.pdf")
        return message

    def _deliver(self, message: EmailMessage) -> None:
        """Port 465 is implicit TLS (SMTP_SSL); 587 upgrades with STARTTLS."""
        if settings.smtp_port == 465:
            with smtplib.SMTP_SSL(settings.smtp_host, 465, timeout=20) as server:
                self._login_and_send(server, message)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
                if settings.smtp_use_tls:
                    server.starttls()
                self._login_and_send(server, message)

    def _login_and_send(self, server: smtplib.SMTP, message: EmailMessage) -> None:
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(message)