"""UNIT — UC7 Share Learning Activity.

Each test carries its ID from the UC7 test plan so the table and the suite can
be read side by side.

    UT-7.1  / 7.2    ActivityRepository.find_by_id()
    UT-7.3  / 7.4    ActivityPdfRenderer.render()
    UT-7.5  / 7.6    EmailGateway.send()
    UT-7.7  – 7.9    ShareService.share()
    UT-7.10 – 7.13   ShareController (POST /share)


Every collaborator is mocked: the repository, the renderer and the gateway are
stand-ins, so nothing touches Supabase, a filesystem or an SMTP server.
"""
from unittest.mock import Mock, patch

import pytest

from app.gateways.email_gateway import EmailGateway, EmailSendError
from app.services.pdf_renderer import ActivityPdfRenderer, PdfRenderError
from app.services.share_service import ExportError, InvalidEmailError, ShareService

pytestmark = pytest.mark.unit

ACTIVITY = {
    "id": "act-1",
    "content": {"text": "# Rhyme sort\n**Objective:** hear rhyme.\n- Sort the cards"},
    "literacy_objective": "Phonological awareness",
    "level": "A2",
    "status": "GENERATED",
}


def make_service(activity=ACTIVITY):
    svc = ShareService()
    svc.activities = Mock()
    svc.activities.find_by_id.return_value = activity
    svc.renderer = Mock()
    svc.renderer.render.return_value = b"%just some pdf"
    svc.email = Mock()
    svc.email.send.return_value = True
    return svc


def smtp_settings(cfg):
    cfg.email_enabled = True
    cfg.smtp_host = "smtp.example.com"
    cfg.smtp_port = 587
    cfg.smtp_use_tls = True
    cfg.smtp_user = ""
    cfg.smtp_password = ""
    cfg.smtp_from = ""



# UT: 7.1-7.2 
# ActivityRepository.find_by_id()
# --------------------------------------------------------------------------- #
def test_ut_7_1_find_by_id_returns_the_activity_when_it_exists(fake_supabase):
    #returns the LearningActivity
    from app.repositories.activity_repository import ActivityRepository

    fake_supabase(seed={"learning_activities": [ACTIVITY]})

    assert ActivityRepository().find_by_id("act-1")["id"] == "act-1"


def test_ut_7_2_find_by_id_returns_none_when_there_is_no_match(fake_supabase):
    from app.repositories.activity_repository import ActivityRepository

    fake_supabase(seed={"learning_activities": []})

    assert ActivityRepository().find_by_id("nope") is None


# UT: 7.3-7.4 
# ActivityPdfRenderer().render()
# --------------------------------------------------------------------------- #
def test_ut_7_3_renderer_produces_a_pdf_containing_the_activity():
    pdf = ActivityPdfRenderer().render(ACTIVITY)

    assert pdf.startswith(b"%PDF")
    fitz = pytest.importorskip("fitz")
    text = fitz.open(stream=pdf, filetype="pdf")[0].get_text()
    assert "Phonological awareness" in text   
    assert "Sort the cards" in text          


def test_ut_7_4_renderer_raises_when_there_is_nothing_to_render():
    with pytest.raises(PdfRenderError):
        ActivityPdfRenderer().render({"id": "act-1", "content": {"text": ""}})



# UT: 7.5-7.6 
# EmailGateway.send()
# --------------------------------------------------------------------------- #
def test_ut_7_5_gateway_returns_true_when_the_server_accepts():
    
    with patch("app.gateways.email_gateway.settings") as cfg:
        smtp_settings(cfg)
        with patch("smtplib.SMTP") as smtp:
            server = smtp.return_value.__enter__.return_value
            assert EmailGateway().send(b"%just some pdf", "parent@example.com") is True
            message = server.send_message.call_args.args[0]
            assert message["To"] == "parent@example.com"
            assert [a.get_content_type() for a in message.iter_attachments()] == ["application/pdf"]


def test_ut_7_6_gateway_raises_when_the_server_refuses():
    with patch("app.gateways.email_gateway.settings") as cfg:
        smtp_settings(cfg)
        with patch("smtplib.SMTP", side_effect=OSError("Connection refused")):
            with pytest.raises(EmailSendError):
                EmailGateway().send(b"%just some pdf", "parent@example.com")




# UT: 7.7-7.9 
# ShareService.share()
# --------------------------------------------------------------------------- #
def test_ut_7_7_share_renders_the_activity_and_sends_it():
    svc = make_service()

    result = svc.share("act-1", "parent@example.com")

    svc.activities.find_by_id.assert_called_once_with("act-1")
    svc.renderer.render.assert_called_once_with(ACTIVITY)
    pdf, recipient = svc.email.send.call_args.args
    assert pdf == b"%just some pdf"
    assert recipient == "parent@example.com"
    assert result["sent"] is True


def test_ut_7_8_render_failure_aborts_the_share_without_emailing():
    svc = make_service()
    svc.renderer.render.side_effect = PdfRenderError("Activity has no content to export")

    with pytest.raises(ExportError):
        svc.share("act-1", "parent@example.com")

    svc.email.send.assert_not_called()


def test_ut_7_8b_missing_activity_aborts_the_share_without_emailing():
    svc = make_service(activity=None)

    with pytest.raises(ExportError):
        svc.share("ghost", "parent@example.com")

    svc.email.send.assert_not_called()


def test_ut_7_9_gateway_failure_propagates_for_retry():
    svc = make_service()
    svc.email.send.side_effect = EmailSendError("Email server refused")

    with pytest.raises(EmailSendError):
        svc.share("act-1", "parent@example.com")




# UT: 7.10-7.13  
# ShareController 
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("test_id, side_effect, expected_status", [
    ("UT-7.10", None, 200),
    ("UT-7.11", InvalidEmailError("Invalid email address, please re-enter"), 400),
    ("UT-7.12", ExportError("Could not export activity as PDF"), 422),
    ("UT-7.13", EmailSendError("Could not send activity"), 502),
])
def test_controller_maps_each_outcome_to_its_status_code(
    client, auth_ok, monkeypatch, test_id, side_effect, expected_status
):
    """UT-7.10 success, 7.11 invalid email, 7.12 export error, 7.13 send error
    The Dashboard branches on these codes: 400 means re-enter the address, 422
    means abort, 502 means offer a retry.
    """
    from app.routers import share as share_router

    stub = Mock()
    if side_effect:
        stub.side_effect = side_effect
    else:
        stub.return_value = {"sent": True, "activity_id": "act-1"}
    monkeypatch.setattr(share_router.svc, "share", stub)

    response = client.post("/share", json={
        "activity_id": "act-1",
        "recipient_email": "parent@example.com",
    })

    assert response.status_code == expected_status







