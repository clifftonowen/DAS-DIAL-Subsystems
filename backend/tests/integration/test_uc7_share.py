"""INTEGRATION — UC7 Share Learning Activity.

Bottom-up through the call graph. Real ShareService, real ActivityRepository,
real ActivityPdfRenderer, real EmailGateway; only the Supabase driver and the
SMTP socket are faked. Catches the wiring bugs a unit test cannot, because unit
tests mock the very seams these exercise.

    IT-7.1 – 7.3     ShareService + ActivityRepository + EmailGateway
    IT-7.4 – 7.7     the above + ShareController (POST /share)
    IT-7.8 – 7.11    the Dashboard layer — see the note at the bottom

The plan's IT-7.5 lists "Valid PDF" as an input. The controller never receives a
PDF: it takes an activityId and the PDF is produced inside the service. The test
below reads that row as "valid activityId, invalid recipientEmail".
"""
from unittest.mock import patch

import pytest

from app.gateways.email_gateway import EmailSendError
from app.services.share_service import ExportError, InvalidEmailError, ShareService

pytestmark = pytest.mark.integration

ACTIVITY = {
    "id": "act-1",
    "profiled": "prof-1",
    "content": {"text": "# Rhyme sort\n**Objective:** hear rhyme.\n- Sort the cards"},
    "literacy_objective": "Phonological awareness",
    "level": "A2",
    "status": "GENERATED",
}

# An activity whose content is empty: the renderer refuses it, which is how a
# render failure is provoked without monkeypatching the renderer itself.
UNRENDERABLE = {**ACTIVITY, "id": "act-blank", "content": {"text": ""}}


def smtp_on(cfg):
    cfg.email_enabled = True
    cfg.smtp_host = "smtp.example.com"
    cfg.smtp_port = 587
    cfg.smtp_use_tls = True
    cfg.smtp_user = ""
    cfg.smtp_password = ""
    cfg.smtp_from = ""



# IT: 7.1-7.3 
# service + repository + gateway
# --------------------------------------------------------------------------- #
def test_it_7_1_share_succeeds_through_the_real_call_graph(fake_supabase):
    #repository
    fake_supabase(seed={"learning_activities": [ACTIVITY]})
    #gateway
    with patch("app.gateways.email_gateway.settings") as cfg:
        smtp_on(cfg)
        with patch("smtplib.SMTP") as smtp:
            server = smtp.return_value.__enter__.return_value
            result = ShareService().share("act-1", "parent@example.com")

            assert result["sent"] is True
        
            assert result["pdf_bytes"] > 1000
            message = server.send_message.call_args.args[0]
            assert message["To"] == "parent@example.com"
            assert [a.get_filename() for a in message.iter_attachments()] == [
                "learning-activity.pdf"]


def test_it_7_2_email_server_refusal_surfaces_as_send_error(fake_supabase):
    fake_supabase(seed={"learning_activities": [ACTIVITY]})
    with patch("app.gateways.email_gateway.settings") as cfg:
        smtp_on(cfg)
        with patch("smtplib.SMTP", side_effect=OSError("Connection refused")):
            with pytest.raises(EmailSendError):
                ShareService().share("act-1", "parent@example.com")


def test_it_7_3_render_failure_surfaces_as_export_error(fake_supabase):
    fake_supabase(seed={"learning_activities": [UNRENDERABLE]})
    with patch("app.gateways.email_gateway.settings") as cfg:
        smtp_on(cfg)
        with patch("smtplib.SMTP") as smtp:
            with pytest.raises(ExportError):
                ShareService().share("act-blank", "parent@example.com")
            smtp.assert_not_called()



# IT: 7.4-7.7 
# add ShareController
# --------------------------------------------------------------------------- #
def test_it_7_4_post_share_returns_success_through_the_whole_stack(
    client, auth_ok, fake_supabase):
    fake_supabase(seed={"learning_activities": [ACTIVITY]})
    with patch("app.gateways.email_gateway.settings") as cfg:
        smtp_on(cfg)
        with patch("smtplib.SMTP"):
            response = client.post("/share", json={
                "activity_id": "act-1", "recipient_email": "parent@example.com",
            })

    assert response.status_code == 200
    assert response.json()["sent"] is True


def test_it_7_5_post_share_rejects_an_invalid_address_with_400(
    client, auth_ok, fake_supabase):
    fake_supabase(seed={"learning_activities": [ACTIVITY]})
    response = client.post("/share", json={
        "activity_id": "act-1", "recipient_email": "not-an-email",
    })
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid email address, please re-enter"


def test_it_7_6_post_share_returns_422_when_the_render_fails(
    client, auth_ok, fake_supabase
):
    fake_supabase(seed={"learning_activities": [UNRENDERABLE]})
    with patch("app.gateways.email_gateway.settings") as cfg:
        smtp_on(cfg)
        with patch("smtplib.SMTP") as smtp:
            response = client.post("/share", json={
                "activity_id": "act-blank", "recipient_email": "parent@example.com",
            })

            smtp.assert_not_called()

    assert response.status_code == 422


def test_it_7_7_post_share_returns_502_when_the_email_server_refuses(
    client, auth_ok, fake_supabase
):
    fake_supabase(seed={"learning_activities": [ACTIVITY]})
    with patch("app.gateways.email_gateway.settings") as cfg:
        smtp_on(cfg)
        with patch("smtplib.SMTP", side_effect=OSError("Connection refused")):
            response = client.post("/share", json={
                "activity_id": "act-1", "recipient_email": "parent@example.com",
            })

    assert response.status_code == 502


