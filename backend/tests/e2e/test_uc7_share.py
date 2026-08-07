"""E2E use case: UC7 "Share Learning Activity" 


    TC7a  therapist shares an activity            -> 200, confirmation
    TC7b  invalid recipient format                -> 400, re-entry prompt
    TC7c  the activity cannot be rendered as PDF  -> 422, abort
    TC7d  the email server refuses the message    -> 502, retry offered



Levels below this one need no setup: `pytest -m "unit or integration"`.
"""
import os
from unittest.mock import patch
import pytest

pytestmark = pytest.mark.e2e


def _auth(token):
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def activity_id():
    value = os.environ.get("TEST_ACTIVITY_ID")
    if not value:
        pytest.skip("set TEST_ACTIVITY_ID to a row in learning_activities")
    return value

@pytest.fixture
def smtp_enabled():
    with patch("app.gateways.email_gateway.settings") as cfg:
        cfg.email_enabled = True
        cfg.smtp_host = "smtp.invalid.test"
        cfg.smtp_port = 587
        cfg.smtp_use_tls = True
        cfg.smtp_user = ""
        cfg.smtp_password = ""
        cfg.smtp_from = "no-reply@das-dial.com"
        yield cfg


# TC7a — the operational flow
def test_therapist_shares_an_activity_by_email(client, access_token, activity_id, smtp_enabled):
    with patch("smtplib.SMTP") as smtp:
        server = smtp.return_value.__enter__.return_value
        resp = client.post("/share", headers=_auth(access_token), json={
            "activity_id": activity_id,
            "recipient_email": "parent@example.com",
        })

    assert resp.status_code == 200
    body = resp.json()
    assert body["sent"] is True
    assert body["recipient_email"] == "parent@example.com"
    # a stub would be a few bytes.
    assert body["pdf_bytes"] > 1000

    message = server.send_message.call_args.args[0]
    assert message["To"] == "parent@example.com"
    assert [a.get_filename() for a in message.iter_attachments()] == [
        "learning-activity.pdf"]


# TC7b — invalid recipient format
@pytest.mark.parametrize("address", ["not-an-email", "a@b", "parent@", ""])
def test_an_invalid_recipient_is_rejected(client, access_token, activity_id, address):
    with patch("smtplib.SMTP") as smtp:
        resp = client.post("/share", headers=_auth(access_token), json={
            "activity_id": activity_id,
            "recipient_email": address,
        })

        smtp.assert_not_called()

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid email address, please re-enter"



# TC7c — the activity cannot be exported 
def test_an_unknown_activity_cannot_be_exported(client, access_token):
    
    missing = "00000000-0000-0000-0000-000000000000"

    with patch("smtplib.SMTP") as smtp:
        resp = client.post("/share", headers=_auth(access_token), json={
            "activity_id": missing,
            "recipient_email": "parent@example.com",
        })
        smtp.assert_not_called()
    assert resp.status_code == 422


# TC7d — the email server refuses
def test_tc7d_a_refused_message_is_reported_as_a_send_failure(client, access_token, activity_id, smtp_enabled):
    with patch("smtplib.SMTP", side_effect=OSError("Connection refused")):
        resp = client.post("/share", headers=_auth(access_token), json={
            "activity_id": activity_id,
            "recipient_email": "parent@example.com",
        })

    assert resp.status_code == 502
    assert resp.json()["detail"]
