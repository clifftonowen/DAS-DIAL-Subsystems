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


def _setting(name: str, default):
    """Read an optional setting, falling back if Settings doesn't declare it.

    config.py is owned by another part of the team, so the SMTP fields may not
    exist there. getattr keeps this gateway working against a Settings class
    that has never heard of email: every field falls back to its default and
    EMAIL_ENABLED stays False, so share still runs in dry-run mode. Declare the
    fields in config.py later and this picks them up with no change here.
    """
    return getattr(settings, name, default)


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

        if not _setting("email_enabled", False):
            log.info("[email:dry-run] %d byte PDF for %s — set EMAIL_ENABLED=true to send",
                     len(pdf_bytes), recipient_email)
            return True

        if not _setting("smtp_host", ""):
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

        log.info("[email] sent %d byte PDF to %s", len(pdf_bytes), recipient_email)
        return True


    def _build_message(self, pdf_bytes: bytes, recipient_email: str) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = SUBJECT
        message["From"] = _setting("smtp_from", "") or _setting("smtp_user", "") or "no-reply@das-dial.local"
        message["To"] = recipient_email
        message.set_content(BODY)
        message.add_attachment(pdf_bytes, maintype="application", subtype="pdf",
                               filename="learning-activity.pdf")
        return message

    def _deliver(self, message: EmailMessage) -> None:
        """Port 465 is implicit TLS (SMTP_SSL); 587 upgrades with STARTTLS."""
        if _setting("smtp_port", 587) == 465:
            with smtplib.SMTP_SSL(_setting("smtp_host", ""), 465, timeout=20) as server:
                self._login_and_send(server, message)
        else:
            with smtplib.SMTP(_setting("smtp_host", ""), _setting("smtp_port", 587), timeout=20) as server:
                if _setting("smtp_use_tls", True):
                    server.starttls()
                self._login_and_send(server, message)

    def _login_and_send(self, server: smtplib.SMTP, message: EmailMessage) -> None:
        if _setting("smtp_user", ""):
            server.login(_setting("smtp_user", ""), _setting("smtp_password", ""))
        server.send_message(message)