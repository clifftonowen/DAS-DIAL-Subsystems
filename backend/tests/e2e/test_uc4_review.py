"""E2E — UC4 Submit Review through the real API and Supabase test project."""
import uuid

import pytest

pytestmark = pytest.mark.e2e


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_uc4_review_is_persisted_and_returned(client, access_token, uc4_activity):
    marker = f"UC4 API E2E review {uuid.uuid4().hex}"
    activity_id = uc4_activity["id"]

    submitted = client.post(
        "/reviews",
        headers=_auth(access_token),
        json={"activity_id": activity_id, "text": marker},
    )

    assert submitted.status_code == 200
    assert submitted.json()["text"] == marker

    listed = client.get(
        f"/reviews/{activity_id}", headers=_auth(access_token),
    )
    assert listed.status_code == 200
    assert any(review["text"] == marker for review in listed.json())


def test_uc4_approval_is_persisted_without_changing_uc3_status(
    client, access_token, uc4_activity,
):
    marker = f"UC4 API E2E approval {uuid.uuid4().hex}"
    activity_id = uc4_activity["id"]

    submitted = client.post(
        "/reviews",
        headers=_auth(access_token),
        json={
            "activity_id": activity_id, "text": marker,
            "approval_status": "APPROVED",
        },
    )

    assert submitted.status_code == 200
    assert submitted.json()["approval_status"] == "APPROVED"
    assert submitted.json()["reviewer"]["email"]

    listed = client.get(f"/reviews/{activity_id}", headers=_auth(access_token))
    saved = next(review for review in listed.json() if review["text"] == marker)
    assert saved["approval_status"] == "APPROVED"

    activities = client.get(
        f"/profiles/{uc4_activity['learner_id']}/activities",
        headers=_auth(access_token),
    )
    stored_activity = next(
        activity for activity in activities.json() if activity["id"] == activity_id
    )
    assert stored_activity["status"] == "GENERATED"


def test_uc4_database_rejects_a_review_for_a_missing_activity(client, access_token):
    missing_activity = str(uuid.uuid4())

    response = client.post(
        "/reviews",
        headers=_auth(access_token),
        json={"activity_id": missing_activity, "text": "Cannot be attached."},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Review could not be saved"
    listed = client.get(
        f"/reviews/{missing_activity}", headers=_auth(access_token),
    )
    assert listed.status_code == 200
    assert listed.json() == []
