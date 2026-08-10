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
